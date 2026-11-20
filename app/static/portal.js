"use strict";
// Token chỉ nằm trong bộ nhớ trang: tải lại trang là phải đăng nhập lại.
let token = "";
let user = null;
let provider = "local";
let maxUploadBytes = 50_000_000;
let videos = [];
let selectedId = null;
let pollTimer = null;
let toastTimer = null;
const details = new Map(); // video id -> { progress, error }
const thumbnails = new Map(); // video id -> { url, at }
const $ = (id) => document.getElementById(id);
const megabytes = () => Math.floor(maxUploadBytes / 1_000_000);
const ACTIVE = new Set(["QUEUED", "PROCESSING", "RETRYING"]);

const labels = {
  PENDING_UPLOAD: "Chờ tải lên",
  QUEUED: "Đang xếp hàng",
  PROCESSING: "Đang xử lý",
  RETRYING: "Đang thử lại",
  READY: "Sẵn sàng",
  FAILED: "Xử lý thất bại",
};
const errors = {
  authentication_required: "Hãy đăng nhập trước khi tiếp tục.",
  invalid_or_expired_token: "Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại.",
  auth_not_configured: "Đăng nhập chưa được cấu hình. Hãy liên hệ quản trị viên.",
  auth_temporarily_unavailable: "Chưa xác minh được tài khoản. Hãy thử lại sau.",
  invalid_credentials: "Email hoặc mật khẩu không đúng.",
  too_many_attempts: "Đăng nhập sai quá nhiều lần. Hãy thử lại sau 15 phút.",
  video_not_ready: "Video chưa sẵn sàng để xem.",
  video_not_found: "Không tìm thấy video hoặc bạn chưa được cấp quyền.",
  video_processing: "Video đang được xử lý. Hãy xoá sau khi xử lý xong.",
  upload_too_large: "Video vượt quá dung lượng cho phép.",
  unsupported_content_type: "Chỉ nhận video MP4, WebM hoặc MOV.",
  object_not_ready: "File chưa được tải lên đầy đủ.",
  storage_full: "Máy chủ sắp hết dung lượng lưu trữ. Hãy báo quản trị viên.",
  database_unavailable: "Máy chủ đang bận. Hãy thử lại sau.",
  storage_unavailable: "Kho lưu trữ đang bận. Hãy thử lại sau.",
  admin_required: "Chỉ quản trị viên mới làm được việc này.",
  invalid_email: "Email không hợp lệ.",
  weak_password: "Mật khẩu phải có ít nhất 12 ký tự.",
  user_exists: "Email này đã có tài khoản.",
  user_not_found: "Không tìm thấy tài khoản này.",
  cannot_disable_self: "Bạn không thể tự vô hiệu hoá tài khoản của mình.",
};
const failures = {
  input_too_long: "Video dài hơn 30 giây.",
  invalid_media: "File không phải là video hợp lệ.",
  unsupported_codec: "Kiểu mã hoá của video không được hỗ trợ.",
  unsupported_streams: "Video có cấu trúc không được hỗ trợ.",
  invalid_dimensions: "Kích thước khung hình không được hỗ trợ.",
  input_size_invalid: "Dung lượng file vượt quá giới hạn.",
};

