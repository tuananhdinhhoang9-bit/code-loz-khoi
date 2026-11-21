import argparse
from fractions import Fraction
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

MAX_INPUT_BYTES = 50_000_000
MAX_OUTPUT_BYTES = 50_000_000
MAX_SECONDS = 30
VIDEO_CODECS = {"h264", "hevc", "vp8", "vp9", "mpeg4", "av1"}
AUDIO_CODECS = {"aac", "opus", "vorbis", "mp3", "pcm_s16le", "flac"}
SCALE = "scale=w='min(iw,854)':h='min(ih,480)':force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1"


class MediaError(Exception):
    def __init__(self, code, retryable=False, detail=""):
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.detail = detail


def setting(name, default, low, high):
    # Đọc biến môi trường lúc chạy (không phải lúc import) để service nạp .env trước vẫn có hiệu lực.
    try:
        value = int(os.getenv(name, default))
    except ValueError:
        value = default
    return min(high, max(low, value))


def max_input_bytes():
    return setting("MAX_UPLOAD_BYTES", MAX_INPUT_BYTES, 1, 2_000_000_000)


def encode_timeout():
    return setting("TRANSCODE_TIMEOUT_SECONDS", 90, 30, 3600)


def threads():
    return str(setting("FFMPEG_THREADS", 1, 1, 2))


def tool(name):
    # FFMPEG_BIN / FFPROBE_BIN cho phép trỏ thẳng tới file .exe khi service không có PATH.
    return os.getenv(name.upper() + "_BIN") or name


def error_tail(raw):
    return " | ".join(raw.decode("utf-8", "replace").strip().splitlines()[-8:])[:1500]


def run_tool(arguments, timeout, error_code):
    try:
        return subprocess.run(arguments, check=True, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise MediaError("processing_timeout", retryable=True) from None
    except subprocess.CalledProcessError as error:
        raise MediaError(error_code, detail=error_tail(error.stderr or b"")) from None
    except OSError:
        raise MediaError("media_tool_unavailable", retryable=True) from None


def run_encode(arguments, timeout, seconds, on_progress=None):
    """Chạy FFmpeg, đọc tiến độ thật từ -progress và dừng tiến trình khi quá thời gian."""
    command = [arguments[0], "-progress", "pipe:1", "-nostats", *arguments[1:]]
    expired = threading.Event()
    with tempfile.TemporaryFile() as errors:
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors, stdin=subprocess.DEVNULL)
        except OSError:
            raise MediaError("media_tool_unavailable", retryable=True) from None

        def stop():
            expired.set()
            process.kill()

        timer = threading.Timer(timeout, stop)
        timer.start()
        try:
            for line in process.stdout:
                if on_progress and line.startswith(b"out_time_us="):
                    try:
                        done = int(line.split(b"=")[1]) / 1_000_000
                    except ValueError:
                        continue
                    on_progress(max(0, min(99, int(done * 100 / seconds))))
            code = process.wait()
        finally:
            timer.cancel()
            if process.poll() is None:
                process.kill()
                process.wait()
            process.stdout.close()
        if expired.is_set():
            raise MediaError("processing_timeout", retryable=True)
        if code != 0:
            errors.seek(max(0, errors.seek(0, 2) - 4000))
            raise MediaError("decode_or_encode_failed", detail=error_tail(errors.read()))


def probe(path):
    result = run_tool([
        tool("ffprobe"), "-v", "error", "-protocol_whitelist", "file,pipe",
        "-format_whitelist", "mov,matroska,webm,image2,jpeg_pipe",
        "-show_entries", "stream=codec_name,codec_type,width,height,pix_fmt,sample_aspect_ratio,avg_frame_rate,duration:format=format_name,duration,size",
        "-of", "json", str(path),
    ], 10, "invalid_media")
    try:
        return json.loads(result.stdout)
    except (ValueError, UnicodeError):
        raise MediaError("invalid_probe_result") from None


def duration(info):
    try:
        values = [float(info["format"]["duration"])]
        values += [float(s["duration"]) for s in info.get("streams", []) if s.get("duration") not in (None, "N/A")]
        if any(not math.isfinite(value) or value <= 0 for value in values):
            raise ValueError
        return max(values)
    except (KeyError, TypeError, ValueError):
        raise MediaError("invalid_duration") from None


