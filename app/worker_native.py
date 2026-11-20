"""Chạy worker FFmpeg trực tiếp trên Windows (không Docker), cùng chữ ký với run_container.

Mỗi job chạy trong một tiến trình con `python -m worker.transcode`. Trên Windows tiến trình con
được đưa vào Job Object: quá thời gian, bị huỷ, hoặc worker chết thì toàn bộ cây tiến trình
(kể cả ffmpeg.exe) bị dừng, không để lại tiến trình mồ côi.
"""

from collections import deque
import json
import logging
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from uuid import UUID

from app.worker_runner import worker_result
from worker.transcode import MediaError, encode_timeout, setting

ROOT = Path(__file__).resolve().parent.parent
HEARTBEAT_SECONDS = 3
logger = logging.getLogger("app.worker")
WINDOWS = os.name == "nt"

if WINDOWS:
    import ctypes
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimits), ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    KILL_ON_JOB_CLOSE = 0x2000
    JOB_MEMORY_LIMIT = 0x200
    JOB_AFFINITY_LIMIT = 0x10
    EXTENDED_LIMIT_INFORMATION = 9
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.GetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t)]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


def cpu_mask(count):
    """Mặt nạ gồm `count` CPU cao nhất mà worker được dùng; 0 nghĩa là máy không có CPU dư để giới hạn.

    `-threads` của FFmpeg chỉ giới hạn luồng codec; đo thực tế vẫn dùng hơn 3 nhân. Affinity là giới hạn cứng,
    nhờ đó API và PostgreSQL luôn còn CPU khi đang mã hoá.
    """
    own, system = ctypes.c_size_t(), ctypes.c_size_t()
    if not kernel32.GetProcessAffinityMask(kernel32.GetCurrentProcess(), ctypes.byref(own), ctypes.byref(system)):
        return 0
    cpus = [bit for bit in range(64) if own.value >> bit & 1]
    if len(cpus) <= count:
        return 0
    return sum(1 << bit for bit in cpus[-count:])


def create_job(memory_bytes, cpus=0):
    """Job Object: giới hạn RAM/CPU cả cây tiến trình và tự kill khi handle đóng (worker chết)."""
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise OSError(ctypes.get_last_error(), "CreateJobObject failed")
    limits = ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = KILL_ON_JOB_CLOSE | JOB_MEMORY_LIMIT
    limits.JobMemoryLimit = memory_bytes
    mask = cpu_mask(cpus) if cpus else 0
    if mask:
        limits.BasicLimitInformation.LimitFlags |= JOB_AFFINITY_LIMIT
        limits.BasicLimitInformation.Affinity = mask
    if not kernel32.SetInformationJobObject(job, EXTENDED_LIMIT_INFORMATION, ctypes.byref(limits), ctypes.sizeof(limits)):
        kernel32.CloseHandle(job)
        raise OSError(ctypes.get_last_error(), "SetInformationJobObject failed")
    return job


def stop_tree(process, job):
    """Dừng tiến trình con cùng mọi tiến trình cháu (ffmpeg/ffprobe)."""
    if WINDOWS and job:
        kernel32.TerminateJobObject(job, 1)
    elif not WINDOWS:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        process.kill()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        raise MediaError("worker_cleanup_unconfirmed", retryable=True) from None


def read_stderr(stream, state, tail):
    for line in stream:
        line = line.strip()
        if line.startswith("progress "):
            try:
                state["percent"] = int(line.split()[1])
            except (ValueError, IndexError):
                pass
        elif line:
            tail.append(line[:500])


def run_native(source, output, attempt_id, on_progress=None, timeout=None):
    attempt_id = UUID(str(attempt_id))
    source, output = Path(source).resolve(), Path(output).resolve()
    timeout = timeout or encode_timeout() + 60
    memory = setting("WORKER_MEMORY_LIMIT_MB", 1536, 256, 16384) * 1024 * 1024
    # Danh sách tham số + shell=False: tên file không bao giờ được shell diễn giải.
    arguments = [sys.executable, "-m", "worker.transcode", "--progress", str(source), str(output)]
    options = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "stdin": subprocess.DEVNULL,
               "cwd": ROOT, "text": True, "encoding": "utf-8", "errors": "replace"}
    if WINDOWS:
        # Ưu tiên thấp hơn bình thường để API vẫn phản hồi khi FFmpeg đang mã hoá.
        options["creationflags"] = subprocess.BELOW_NORMAL_PRIORITY_CLASS | subprocess.CREATE_NO_WINDOW
    else:
        options["start_new_session"] = True
    job = None
    started = time.monotonic()
    try:
        job = create_job(memory, setting("FFMPEG_THREADS", 1, 1, 2)) if WINDOWS else None
        process = subprocess.Popen(arguments, **options)
        if job and not kernel32.AssignProcessToJobObject(job, int(process._handle)):
            process.kill()
            raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject failed")
    except OSError:
        if job:
            kernel32.CloseHandle(job)
        raise MediaError("worker_runtime_unavailable", retryable=True) from None

    state, tail, stdout = {"percent": None}, deque(maxlen=40), []
    readers = [threading.Thread(target=read_stderr, args=(process.stderr, state, tail), daemon=True),
               threading.Thread(target=lambda: stdout.append(process.stdout.read(65536)), daemon=True)]
    for reader in readers:
        reader.start()
    failure = None
    last_beat = time.monotonic()
    try:
        while process.poll() is None:
            now = time.monotonic()
            if now - started > timeout:
                failure = "worker_timeout"
            elif on_progress and now - last_beat >= HEARTBEAT_SECONDS:
                last_beat = now
                if on_progress(state["percent"]) is False:
                    failure = "worker_cancelled"
            if failure:
                stop_tree(process, job)
                break
            time.sleep(0.2)
    except BaseException:
        # Ctrl+C hoặc lỗi bất ngờ: không để ffmpeg chạy tiếp sau khi worker thoát.
        if process.poll() is None:
            stop_tree(process, job)
        raise
    finally:
        for reader in readers:
            reader.join(timeout=5)
        process.stdout.close()
        process.stderr.close()
        if job:
            kernel32.CloseHandle(job)
    seconds = round(time.monotonic() - started, 3)
    record = {"event": "worker_process", "attempt_id": str(attempt_id), "exit_code": process.returncode,
              "seconds": seconds, "failure": failure}
    if failure or process.returncode != 0:
        # Chỉ giữ tối đa 40 dòng cuối của stderr, mỗi dòng 500 ký tự.
        logger.warning(json.dumps({**record, "stderr_tail": list(tail)}))
    else:
        logger.info(json.dumps(record))
    if failure:
        raise MediaError(failure, retryable=True)
    if on_progress and state["percent"] is not None:
        on_progress(state["percent"])
    return worker_result(process.returncode, "".join(stdout), output, "worker")