// ---------- Nền sao ----------
function startStarfield() {
  const canvas = $("starfield");
  const context = canvas.getContext("2d");
  const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let stars = [];
  let meteor = null;
  let frame = 0;
  function resize() {
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = window.innerWidth * ratio;
    canvas.height = window.innerHeight * ratio;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    const count = Math.min(260, Math.floor((window.innerWidth * window.innerHeight) / 5200));
    stars = Array.from({ length: count }, () => ({
      x: Math.random() * window.innerWidth,
      y: Math.random() * window.innerHeight,
      size: Math.random() * 1.5 + 0.3,
      speed: Math.random() * 0.12 + 0.02,
      phase: Math.random() * Math.PI * 2,
      tint: Math.random(),
    }));
  }
  function draw() {
    const width = window.innerWidth;
    const height = window.innerHeight;
    context.clearRect(0, 0, width, height);
    frame += 1;
    for (const star of stars) {
      if (!still) {
        star.x -= star.speed;
        if (star.x < -2) star.x = width + 2;
      }
      const glow = 0.45 + 0.55 * Math.sin(frame * 0.02 + star.phase);
      const color = star.tint > 0.85 ? "69, 227, 255" : star.tint > 0.7 ? "190, 170, 255" : "235, 240, 255";
      context.fillStyle = `rgba(${color}, ${still ? 0.8 : glow})`;
      context.beginPath();
      context.arc(star.x, star.y, star.size, 0, Math.PI * 2);
      context.fill();
    }
    if (!still) {
      if (!meteor && Math.random() < 0.004) meteor = { x: Math.random() * width * 0.8 + width * 0.2, y: -20, life: 0 };
      if (meteor) {
        meteor.x -= 9;
        meteor.y += 5.5;
        meteor.life += 1;
        const trail = context.createLinearGradient(meteor.x, meteor.y, meteor.x + 110, meteor.y - 67);
        trail.addColorStop(0, "rgba(255, 255, 255, 0.9)");
        trail.addColorStop(1, "rgba(69, 227, 255, 0)");
        context.strokeStyle = trail;
        context.lineWidth = 1.6;
        context.beginPath();
        context.moveTo(meteor.x, meteor.y);
        context.lineTo(meteor.x + 110, meteor.y - 67);
        context.stroke();
        if (meteor.life > 90) meteor = null;
      }
      if (!document.hidden) window.requestAnimationFrame(draw);
    }
  }
  window.addEventListener("resize", () => { resize(); if (still) draw(); });
  document.addEventListener("visibilitychange", () => { if (!document.hidden && !still) window.requestAnimationFrame(draw); });
  resize();
  draw();
}

// ---------- Thông báo và gọi API ----------
function say(text, isError = false) {
  const box = $("message");
  window.clearTimeout(toastTimer);
  box.textContent = text;
  box.classList.toggle("error", isError);
  box.hidden = false;
  if (!isError) toastTimer = window.setTimeout(() => { box.hidden = true; }, 6000);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...(token ? { Authorization: "Bearer " + token } : {}),
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && user && data.error === "invalid_or_expired_token") signOut(false);
    const error = new Error(errors[data.error] || "Không hoàn tất được thao tác. Hãy thử lại.");
    error.code = data.error;
    throw error;
  }
  return data;
}