def validate_source(path):
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise MediaError("input_not_regular_file")
    if not 0 < path.stat().st_size <= max_input_bytes():
        raise MediaError("input_size_invalid")
    info = probe(path)
    seconds = duration(info)
    if seconds > MAX_SECONDS:
        raise MediaError("input_too_long")
    videos = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    audios = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    if len(videos) != 1 or len(audios) > 1 or len(info.get("streams", [])) > 4:
        raise MediaError("unsupported_streams")
    video = videos[0]
    if video.get("codec_name") not in VIDEO_CODECS or any(s.get("codec_name") not in AUDIO_CODECS for s in audios):
        raise MediaError("unsupported_codec")
    width, height = video.get("width", 0), video.get("height", 0)
    if not (2 <= width <= 4096 and 2 <= height <= 4096 and width * height <= 8_847_360):
        raise MediaError("invalid_dimensions")
    if video.get("sample_aspect_ratio") not in (None, "N/A", "0:1", "1:1"):
        raise MediaError("unsupported_pixel_aspect")
    try:
        rate = float(Fraction(video.get("avg_frame_rate", "0/1")))
    except (ValueError, ZeroDivisionError):
        raise MediaError("invalid_frame_rate") from None
    if not 0 < rate <= 60:
        raise MediaError("invalid_frame_rate")
    return {"duration_seconds": seconds, "has_audio": bool(audios)}


def verify_outputs(directory, source):
    directory = Path(directory)
    mp4, jpg = directory / "video.mp4", directory / "thumbnail.jpg"
    for path in [mp4, jpg]:
        if not path.is_file() or not 0 < path.stat().st_size <= MAX_OUTPUT_BYTES:
            raise MediaError("incomplete_outputs")
    info = probe(mp4)
    videos = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    audios = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    seconds = duration(info)
    if len(videos) != 1 or videos[0].get("codec_name") != "h264" or videos[0].get("pix_fmt") != "yuv420p":
        raise MediaError("invalid_output_codec")
    if any(s.get("codec_name") != "aac" for s in audios) or bool(audios) != source["has_audio"]:
        raise MediaError("invalid_output_audio")
    width, height = videos[0].get("width", 0), videos[0].get("height", 0)
    if not (0 < width <= 854 and 0 < height <= 480 and width % 2 == height % 2 == 0):
        raise MediaError("invalid_output_dimensions")
    if seconds > MAX_SECONDS + 0.15 or abs(seconds - source["duration_seconds"]) > 0.35:
        raise MediaError("invalid_output_duration")
    image = probe(jpg).get("streams", [])
    if len(image) != 1 or image[0].get("codec_name") != "mjpeg":
        raise MediaError("invalid_thumbnail")
    return {"duration_ms": round(seconds * 1000), "width": width, "height": height,
            "mp4_bytes": mp4.stat().st_size, "thumbnail_bytes": jpg.stat().st_size}


def transcode(source_path, output_directory, on_progress=None):
    source_path = Path(source_path)
    source = validate_source(source_path)
    source_path = source_path.resolve()
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    if any(directory.iterdir()):
        raise MediaError("attempt_directory_not_empty")
    mp4 = directory / "video.mp4"
    count = threads()
    arguments = [
        tool("ffmpeg"), "-nostdin", "-v", "error", "-xerror", "-n",
        "-protocol_whitelist", "file,pipe", "-format_whitelist", "mov,matroska,webm",
        "-threads", count, "-i", str(source_path), "-map", "0:v:0", "-map", "0:a:0?",
        "-map_metadata", "-1", "-vf", SCALE, "-c:v", "libx264", "-preset", "fast",
        "-crf", "23", "-pix_fmt", "yuv420p", "-threads", count, "-filter_threads", "1",
        "-r", "30", "-c:a", "aac", "-b:a", "96k", "-t", "31",
        "-fs", str(MAX_OUTPUT_BYTES), "-movflags", "+faststart", str(mp4),
    ]
    try:
        run_encode(arguments, encode_timeout(), source["duration_seconds"], on_progress)
        run_tool([
            tool("ffmpeg"), "-nostdin", "-v", "error", "-n", "-threads", "1", "-i", str(mp4),
            "-frames:v", "1", "-vf", SCALE, "-q:v", "3", "-threads", "1",
            "-filter_threads", "1", "-update", "1", str(directory / "thumbnail.jpg"),
        ], 15, "thumbnail_failed")
        metadata = verify_outputs(directory, source)
        (directory / "metadata.json").write_text(json.dumps(metadata) + "\n", encoding="utf-8")
        return metadata
    except BaseException:
        # Không để file dang dở bị hiểu nhầm là kết quả đã kiểm tra thành công.
        for name in ["video.mp4", "thumbnail.jpg", "metadata.json"]:
            (directory / name).unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description="Transcode one bounded private source file")
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--progress", action="store_true", help="report measured FFmpeg progress on stderr")
    args = parser.parse_args()
    last = [-1]

    def report(percent):
        if percent != last[0]:
            last[0] = percent
            print(f"progress {percent}", file=sys.stderr, flush=True)

    try:
        metadata = transcode(args.input, args.output, report if args.progress else None)
        print(json.dumps({"status": "validated", **metadata}))
        return 0
    except MediaError as error:
        if error.detail:
            print("detail " + error.detail, file=sys.stderr, flush=True)
        print(json.dumps({"status": "failed", "error": error.code, "retryable": error.retryable}))
        return 2 if not error.retryable else 3


if __name__ == "__main__":
    raise SystemExit(main())
