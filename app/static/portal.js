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
  // Trang chi tiết cần một video đang chọn; gõ thẳng #watch hoặc video vừa bị xoá thì quay về Thư viện.
  if (view.id === "watch" && !videos.some((video) => video.id === selectedId)) {
    window.location.hash = "#library";
    return;
  }
  for (const item of views) item.hidden = item !== view;
  $("view-title").textContent = view.dataset.title;
  const section = view.id === "watch" ? "library" : view.id;
  document.querySelectorAll(".nav-link").forEach((link) => {
    const active = link.dataset.view === section;
    link.classList.toggle("active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  $("sidebar").classList.remove("open");
  $("menu-toggle").setAttribute("aria-expanded", "false");
  closeMenu();
  if (view.id !== "watch") closePlayer();
  if (user && ["home", "library", "watch"].includes(view.id)) refresh().catch((error) => say(error.message, true));
  if (view.id === "users" && user && user.admin) loadUsers().catch((error) => say(error.message, true));
  if (view.id === "watch") fillDetail();
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
  // Chưa đăng nhập thì chỉ hiện màn hình giới thiệu; không có dữ liệu hay khung trống nào của ứng dụng lộ ra.
  document.body.classList.toggle("guest", !user);
  $("password-form").hidden = !local;
  $("nav-users").hidden = !(user && user.admin && local);
  $("users-gate").hidden = Boolean(user && user.admin && local);
  $("users-body").hidden = !(user && user.admin && local);
  if (!user) return;
  $("identity").textContent = user.uid;
  $("role").textContent = user.admin ? "Quản trị viên" : "Người dùng";
  $("avatar").textContent = user.uid.slice(0, 1);
  $("profile-name").textContent = user.uid;
  $("profile-role").textContent = user.admin ? "Quản trị viên: quản lý được tài khoản và xem số liệu hệ thống." : "Người dùng: tải lên, xem và chia sẻ video của mình.";
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
  closeMenu();
  $("password").value = "";
  $("tracker-panel").hidden = true;
  $("search").value = "";
  searchText = "";
  render();
  applyAuth();
  // Lần đăng nhập sau bắt đầu lại ở Tổng quan.
  if (window.location.hash && window.location.hash !== "#home") window.location.hash = "#home";
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
    window.location.hash = "#home";
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

// ---------- Tổng quan, thư viện, chi tiết video ----------
let statusFilter = "all"; // all | ready | active | failed
let ownerFilter = "all"; // all | mine | shared
let viewMode = "grid"; // grid | list
let searchText = "";
let lastRender = "";
try {
  if (window.localStorage.getItem("video-portal-view") === "list") viewMode = "list";
} catch (error) {
  // Trình duyệt chặn localStorage: dùng kiểu lưới mặc định.
}

function clock(milliseconds) {
  const seconds = Math.round(milliseconds / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}
const sizeText = (bytes) => (bytes < 100_000 ? `${Math.max(1, Math.round(bytes / 1000))} KB` : (bytes / 1_000_000).toFixed(1).replace(".", ",") + " MB");
function dateText(iso) {
  const date = new Date(iso);
  const two = (value) => String(value).padStart(2, "0");
  return `${two(date.getDate())}/${two(date.getMonth() + 1)} ${two(date.getHours())}:${two(date.getMinutes())}`;
}
const ownerText = (video) => (video.owner_uid === user.uid ? "Của bạn" : "Chia sẻ bởi " + video.owner_uid);
const waiting = (video) => ACTIVE.has(video.status) || video.status === "PENDING_UPLOAD";

function stateText(video) {
  const percent = details.get(video.id)?.progress;
  return (labels[video.status] || video.status) + (video.status === "PROCESSING" && Number.isInteger(percent) ? ` ${percent}%` : "");
}

function setBadge(item, video) {
  item.className = "st";
  item.dataset.state = video.status;
  item.textContent = stateText(video);
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

function icon(name) {
  const space = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(space, "svg");
  const use = document.createElementNS(space, "use");
  use.setAttribute("href", "#i-" + name);
  svg.append(use);
  return svg;
}

// Lời gọi /thumbnail trả cả liên kết ảnh (sống 2 phút) lẫn thời lượng đã đo của video.
async function thumbnailInfo(video) {
  const cached = thumbnails.get(video.id);
  if (cached && Date.now() - cached.at < 100_000) return cached;
  const data = await api(`/api/videos/${video.id}/thumbnail`);
  const info = { url: data.url, duration: data.duration_ms, at: Date.now() };
  thumbnails.set(video.id, info);
  return info;
}
const thumbnailUrl = async (video) => (await thumbnailInfo(video)).url;

// Khung 16:9. Video sẵn sàng thì hiện ảnh thu nhỏ thật và thời lượng; chưa sẵn sàng thì hiện đúng trạng thái, không vẽ ảnh giả.
function thumb(video, onDuration) {
  const box = document.createElement("span");
  box.className = "thumb";
  box.dataset.state = video.status;
  if (video.status !== "READY") {
    const state = document.createElement("span");
    state.className = "state";
    state.textContent = stateText(video);
    box.append(state);
    return box;
  }
  const image = document.createElement("img");
  image.alt = "";
  image.addEventListener("error", () => image.remove());
  box.append(image);
  thumbnailInfo(video).then((info) => {
    image.src = info.url;
    if (info.duration == null) return;
    const length = document.createElement("span");
    length.className = "len";
    length.textContent = clock(info.duration);
    box.append(length);
    if (onDuration) onDuration(length.textContent);
  }).catch(() => image.remove());
  return box;
}

function visibleVideos() {
  return videos.filter((video) => {
    if (statusFilter === "ready" && video.status !== "READY") return false;
    if (statusFilter === "active" && !waiting(video)) return false;
    if (statusFilter === "failed" && video.status !== "FAILED") return false;
    if (ownerFilter === "mine" && video.owner_uid !== user.uid) return false;
    if (ownerFilter === "shared" && video.owner_uid === user.uid) return false;
    return !searchText || video.title.toLowerCase().includes(searchText);
  });
}

// Mở trang chi tiết của một video; video sẵn sàng thì phát luôn.
let wantPlay = false;
function select(id) {
  selectedId = id;
  wantPlay = true;
  if (window.location.hash !== "#watch") window.location.hash = "#watch";
  else route();
}

// ----- Menu thao tác của từng video -----
function closeMenu() {
  $("item-menu").hidden = true;
  $("item-menu").replaceChildren();
}

function openMenu(video, anchor) {
  const menu = $("item-menu");
  const entry = (text, action, danger = false) => {
    const item = document.createElement("button");
    item.type = "button";
    item.setAttribute("role", "menuitem");
    if (danger) item.className = "danger";
    item.textContent = text;
    item.addEventListener("click", () => { closeMenu(); action(); });
    return item;
  };
  const entries = [entry(video.status === "READY" ? "Xem video" : "Xem trạng thái", () => select(video.id))];
  if (video.owner_uid === user.uid) {
    entries.push(entry("Chia sẻ", () => { select(video.id); window.setTimeout(() => $("viewer").focus(), 250); }));
    entries.push(entry("Xoá video", () => removeVideo(video), true));
  }
  menu.replaceChildren(...entries);
  menu.hidden = false;
  const box = anchor.getBoundingClientRect();
  menu.style.top = Math.max(8, Math.min(box.bottom + 4, window.innerHeight - menu.offsetHeight - 8)) + "px";
  menu.style.left = Math.max(8, Math.min(box.right - menu.offsetWidth, window.innerWidth - menu.offsetWidth - 8)) + "px";
  entries[0].focus();
}
document.addEventListener("click", (event) => { if (!$("item-menu").hidden && !event.target.closest("#item-menu, .more")) closeMenu(); });
document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeMenu(); });
window.addEventListener("scroll", closeMenu, { passive: true });

function moreButton(video) {
  const more = document.createElement("button");
  more.type = "button";
  more.className = "more";
  more.setAttribute("aria-label", "Thao tác với video " + video.title);
  more.setAttribute("aria-haspopup", "menu");
  more.append(icon("more"));
  more.addEventListener("click", (event) => {
    event.stopPropagation();
    if ($("item-menu").hidden) openMenu(video, more);
    else closeMenu();
  });
  return more;
}

async function removeVideo(video) {
  if (!window.confirm(`Xoá vĩnh viễn video "${video.title}"?`)) return;
  try {
    await api(`/api/videos/${video.id}`, { method: "DELETE" });
    thumbnails.delete(video.id);
    if (selectedId === video.id) selectedId = null;
    await refresh();
    if (window.location.hash === "#watch") window.location.hash = "#library";
    say("Đã xoá video và các file liên quan.");
  } catch (error) {
    say(error.message, true);
  }
}

// ----- Thẻ video (lưới) và dòng video (danh sách) -----
function mediaCard(video, featured = false) {
  const item = document.createElement("article");
  item.className = "media" + (featured ? " featured" : "");
  const open = document.createElement("button");
  open.type = "button";
  open.className = "thumb-button";
  open.setAttribute("aria-label", (video.status === "READY" ? "Xem video " : "Xem trạng thái video ") + video.title);
  open.append(thumb(video));
  open.addEventListener("click", () => select(video.id));
  const foot = document.createElement("div");
  foot.className = "media-foot";
  const title = document.createElement("strong");
  title.className = "media-title";
  title.textContent = video.title;
  const meta = document.createElement("span");
  meta.className = "media-meta";
  meta.textContent = `${ownerText(video)}, ${dateText(video.created_at)}`;
  foot.append(title, moreButton(video), meta);
  if (ACTIVE.has(video.status)) foot.append(progressBar(video));
  item.append(open, foot);
  return item;
}

function row(video) {
  const line = document.createElement("tr");
  const cell = (...children) => { const item = document.createElement("td"); item.append(...children); line.append(item); return item; };
  const duration = document.createElement("span");
  duration.textContent = "–";
  const picture = document.createElement("button");
  picture.type = "button";
  picture.className = "thumb-button";
  picture.setAttribute("aria-label", (video.status === "READY" ? "Xem video " : "Xem trạng thái video ") + video.title);
  picture.append(thumb(video, (value) => { duration.textContent = value; }));
  const text = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = video.title;
  const owner = document.createElement("small");
  owner.textContent = ownerText(video);
  text.append(title, owner);
  const name = document.createElement("div");
  name.className = "name";
  name.append(picture, text);
  cell(name);
  const state = cell(setBadge(document.createElement("span"), video));
  if (ACTIVE.has(video.status)) state.append(progressBar(video));
  cell(duration);
  cell(sizeText(video.size_bytes));
  cell(dateText(video.created_at));
  cell(moreButton(video));
  line.addEventListener("click", () => select(video.id));
  return line;
}

// ----- Tổng quan -----
function fillRunning(list) {
  const items = list.slice(0, 4).map((video) => {
    const item = document.createElement("li");
    const open = document.createElement("button");
    open.type = "button";
    open.className = "link";
    open.textContent = video.title;
    open.addEventListener("click", () => select(video.id));
    item.append(open, setBadge(document.createElement("span"), video));
    if (ACTIVE.has(video.status)) item.append(progressBar(video));
    return item;
  });
  const note = document.createElement("li");
  note.className = "idle";
  if (!list.length) note.textContent = "Không có video nào đang xử lý. Video mới tải lên sẽ hiện ở đây cùng tiến độ đo được.";
  else if (list.length > 4) note.textContent = `và ${list.length - 4} video khác đang chờ`;
  if (note.textContent) items.push(note);
  $("running").replaceChildren(...items);
}

function fillRows(id, list, emptyText, describe) {
  const items = list.slice(0, 5).map((video) => {
    const item = document.createElement("li");
    const text = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = video.title;
    const note = document.createElement("small");
    note.textContent = describe(video);
    text.append(title, note);
    const open = document.createElement("button");
    open.type = "button";
    open.className = "link";
    open.textContent = "Mở";
    open.setAttribute("aria-label", "Mở video " + video.title);
    open.addEventListener("click", () => select(video.id));
    item.append(thumb(video), text, open);
    return item;
  });
  if (!items.length) {
    const none = document.createElement("li");
    none.className = "none";
    none.textContent = emptyText;
    items.push(none);
  }
  $(id).replaceChildren(...items);
}

function fillDashboard() {
  const stages = {
    pending: videos.filter((video) => video.status === "PENDING_UPLOAD").length,
    queued: videos.filter((video) => video.status === "QUEUED" || video.status === "RETRYING").length,
    processing: videos.filter((video) => video.status === "PROCESSING").length,
    ready: videos.filter((video) => video.status === "READY").length,
  };
  for (const [name, total] of Object.entries(stages)) {
    $("count-" + name).textContent = total;
    document.querySelector(`.stages [data-stage="${name}"]`).classList.toggle("has", total > 0);
  }
  fillRunning(videos.filter(waiting));
  $("live-home").hidden = !videos.some((video) => ACTIVE.has(video.status));

  // Video gần đây: API trả video mới nhất trước; ô đầu tiên được phóng to.
  const recent = videos.slice(0, 5).map((video, index) => mediaCard(video, index === 0 && videos.length > 2));
  if (!recent.length) {
    const none = document.createElement("p");
    none.className = "hint";
    none.textContent = "Chưa có video nào. Bấm Tải video lên để bắt đầu.";
    recent.push(none);
  }
  $("recent").replaceChildren(...recent);
  fillRows("attention", videos.filter((video) => video.status === "FAILED"), "Không có video nào cần bạn xử lý.",
    (video) => (failures[details.get(video.id)?.error] || "Máy chủ không xử lý được video này.") + " Hãy tải một file khác.");
  fillRows("shared", videos.filter((video) => video.owner_uid !== user.uid), "Chưa ai chia sẻ video cho bạn.", ownerText);
}

function render() {
  if (!user) {
    lastRender = "";
    for (const id of ["recent", "running", "attention", "shared", "video-grid", "videos"]) $(id).replaceChildren();
    return;
  }
  const count = (matches) => videos.filter(matches).length;
  $("stat-total").textContent = videos.length;
  $("stat-ready").textContent = count((video) => video.status === "READY");
  $("stat-active").textContent = count(waiting);
  $("stat-failed").textContent = count((video) => video.status === "FAILED");
  $("nav-count").hidden = !videos.length;
  $("nav-count").textContent = videos.length;
  $("library-empty").hidden = videos.length > 0;
  $("library-body").hidden = !videos.length;
  // Chỉ dựng lại khi dữ liệu thật sự đổi: tránh tải lại ảnh thu nhỏ mỗi lần trang tự hỏi trạng thái.
  const signature = JSON.stringify([statusFilter, ownerFilter, viewMode, searchText, videos.map((video) => [video.id, video.status, video.title, details.get(video.id)])]);
  if (signature !== lastRender) {
    lastRender = signature;
    const shown = visibleVideos();
    $("video-grid").hidden = viewMode !== "grid" || !shown.length;
    $("video-list").hidden = viewMode !== "list" || !shown.length;
    $("no-match").hidden = shown.length > 0;
    $("video-grid").replaceChildren(...(viewMode === "grid" ? shown.map((video) => mediaCard(video)) : []));
    $("videos").replaceChildren(...(viewMode === "list" ? shown.map(row) : []));
    const totals = { all: videos.length, ready: count((video) => video.status === "READY"), active: count(waiting), failed: count((video) => video.status === "FAILED") };
    for (const button of $("status-filter").children) {
      button.textContent = `${button.dataset.label} ${totals[button.dataset.filter]}`;
      button.classList.toggle("on", button.dataset.filter === statusFilter);
    }
    for (const button of $("owner-filter").children) button.classList.toggle("on", button.dataset.owner === ownerFilter);
    for (const button of $("view-mode").children) {
      button.classList.toggle("on", button.dataset.mode === viewMode);
      button.setAttribute("aria-pressed", String(button.dataset.mode === viewMode));
    }
    fillDashboard();
  }
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

// ----- Chi tiết video -----
function markSteps(list, step, failed = false) {
  const items = [...list.children];
  const index = items.findIndex((item) => item.dataset.step === step);
  items.forEach((item, position) => {
    item.className = position < index ? "done" : position === index ? (failed ? "failed" : step === "ready" ? "done" : "active") : "";
  });
}

let playerFor = null; // id của video đang nằm trong trình phát
function fillDetail() {
  if ($("watch").hidden) return;
  const video = user && videos.find((item) => item.id === selectedId);
  if (!video) {
    window.location.hash = "#library";
    return;
  }
  const mine = video.owner_uid === user.uid;
  const info = details.get(video.id) || {};
  $("detail-title").textContent = video.title;
  setBadge($("video-status"), video);
  setBadge($("stage-state"), video);
  $("detail-owner").textContent = mine ? "Bạn" : video.owner_uid;
  $("detail-size").textContent = sizeText(video.size_bytes);
  $("detail-created").textContent = new Date(video.created_at).toLocaleString("vi-VN");
  const step = { PENDING_UPLOAD: "send", QUEUED: "queue", RETRYING: "process", PROCESSING: "process", READY: "ready", FAILED: "process" }[video.status];
  markSteps($("detail-steps"), step, video.status === "FAILED");
  const bar = $("detail-progress");
  bar.hidden = !ACTIVE.has(video.status);
  bar.classList.toggle("busy", !(video.status === "PROCESSING" && Number.isInteger(info.progress)));
  bar.firstElementChild.style.width = Number.isInteger(info.progress) ? info.progress + "%" : "";
  let note = "";
  if (video.status === "PROCESSING") note = Number.isInteger(info.progress) ? `Đang chuyển mã: ${info.progress}%.` : "Đang kiểm tra file.";
  else if (video.status === "QUEUED") note = "Đang chờ tới lượt. Máy chủ xử lý từng video một.";
  else if (video.status === "RETRYING") note = "Lần xử lý trước bị gián đoạn. Hệ thống đang thử lại.";
  else if (video.status === "FAILED") note = (failures[info.error] || "Máy chủ không xử lý được video này.") + " Hãy tải một file khác.";
  else if (video.status === "PENDING_UPLOAD") note = "File chưa được tải lên xong.";
  $("detail-note").textContent = note;
  $("detail-note").hidden = !note;
  $("stage-text").textContent = note;
  $("delete-video").hidden = !mine;
  $("permission-form").hidden = !mine;
  if (video.status === "READY") {
    $("stage-wait").hidden = true;
    if (playerFor !== video.id) {
      playerFor = video.id;
      $("detail-duration").textContent = "–";
      loadPlayer(video, wantPlay);
    }
  } else {
    if (playerFor) closePlayer();
    $("stage-wait").hidden = false;
    $("detail-duration").textContent = "Chưa có";
    $("player-note").textContent = "";
  }
  wantPlay = false;
}

$("status-filter").addEventListener("click", (event) => {
  if (!event.target.dataset.filter) return;
  statusFilter = event.target.dataset.filter;
  render();
});
$("owner-filter").addEventListener("click", (event) => {
  if (!event.target.dataset.owner) return;
  ownerFilter = event.target.dataset.owner;
  render();
});
$("view-mode").addEventListener("click", (event) => {
  const button = event.target.closest("[data-mode]");
  if (!button) return;
  viewMode = button.dataset.mode;
  try {
    window.localStorage.setItem("video-portal-view", viewMode);
  } catch (error) {
    // Không lưu được lựa chọn: vẫn đổi kiểu hiển thị cho lần xem này.
  }
  render();
});
$("search").addEventListener("input", () => {
  searchText = $("search").value.trim().toLowerCase();
  if (user && window.location.hash !== "#library") window.location.hash = "#library";
  render();
});

$("refresh").addEventListener("click", async () => {
  try {
    await refresh();
    say("Thư viện đã cập nhật.");
  } catch (error) {
    say(error.message, true);
  }
});

$("delete-video").addEventListener("click", () => {
  const video = videos.find((item) => item.id === selectedId);
  if (video) removeVideo(video);
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

// ---------- Trình phát (nằm ngay trong trang chi tiết) ----------
let playing = null; // { video, issuedAt, renewing, duration }
async function playbackUrl(video) {
  const data = await api(`/api/videos/${video.id}/playback`);
  playing = { video, issuedAt: Date.now(), renewing: false, duration: data.duration_ms };
  return data.url;
}

async function loadPlayer(video, start) {
  const player = $("player");
  $("player-box").hidden = false;
  $("player-note").textContent = "Đang lấy liên kết phát…";
  try {
    const [url, poster] = await Promise.all([playbackUrl(video), thumbnailUrl(video).catch(() => "")]);
    if (playerFor !== video.id) return; // người dùng đã chuyển sang video khác trong lúc chờ
    if (poster) player.poster = poster;
    player.src = url;
    if (start) player.play().catch(() => {});
    if (playing.duration != null) $("detail-duration").textContent = clock(playing.duration);
    $("player-note").textContent = "Liên kết phát chỉ sống 2 phút và tự gia hạn khi bạn xem lâu.";
  } catch (error) {
    $("player-note").textContent = error.message;
  }
}

// Liên kết phát chỉ sống 2 phút: xin liên kết mới và phát tiếp đúng vị trí đang xem.
async function renewPlayback() {
  if (!playing || playing.renewing || $("watch").hidden) return;
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
  playerFor = null;
  player.pause();
  player.removeAttribute("src");
  player.removeAttribute("poster");
  player.load();
  $("player-box").hidden = true;
}

// ---------- Tải lên ----------
function track(step, failed = false) {
  $("tracker-panel").hidden = false;
  markSteps($("tracker"), step, failed);
}

// Hai pha có số đo riêng: "upload" đo bằng số byte trình duyệt đã gửi, "transcode" đo bằng phần trăm FFmpeg báo về.
function setPhase(name, state, figure, percent = null) {
  $("phase-" + name).dataset.state = state; // wait | active | done | failed
  $(name + "-figure").textContent = figure;
  const bar = $(name + "-progress");
  bar.classList.toggle("busy", state === "active" && percent === null);
  bar.firstElementChild.style.width = state === "done" ? "100%" : percent === null ? "" : percent + "%";
}

// created.upload_method: "PUT" = gửi thẳng lên máy chủ của trang; "POST" = form ký sẵn gửi thẳng tới S3.
function sendFile(created, file, onProgress) {
  return new Promise((resolve, reject) => {
    const form = created.upload_method === "POST";
    const request = new XMLHttpRequest();
    request.open(form ? "POST" : "PUT", created.upload_url);
    request.upload.addEventListener("progress", (event) => { if (event.lengthComputable) onProgress(event.loaded, event.total); });
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

const typeNames = { "video/mp4": "MP4", "video/webm": "WebM", "video/quicktime": "MOV" };
function showFile() {
  const file = $("file").files[0];
  $("file-card").hidden = !file;
  $("dropzone").classList.toggle("compact", Boolean(file));
  if (!file) return;
  $("file-name").textContent = file.name;
  $("file-size").textContent = sizeText(file.size);
  $("file-type").textContent = typeNames[file.type] || "định dạng không được hỗ trợ";
  let problem = "";
  if (!typeNames[file.type]) problem = "Chỉ nhận video MP4, WebM hoặc MOV.";
  else if (file.size > maxUploadBytes) problem = `File lớn hơn giới hạn ${megabytes()} MB.`;
  $("file-warning").textContent = problem;
  $("file-warning").hidden = !problem;
  if (!$("title").value.trim()) $("title").value = file.name.replace(/\.[^.]+$/, "").slice(0, 200);
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
      if (status.status === "QUEUED") {
        track("queue");
        setPhase("transcode", "active", "Đang xếp hàng");
      } else if (status.status === "PROCESSING" || status.status === "RETRYING") {
        const percent = Number.isInteger(status.progress_percent) ? status.progress_percent : null;
        track("process");
        setPhase("transcode", "active", status.status === "RETRYING" ? "Đang thử lại" : percent === null ? "Đang kiểm tra file" : `${percent}%`, percent);
        note.textContent = "Máy chủ đang chuyển mã. Bạn có thể rời trang; video sẽ có trong Thư viện khi xong.";
      } else if (status.status === "READY") {
        track("ready");
        setPhase("transcode", "done", "Hoàn tất");
        note.textContent = "Video đã sẵn sàng. ";
        const watch = document.createElement("button");
        watch.type = "button";
        watch.className = "link";
        watch.textContent = "Xem ngay";
        watch.addEventListener("click", () => refresh().catch(() => {}).then(() => select(videoId)));
        note.append(watch);
        say(`"${title}" đã sẵn sàng để xem.`);
        refresh().catch(() => {});
        return;
      } else if (status.status === "FAILED") {
        track("process", true);
        setPhase("transcode", "failed", "Thất bại");
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
  const note = $("upload-note");
  $("upload-button").disabled = true;
  $("tracker-title").textContent = title;
  note.textContent = "";
  try {
    track("create");
    setPhase("upload", "active", "Đang chuẩn bị", 0);
    setPhase("transcode", "wait", "Chưa bắt đầu", 0);
    const created = await api("/api/videos", { method: "POST", body: JSON.stringify({ title, mime_type: file.type, size_bytes: file.size }) });
    track("send");
    await sendFile(created, file, (loaded, total) => {
      const percent = Math.round((loaded / total) * 100);
      setPhase("upload", "active", `${sizeText(loaded)} / ${sizeText(total)}, ${percent}%`, percent);
    });
    setPhase("upload", "done", `Đã gửi ${sizeText(file.size)}`);
    await api(`/api/videos/${created.video_id}/complete`, { method: "POST" });
    track("queue");
    setPhase("transcode", "active", "Đang xếp hàng");
    note.textContent = "Đã gửi xong. Đang chờ tới lượt xử lý.";
    event.target.reset();
    showFile();
    refresh().catch(() => {});
    follow(created.video_id, title);
  } catch (error) {
    // Lỗi trước khi vào hàng đợi: báo ngay tại pha gửi file, không để thanh tiến độ treo.
    setPhase("upload", "failed", "Không gửi được", 0);
    note.textContent = error.message;
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
    $("file-hint").textContent = `MP4, WebM hoặc MOV. Tối đa ${megabytes()} MB, dài không quá 30 giây.`;
    $("welcome-limit").textContent = `${megabytes()} MB, 30 giây`;
    $("guide-limit").textContent = `Dung lượng tối đa ${megabytes()} MB.`;
    applyAuth();
  })
  .catch(() => {});
applyAuth();
render();
route();