// ---------- Điều hướng theo mục ----------
const views = [...document.querySelectorAll(".view")];
function route() {
  const wanted = window.location.hash.slice(1) || "home";
  const view = views.find((item) => item.id === wanted) || views[0];
  for (const item of views) item.hidden = item !== view;
  $("view-title").textContent = view.dataset.title;
  document.querySelectorAll(".nav-link").forEach((link) => {
    const active = link.dataset.view === view.id;
    link.classList.toggle("active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  $("sidebar").classList.remove("open");
  $("menu-toggle").setAttribute("aria-expanded", "false");
  if (view.id === "library" && user) refresh().catch((error) => say(error.message, true));
  if (view.id === "users" && user && user.admin) loadUsers().catch((error) => say(error.message, true));
  window.scrollTo(0, 0);
}
window.addEventListener("hashchange", route);
$("menu-toggle").addEventListener("click", () => {
  const open = $("sidebar").classList.toggle("open");
  $("menu-toggle").setAttribute("aria-expanded", String(open));
});

// ---------- Đăng nhập ----------
function applyAuth() {
  const local = provider === "local";
  $("identity").textContent = user ? user.uid : "Chưa đăng nhập";
  $("role").textContent = user ? (user.admin ? "Quản trị viên" : "Người dùng") : "";
  $("status-dot").classList.toggle("on", Boolean(user));
  $("logout").hidden = !user;
  $("login-form").hidden = Boolean(user);
  $("profile").hidden = !user;
  $("password-form").hidden = !local;
  $("library-gate").hidden = Boolean(user);
  $("upload-gate").hidden = Boolean(user);
  $("upload-form").hidden = !user;
  $("nav-users").hidden = !(user && user.admin && local);
  $("users-gate").hidden = Boolean(user && user.admin && local);
  $("users-body").hidden = !(user && user.admin && local);
  $("stats-hint").hidden = Boolean(user);
  if (user) {
    $("profile-name").textContent = user.uid;
    $("profile-role").textContent = user.admin ? "Quản trị viên: quản lý được tài khoản và xem số liệu hệ thống." : "Người dùng: tải lên, xem và chia sẻ video của mình.";
  }
}

function signOut(showMessage = true) {
  token = "";
  user = null;
  videos = [];
  selectedId = null;
  details.clear();
  thumbnails.clear();
  window.clearTimeout(pollTimer);
  closePlayer();
  $("password").value = "";
  $("detail").hidden = true;
  $("tracker").hidden = true;
  render();
  applyAuth();
  if (showMessage) say("Đã đăng xuất.");
  else say("Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại.", true);
}

async function signIn(email, password) {
  const configResponse = await fetch("/api/auth/config");
  const config = await configResponse.json();
  if (!configResponse.ok) throw new Error(errors[config.error]);
  if (config.provider === "local") {
    const login = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
      signal: AbortSignal.timeout(15000),
    });
    const session = await login.json();
    if (!login.ok || !session.token) throw new Error(errors[session.error] || errors.invalid_credentials);
    return session.token;
  }
  if (config.provider === "cognito") {
    // Mật khẩu đi thẳng từ trình duyệt tới Cognito; máy chủ của trang chỉ nhận ID token.
    const login = await fetch(`https://cognito-idp.${config.region}.amazonaws.com/`, {
      method: "POST",
      headers: { "Content-Type": "application/x-amz-json-1.1", "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth" },
      body: JSON.stringify({ AuthFlow: "USER_PASSWORD_AUTH", ClientId: config.client_id, AuthParameters: { USERNAME: email, PASSWORD: password } }),
      signal: AbortSignal.timeout(15000),
    });
    const result = await login.json().catch(() => ({}));
    if (result.ChallengeName) throw new Error("Tài khoản chưa có mật khẩu chính thức. Hãy nhờ quản trị viên đặt mật khẩu.");
    if (!login.ok || !result.AuthenticationResult?.IdToken) throw new Error(errors.invalid_credentials);
    return result.AuthenticationResult.IdToken;
  }
  const login = await fetch(
    "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=" + encodeURIComponent(config.api_key),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, returnSecureToken: true }),
      signal: AbortSignal.timeout(15000),
    },
  );
  const credentials = await login.json();
  if (!login.ok || !credentials.idToken) throw new Error(errors.invalid_credentials);
  return credentials.idToken;
}

$("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const email = $("email").value.trim();
  const password = $("password").value;
  $("password").value = "";
  try {
    token = await signIn(email, password);
    user = await api("/api/me");
    applyAuth();
    say("Đăng nhập thành công.");
    window.location.hash = "#library";
    await refresh();
  } catch (error) {
    token = "";
    user = null;
    applyAuth();
    say(error.message, true);
  }
});

$("logout").addEventListener("click", async () => {
  if (token) await api("/api/auth/logout", { method: "POST" }).catch(() => {});
  signOut();
});

$("password-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api("/api/auth/password", {
      method: "POST",
      body: JSON.stringify({ current_password: $("current-password").value, new_password: $("new-password").value }),
    });
    event.target.reset();
    signOut(false);
    say("Đã đổi mật khẩu. Hãy đăng nhập lại bằng mật khẩu mới.");
  } catch (error) {
    say(error.code === "invalid_credentials" ? "Mật khẩu hiện tại không đúng." : error.message, true);
  }
});

// ---------- Thư viện ----------
function badge(state) {
  const item = document.createElement("span");
  item.className = "badge";
  item.dataset.state = state;
  item.textContent = labels[state] || state;
  return item;
}

function progressBar(video) {
  const bar = document.createElement("div");
  bar.className = "progress";
  const fill = document.createElement("i");
  const percent = details.get(video.id)?.progress;
  if (video.status === "PROCESSING" && Number.isInteger(percent)) fill.style.width = percent + "%";
  else bar.classList.add("busy");
  bar.append(fill);
  return bar;
}

async function thumbnailUrl(video) {
  const cached = thumbnails.get(video.id);
  if (cached && Date.now() - cached.at < 100_000) return cached.url;
  const data = await api(`/api/videos/${video.id}/thumbnail`);
  thumbnails.set(video.id, { url: data.url, at: Date.now() });
  return data.url;
}

function card(video) {
  const item = document.createElement("li");
  item.className = "card" + (video.id === selectedId ? " selected" : "");
  item.dataset.state = video.status;

  const thumb = document.createElement("button");
  thumb.type = "button";
  thumb.className = "thumb";
  thumb.setAttribute("aria-label", (video.status === "READY" ? "Xem video " : "Chi tiết video ") + video.title);
  const icon = document.createElement("span");
  icon.className = "thumb-icon";
  icon.textContent = video.status === "FAILED" ? "✕" : "▶";
  thumb.append(icon);
  if (video.status === "READY") {
    const image = document.createElement("img");
    image.alt = "";
    image.loading = "lazy";
    image.addEventListener("error", () => image.remove());
    thumbnailUrl(video).then((url) => { image.src = url; }).catch(() => image.remove());
    const play = document.createElement("span");
    play.className = "play-badge";
    play.textContent = "▶";
    thumb.append(image, play);
  }
  thumb.addEventListener("click", () => {
    select(video.id);
    if (video.status === "READY") openPlayer(video);
  });

  const body = document.createElement("div");
  body.className = "card-body";
  const title = document.createElement("strong");
  title.className = "card-title";
  title.textContent = video.title;
  const meta = document.createElement("span");
  meta.className = "card-meta";
  meta.textContent = video.owner_uid === user.uid ? "Của bạn" : "Chia sẻ bởi " + video.owner_uid;
  const foot = document.createElement("div");
  foot.className = "card-foot";
  const more = document.createElement("button");
  more.type = "button";
  more.className = "link";
  more.textContent = "Chi tiết";
  more.addEventListener("click", () => select(video.id, true));
  foot.append(badge(video.status), more);
  body.append(title, meta, foot);
  if (ACTIVE.has(video.status)) body.append(progressBar(video));
  item.append(thumb, body);
  return item;
}

function render() {
  const list = $("videos");
  list.replaceChildren();
  if (user && !videos.length) {
    const empty = document.createElement("li");
    empty.className = "empty";
    const text = document.createElement("p");
    text.textContent = "Thư viện còn trống. Tải video đầu tiên của bạn lên, hoặc nhờ người khác chia sẻ video cho bạn.";
    const link = document.createElement("a");
    link.className = "button";
    link.href = "#upload";
    link.textContent = "Tải video lên";
    empty.append(text, link);
    list.append(empty);
  }
  if (user) for (const video of videos) list.append(card(video));
  const count = (matches) => videos.filter((video) => matches(video.status)).length;
  $("stat-total").textContent = user ? videos.length : "–";
  $("stat-ready").textContent = user ? count((status) => status === "READY") : "–";
  $("stat-active").textContent = user ? count((status) => ACTIVE.has(status)) : "–";
  $("stat-failed").textContent = user ? count((status) => status === "FAILED") : "–";
  $("nav-count").hidden = !user || !videos.length;
  $("nav-count").textContent = videos.length;
  fillDetail();
}

async function refresh() {
  if (!user) return;
  window.clearTimeout(pollTimer);
  const data = await api("/api/videos");
  videos = data.videos;
  // Chỉ hỏi chi tiết cho video đang chạy hoặc video lỗi chưa biết nguyên nhân.
  const wanted = videos.filter((video) => ACTIVE.has(video.status) || (video.status === "FAILED" && !details.get(video.id)?.error));
  await Promise.all(wanted.map(async (video) => {
    const status = await api(`/api/videos/${video.id}/status`).catch(() => null);
    if (!status) return;
    video.status = status.status;
    details.set(video.id, { progress: status.progress_percent, error: status.error_code });
  }));
  render();
  const active = videos.some((video) => ACTIVE.has(video.status));
  $("live").hidden = !active;
  if (active) pollTimer = window.setTimeout(() => refresh().catch(() => {}), 2500);
}

function select(id, scroll = false) {
  selectedId = id;
  document.querySelectorAll("#videos .card").forEach((item, index) => item.classList.toggle("selected", videos[index]?.id === id));
  fillDetail();
  if (scroll) $("detail").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function fillDetail() {
  const video = videos.find((item) => item.id === selectedId);
  $("detail").hidden = !video;
  if (!video) return;
  const mine = video.owner_uid === user.uid;
  const info = details.get(video.id) || {};
  $("detail-title").textContent = video.title;
  const created = new Date(video.created_at).toLocaleString("vi-VN");
  const size = (video.size_bytes / 1_000_000).toFixed(1) + " MB";
  $("detail-meta").textContent = `${mine ? "Của bạn" : "Chia sẻ bởi " + video.owner_uid}, tải lên ${created}, file gốc ${size}`;
  const status = $("video-status");
  status.dataset.state = video.status;
  status.textContent = labels[video.status] || video.status;
  const bar = $("detail-progress");
  bar.hidden = !ACTIVE.has(video.status);
  bar.classList.toggle("busy", !(video.status === "PROCESSING" && Number.isInteger(info.progress)));
  bar.firstElementChild.style.width = Number.isInteger(info.progress) ? info.progress + "%" : "";
  let note = "";
  if (video.status === "PROCESSING") note = Number.isInteger(info.progress) ? `Đang chuyển mã: ${info.progress}%` : "Đang kiểm tra file.";
  else if (video.status === "QUEUED") note = "Đang chờ tới lượt. Máy chủ xử lý từng video một.";
  else if (video.status === "RETRYING") note = "Lần xử lý trước bị gián đoạn. Hệ thống đang thử lại.";
  else if (video.status === "FAILED") note = (failures[info.error] || "Máy chủ không xử lý được video này.") + " Hãy tải một file khác.";
  else if (video.status === "PENDING_UPLOAD") note = "File chưa được tải lên xong.";
  $("detail-note").textContent = note;
  $("play").disabled = video.status !== "READY";
  $("delete-video").hidden = !mine;
  $("permission-form").hidden = !mine;
}

$("refresh").addEventListener("click", async () => {
  try {
    await refresh();
    say("Thư viện đã cập nhật.");
  } catch (error) {
    say(error.message, true);
  }
});

$("play").addEventListener("click", () => {
  const video = videos.find((item) => item.id === selectedId);
  if (video) openPlayer(video);
});

$("delete-video").addEventListener("click", async () => {
  const video = videos.find((item) => item.id === selectedId);
  if (!video || !window.confirm(`Xoá vĩnh viễn video "${video.title}"?`)) return;
  try {
    await api(`/api/videos/${video.id}`, { method: "DELETE" });
    selectedId = null;
    thumbnails.delete(video.id);
    await refresh();
    say("Đã xoá video và các file liên quan.");
  } catch (error) {
    say(error.message, true);
  }
});

$("permission-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!selectedId) return;
  const action = event.submitter.value;
  const viewer = $("viewer").value.trim().toLowerCase();
  try {
    await api(`/api/videos/${selectedId}/permissions`, { method: "POST", body: JSON.stringify({ viewer_uid: viewer, action }) });
    say(action === "grant" ? `Đã cấp quyền xem cho ${viewer}.` : `Đã thu hồi quyền xem của ${viewer}.`);
  } catch (error) {
    say(error.message, true);
  }
});

// ---------- Trình phát ----------
let playing = null; // { video, issuedAt, renewing }
async function playbackUrl(video) {
  const data = await api(`/api/videos/${video.id}/playback`);
  playing = { video, issuedAt: Date.now(), renewing: false, duration: data.duration_ms };
  return data.url;
}

async function openPlayer(video) {
  const player = $("player");
  $("player-title").textContent = video.title;
  $("player-note").textContent = "Đang lấy liên kết phát…";
  $("player-modal").hidden = false;
  $("player-close").focus();
  try {
    const [url, poster] = await Promise.all([playbackUrl(video), thumbnailUrl(video).catch(() => "")]);
    if (poster) player.poster = poster;
    player.src = url;
    player.play().catch(() => {});
    const seconds = playing.duration == null ? "" : `Thời lượng ${(playing.duration / 1000).toFixed(1)} giây. `;
    $("player-note").textContent = seconds + "Liên kết phát tự gia hạn khi bạn xem lâu.";
  } catch (error) {
    $("player-note").textContent = error.message;
  }
}

// Liên kết phát chỉ sống 2 phút: xin liên kết mới và phát tiếp đúng vị trí đang xem.
async function renewPlayback() {
  if (!playing || playing.renewing || $("player-modal").hidden) return;
  playing.renewing = true;
  const player = $("player");
  const position = player.currentTime;
  const wasPaused = player.paused;
  try {
    const url = await playbackUrl(playing.video);
    player.src = url;
    player.addEventListener("loadedmetadata", () => {
      player.currentTime = position;
      if (!wasPaused) player.play().catch(() => {});
    }, { once: true });
  } catch (error) {
    $("player-note").textContent = error.message;
  }
}
function renewIfOld() {
  if (playing && !playing.renewing && Date.now() - playing.issuedAt > 100_000) renewPlayback();
}
$("player").addEventListener("error", () => { if (playing && Date.now() - playing.issuedAt > 5000) renewPlayback(); });
$("player").addEventListener("seeking", renewIfOld);
$("player").addEventListener("play", renewIfOld);

function closePlayer() {
  const player = $("player");
  playing = null;
  player.pause();
  player.removeAttribute("src");
  player.removeAttribute("poster");
  player.load();
  $("player-modal").hidden = true;
}
$("player-close").addEventListener("click", closePlayer);
$("player-modal").addEventListener("click", (event) => { if (event.target === $("player-modal")) closePlayer(); });
document.addEventListener("keydown", (event) => { if (event.key === "Escape" && !$("player-modal").hidden) closePlayer(); });

// ---------- Tải lên ----------
function track(step, failed = false) {
  const order = ["create", "send", "queue", "process", "ready"];
  const index = order.indexOf(step);
  $("tracker").hidden = false;
  document.querySelectorAll("#tracker li").forEach((item, position) => {
    item.className = position < index ? "done" : position === index ? (failed ? "failed" : step === "ready" ? "done" : "active") : "";
  });
}

// created.upload_method: "PUT" = gửi thẳng lên máy chủ của trang; "POST" = form ký sẵn gửi thẳng tới S3.
function sendFile(created, file, onProgress) {
  return new Promise((resolve, reject) => {
    const form = created.upload_method === "POST";
    const request = new XMLHttpRequest();
    request.open(form ? "POST" : "PUT", created.upload_url);
    request.upload.addEventListener("progress", (event) => { if (event.lengthComputable) onProgress(event.loaded / event.total); });
    request.addEventListener("load", () => {
      if (request.status === (form ? 204 : 201)) resolve();
      else if (request.status === 413 || request.responseText.includes("EntityTooLarge")) reject(new Error(errors.upload_too_large));
      else reject(new Error("Gửi file chưa hoàn tất. Hãy thử lại."));
    });
    request.addEventListener("error", () => reject(new Error("Mất kết nối khi đang gửi file. Hãy thử lại.")));
    if (form) {
      // S3 yêu cầu các trường đã ký đứng trước, file đứng cuối cùng.
      const body = new FormData();
      for (const [name, value] of Object.entries(created.upload_fields)) body.append(name, value);
      body.append("file", file);
      request.send(body);
    } else {
      request.setRequestHeader("Content-Type", file.type);
      request.send(file);
    }
  });
}

function showFile() {
  const file = $("file").files[0];
  $("file-name").textContent = file ? `${file.name} (${(file.size / 1_000_000).toFixed(1)} MB)` : "Kéo video vào đây hoặc bấm để chọn";
  if (file && !$("title").value.trim()) $("title").value = file.name.replace(/\.[^.]+$/, "").slice(0, 200);
}
$("file").addEventListener("change", showFile);
const dropzone = $("dropzone");
for (const name of ["dragenter", "dragover"]) dropzone.addEventListener(name, (event) => { event.preventDefault(); dropzone.classList.add("over"); });
for (const name of ["dragleave", "drop"]) dropzone.addEventListener(name, (event) => { event.preventDefault(); dropzone.classList.remove("over"); });
dropzone.addEventListener("drop", (event) => {
  if (event.dataTransfer.files.length) {
    $("file").files = event.dataTransfer.files;
    showFile();
  }
});

// Theo dõi video vừa tải lên cho tới khi xem được, ngay trên trang tải lên.
async function follow(videoId, title) {
  const note = $("upload-note");
  for (;;) {
    if (!user) return;
    const status = await api(`/api/videos/${videoId}/status`).catch(() => null);
    if (status) {
      details.set(videoId, { progress: status.progress_percent, error: status.error_code });
      if (status.status === "PROCESSING" || status.status === "RETRYING") {
        track("process");
        note.textContent = Number.isInteger(status.progress_percent) ? `Đang chuyển mã: ${status.progress_percent}%` : "Đang kiểm tra file.";
      } else if (status.status === "READY") {
        track("ready");
        note.textContent = "Video đã sẵn sàng. ";
        const watch = document.createElement("button");
        watch.type = "button";
        watch.className = "link";
        watch.textContent = "Xem ngay";
        watch.addEventListener("click", () => openPlayer({ id: videoId, title }));
        note.append(watch);
        say(`"${title}" đã sẵn sàng để xem.`);
        refresh().catch(() => {});
        return;
      } else if (status.status === "FAILED") {
        track("process", true);
        note.textContent = (failures[status.error_code] || "Máy chủ không xử lý được video này.") + " Hãy tải một file khác.";
        say(`"${title}" xử lý thất bại.`, true);
        refresh().catch(() => {});
        return;
      }
    }
    await new Promise((resolve) => window.setTimeout(resolve, 1500));
  }
}

$("upload-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = $("file").files[0];
  const title = $("title").value.trim();
  if (!file || !file.size || file.size > maxUploadBytes) {
    say(`Chọn video có dung lượng tối đa ${megabytes()} MB.`, true);
    return;
  }
  const bar = $("upload-progress");
  const note = $("upload-note");
  $("upload-button").disabled = true;
  bar.hidden = false;
  bar.firstElementChild.style.width = "0%";
  try {
    track("create");
    note.textContent = "Đang tạo lượt tải lên…";
    const created = await api("/api/videos", { method: "POST", body: JSON.stringify({ title, mime_type: file.type, size_bytes: file.size }) });
    track("send");
    await sendFile(created, file, (part) => {
      bar.firstElementChild.style.width = Math.round(part * 100) + "%";
      note.textContent = `Đang gửi file: ${Math.round(part * 100)}%`;
    });
    await api(`/api/videos/${created.video_id}/complete`, { method: "POST" });
    track("queue");
    note.textContent = "Đã gửi xong. Đang chờ tới lượt xử lý.";
    bar.hidden = true;
    event.target.reset();
    showFile();
    refresh().catch(() => {});
    follow(created.video_id, title);
  } catch (error) {
    bar.hidden = true;
    note.textContent = "";
    $("tracker").hidden = true;
    say(error.message, true);
  } finally {
    $("upload-button").disabled = false;
  }
});

// ---------- Quản lý người dùng (quản trị viên) ----------
async function loadUsers() {
  const data = await api("/api/users");
  const list = $("user-list");
  list.replaceChildren();
  for (const account of data.users) {
    const item = document.createElement("li");
    const name = document.createElement("div");
    name.className = "user-name";
    name.textContent = account.uid;
    const small = document.createElement("small");
    const facts = [account.admin ? "Quản trị viên" : "Người dùng", "tạo ngày " + new Date(account.created_at).toLocaleDateString("vi-VN")];
    if (!account.active) facts.push("đã vô hiệu hoá");
    if (account.locked) facts.push("đang bị khoá tạm vì đăng nhập sai");
    small.textContent = facts.join(", ");
    name.append(small);

    const reset = document.createElement("button");
    reset.type = "button";
    reset.className = "ghost small";
    reset.textContent = "Đặt lại mật khẩu";
    reset.addEventListener("click", () => {
      const field = document.createElement("input");
      field.type = "password";
      field.minLength = 12;
      field.placeholder = "Mật khẩu mới, ít nhất 12 ký tự";
      field.setAttribute("aria-label", "Mật khẩu mới cho " + account.uid);
      const save = document.createElement("button");
      save.type = "button";
      save.className = "small";
      save.textContent = "Lưu mật khẩu";
      save.addEventListener("click", async () => {
        try {
          await api("/api/users/password", { method: "POST", body: JSON.stringify({ email: account.uid, password: field.value }) });
          say(`Đã đặt lại mật khẩu cho ${account.uid}.`);
          await loadUsers();
        } catch (error) {
          say(error.message, true);
        }
      });
      reset.replaceWith(field, save);
      field.focus();
    });

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = account.active ? "danger small" : "ghost small";
    toggle.textContent = account.active ? "Vô hiệu hoá" : "Kích hoạt lại";
    toggle.disabled = account.uid === user.uid;
    toggle.addEventListener("click", async () => {
      try {
        await api("/api/users/active", { method: "POST", body: JSON.stringify({ email: account.uid, active: !account.active }) });
        say(account.active ? `Đã vô hiệu hoá ${account.uid}.` : `Đã kích hoạt lại ${account.uid}.`);
        await loadUsers();
      } catch (error) {
        say(error.message, true);
      }
    });
    item.append(name, reset, toggle);
    list.append(item);
  }
}

$("user-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const created = await api("/api/users", {
      method: "POST",
      body: JSON.stringify({ email: $("user-email").value.trim(), password: $("user-password").value, admin: $("user-admin").checked }),
    });
    event.target.reset();
    say(`Đã tạo tài khoản ${created.uid}.`);
    await loadUsers();
  } catch (error) {
    say(error.message, true);
  }
});

// ---------- Khởi động ----------
fetch("/api/config")
  .then((response) => response.json())
  .then((config) => {
    if (Number.isInteger(config.max_upload_bytes)) maxUploadBytes = config.max_upload_bytes;
    if (config.auth_provider) provider = config.auth_provider;
    $("file-hint").textContent = `Tối đa ${megabytes()} MB, dài không quá 30 giây.`;
    $("guide-limit").textContent = `Dung lượng tối đa ${megabytes()} MB.`;
    applyAuth();
  })
  .catch(() => {});
startStarfield();
applyAuth();
render();
route();
