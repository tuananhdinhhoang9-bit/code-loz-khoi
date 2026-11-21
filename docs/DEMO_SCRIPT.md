# Kịch bản thuyết trình 10–15 phút

Viết ngày 2026-11-21 cho bản Azure. Kịch bản dài 13 phút 45 giây, còn khoảng 1 phút dự phòng. **Chưa tập trọn kịch bản lần nào**: các con số thời gian bên dưới lấy từ những lần chạy riêng lẻ ghi trong `docs/EVIDENCE.md`. Dòng có chữ "CHƯA CÓ:" là việc còn thiếu, phải sửa lại khi làm xong.

Trang: `https://videoportal-api.bravecoast-ef9b0b40.malaysiawest.azurecontainerapps.io`

## Bốn điều phải nhớ

1. **Hệ thống chuyển mã mỗi lúc một video**, và mỗi video mất khoảng 25 giây để khởi động container. Trong buổi demo chỉ tải lên **từng clip một**, chờ clip trước `READY` rồi mới tải clip sau. Không ai khác được tải lên trong lúc demo.
2. **Diễn tập ngắt lỗi:** lần đo ngày 2026-11-21 phục hồi sau 60 giây, nhưng trường hợp xấu nhất lâu hơn khoảng 5 phút (job bảo trì chạy 5 phút một lần). Vì vậy phần giám sát được nói **trong lúc chờ**.
3. **Mật khẩu do người trình bày tự gõ** vào trang hoặc vào dấu nhắc `Password:` của script. Không ghi mật khẩu vào tài liệu, slide, lệnh hay biến môi trường trên màn hình chiếu.
4. Chỗ nào hỏng thì nói thẳng là hỏng và mở bằng chứng đã ghi trong `docs/EVIDENCE.md`. Không nói một việc "đã chạy" nếu nó chưa chạy.

## Bảng thời gian

| # | Phần | Thời lượng | Bắt đầu lúc |
| --- | --- | --- | --- |
| 0 | Mở đầu: bài toán, sơ đồ | 0:45 | 0:00 |
| 1 | Luồng người dùng chuẩn | 2:15 | 0:45 |
| 2 | Kiểm thử bảo mật | 2:45 | 3:00 |
| 3 | Diễn tập ngắt lỗi: khởi động | 1:00 | 5:45 |
| 4 | Giám sát (nói trong lúc chờ phục hồi) | 2:30 | 6:45 |
| 5 | Diễn tập ngắt lỗi: kết quả | 0:45 | 9:15 |
| 6 | CI/CD và rollback | 2:00 | 10:00 |
| 7 | Chi phí và dọn dẹp (một slide, nói trong lúc rollback chạy) | 1:00 | 12:00 |
| 8 | Hạn chế, kết | 0:45 | 13:00 |
| | **Tổng** | **13:45** | |

## Chuẩn bị trước buổi demo

Trước một ngày:

- [ ] CHƯA CÓ: hai tài khoản demo **Owner** và **Viewer** (tài khoản thường, không phải quản trị). Quản trị viên tạo trong trang: **Quản lý người dùng > Tạo tài khoản mới** (email, mật khẩu ít nhất 12 ký tự, không tích "Cho quyền quản trị viên"). Mật khẩu gửi riêng cho thầy, không ghi vào repo.
- [ ] CHƯA CÓ: sự đồng ý của thầy về việc đăng nhập bằng tài khoản nội bộ thay cho Entra External ID. Nếu chưa hỏi được thì nêu ở phần 8 như một điểm lệch đã biết.
- [x] Diễn tập sau khi alert rule được tạo: đã chạy ngày 2026-11-21, cảnh báo nổ 3 phút 19 giây sau khi job bị dừng (`docs/EVIDENCE.md`, mục "alert fired"). Email thông báo: chủ dự án tự kiểm tra hộp thư trước buổi demo.
- [ ] Chuẩn bị hai file video trên máy trình bày:
  - một clip ngắn hợp lệ cho phần 1 (ví dụ một trong mười clip mẫu 1–3 giây: `.\.venv\Scripts\python.exe -m app.seed_media --output-dir .local\seed`);
  - một clip nặng cho phần 3: hai lần đo trước dùng clip 1080p dài 29 giây, 29,2 MB, hiện nằm ở `.local\drill-1080p.mp4` (thư mục `.local` không commit). Tạo lại bằng FFmpeg nếu mất: `ffmpeg -f lavfi -i "testsrc2=size=1920x1080:rate=30" -f lavfi -i "sine=frequency=440" -t 29 -c:v libx264 -preset ultrafast -b:v 8M -maxrate 9M -bufsize 16M -pix_fmt yuv420p -c:a aac drill-1080p.mp4`. Clip phải không quá 30 giây và 50 MB, và đủ nặng để worker chạy hơn mười giây; nếu nhẹ quá thì job xong trước khi kịp dừng và script báo FAIL. Thay `CLIP_NANG.mp4` ở lệnh phần 3 bằng đường dẫn này.
- [ ] Bằng tài khoản Owner, tải sẵn một clip dự phòng và chờ nó `READY`, để thư viện của Owner luôn có một video xem được nếu lượt tải trực tiếp ở phần 1 trục trặc. (Mười clip mẫu hiện nằm trong thư viện của quản trị viên, không phải của Owner.)
- [ ] Tập thử phần 2 (lấy URL của blob) ít nhất một lần.
- [ ] Ghi sẵn hai SHA đầy đủ (40 ký tự) cho phần 6: commit **đang chạy** và commit **ngay trước đó** còn tốt. Xem image đang chạy (cần đã `az login` và có `az` trên PATH, xem bên dưới):
  ```powershell
  az containerapp show --name videoportal-api --resource-group videoportal-rg --query "properties.template.containers[0].image" -o tsv
  ```
  Xem các SHA gần đây: `git log -5 --format=%H` hoặc trang Actions của kho GitHub. Tag dùng để rollback phải là một image đã có trong registry (commit đã từng qua job `images`).

Trước buổi demo 30 phút:

- [ ] Không push lên `main` nữa: mỗi lần push là một lần deploy (khoảng 5 phút) và đổi image của cả hai job.
- [ ] Mở PowerShell tại thư mục gốc của repo, đặt biến cho gọn và kiểm tra trang:
  ```powershell
  $site = "https://videoportal-api.bravecoast-ef9b0b40.malaysiawest.azurecontainerapps.io"
  curl.exe -s "$site/health"
  ```
  Phải thấy `{"database":"ok","status":"ok"}`.
- [ ] Chủ dự án tự đăng nhập Azure CLI (phiên cũ có thể đã hết hạn) và đưa `az` vào PATH:
  ```powershell
  & .\.tools\azcli\bin\az.cmd login --use-device-code
  $env:PATH = "$PWD\.tools\azcli\bin;" + $env:PATH
  powershell -File scripts\azure\Stop-TranscodeExecution.ps1
  ```
  Lệnh cuối chỉ liệt kê. Khi không có video nào đang xử lý, nó in `no Running execution of videoportal-transcode`: nghĩa là đăng nhập dùng được và hệ thống đang rảnh.
- [ ] Mở sẵn các cửa sổ, đăng nhập sẵn những chỗ không cần cho khán giả xem:
  - cửa sổ A (trình duyệt thường): trang portal, chưa đăng nhập;
  - cửa sổ B (InPrivate/ẩn danh): trang portal, chưa đăng nhập;
  - tab Azure Portal: **Monitor > Workbooks > Video Portal** (hoặc Log Analytics workspace `videoportal-logs` > Workbooks);
  - tab Azure Portal: **Monitor > Alerts > Alert rules**;
  - tab GitHub: **Actions** của kho, đã đăng nhập bằng tài khoản có quyền chạy workflow;
  - `docs/EVIDENCE.md` mở sẵn để dùng khi có bước hỏng.
- [ ] Thư viện của Owner không có video nào đang chờ hoặc đang xử lý.
- [ ] Xem số dư credit trong Azure Portal (chưa có lệnh đọc số này; số dư thật chưa từng được ghi lại).

## Kịch bản

### 0. Mở đầu (0:45)

- **Làm:** chiếu sơ đồ trong `docs/AZURE_ARCHITECTURE.md`.
- **Nói:** "Portal cho tải lên video ngắn, chuyển mã trong container thành MP4 480p, và chỉ người được cấp quyền mới xem được. Mọi thứ chạy trên Azure ở Malaysia West và được dựng bằng Terraform; mỗi video được xử lý bởi một lần chạy job riêng."

### 1. Luồng người dùng chuẩn (2:15)

- **Làm, ở cửa sổ A:**
  1. Gõ email của Owner và `<mật khẩu do người trình bày tự gõ>`, bấm **Đăng nhập**.
  2. Bấm **Tải video lên** ở thanh bên, chọn clip ngắn, đặt tên (ví dụ "Demo lớp"), bấm nút **Tải video lên**.
  3. Chỉ vào hai thanh tiến độ: "1. Gửi file lên máy chủ" rồi "2. Chuyển mã trên máy chủ".
  4. Khi hiện "Video đã sẵn sàng", bấm **Xem ngay** và cho phát vài giây.
- **Nói trong lúc chờ (khoảng 40 giây; lần đo thật là 38,5 giây):** "Trình duyệt gửi file thẳng vào Blob Storage bằng một liên kết ký sống hai phút, không qua API. Khi tôi bấm xong, API ghi video, job và một sự kiện vào database trong cùng một giao dịch rồi mới gửi message sang Service Bus. Azure thấy message và khởi động một container chỉ để xử lý video này; khoảng 25 giây đầu là thời gian khởi động container, không phải thời gian chuyển mã."
- **Khán giả thấy:** trạng thái đi từ xếp hàng sang chuyển mã (phần trăm là số FFmpeg báo về) rồi sẵn sàng; video phát được.
- **Nếu hỏng:**
  - Quá 2 phút chưa `READY`: nói rõ là đang chờ, làm phần 2 bằng clip dự phòng đã tải sẵn trong thư viện của Owner, quay lại sau. Chưa chạy phần 3 khi clip này chưa xong.
  - Không tải lên được: mở `docs/EVIDENCE.md`, mục "first real upload, transcode and playback" (lượt tải thật 12:46 UTC, `READY` sau 38,5 giây).

### 2. Kiểm thử bảo mật (2:45)

Dùng video vừa tải ở phần 1.

**a. Người dùng thứ hai không thấy video (0:40)**

- **Làm:** ở cửa sổ B, đăng nhập bằng tài khoản Viewer (`<mật khẩu do người trình bày tự gõ>`), mở **Thư viện**.
- **Nói:** "Viewer là một tài khoản hợp lệ nhưng chưa được cấp quyền, nên video của Owner không có trong danh sách; gọi thẳng API tới video đó cũng nhận 404."

**b. Gọi API không có token (0:20)**

- **Làm, trong PowerShell:**
  ```powershell
  curl.exe -s -i "$site/api/videos"
  ```
- **Khán giả thấy:** dòng đầu có mã **401**.
- **Nói:** "Không đăng nhập thì API không trả gì, kể cả danh sách."

**c. URL lưu trữ không có chữ ký (0:50)**

- **Làm:**
  1. Ở cửa sổ A, đang ở trang chi tiết của video: bấm chuột phải vào trình phát, chọn "Copy video address" (hoặc F12 > Network > request `playback` > trường `url`).
  2. Dán vào một tab mới nhưng **xoá hết từ dấu `?` trở đi** rồi Enter. Hoặc trong PowerShell:
     ```powershell
     curl.exe -s -o NUL -w "%{http_code}`n" "URL_ĐÃ_XOÁ_TỪ_DẤU_HỎI"
     ```
- **Khán giả thấy:** Blob Storage trả lỗi, mã **409** (tài khoản lưu trữ cấm truy cập công khai). Nếu còn giây: giữ nguyên URL nhưng đổi vài ký tự cuối của chữ ký thì được **403**.
- **Nói:** "File nằm trong kho riêng tư. Chỉ liên kết do API ký sau khi kiểm tra quyền mới đọc được, và liên kết đó hết hạn sau hai phút."
- **Lưu ý:** URL đầy đủ có chữ ký còn dùng được trong 120 giây. Không dán nó vào slide, tin nhắn hay tài liệu.

**d. Chia sẻ rồi thu hồi (0:55)**

- **Làm:**
  1. Cửa sổ A, trang chi tiết video, khung **Chia sẻ**: gõ email của Viewer, bấm **Cấp quyền xem**.
  2. Cửa sổ B: bấm **Làm mới** trong Thư viện (hoặc chọn lọc **Được chia sẻ**), mở video, cho phát.
  3. Cửa sổ A: gõ lại email của Viewer, bấm **Thu hồi quyền**.
  4. Cửa sổ B: bấm **Làm mới**; video biến mất.
- **Nói:** "Quyền được kiểm tra ở API mỗi lần xin liên kết. Thu hồi có hiệu lực ngay với lượt xem mới; một liên kết đã cấp còn sống tối đa hai phút, đó là giới hạn chúng em chấp nhận và có ghi trong tài liệu bảo mật."
- **Nếu bất kỳ bước nào của phần 2 hỏng:** mở `docs/EVIDENCE.md`, mục "instructor's Tests 1–3", dòng Test 3b: 11/11 PASS trên Azure (không token 401, token giả 401, URL không SAS 409, sửa chữ ký 403, người dùng thứ hai 404, cấp quyền thì xem được, thu hồi thì 404).

### 3. Diễn tập ngắt lỗi: khởi động (1:00)

Chỉ bắt đầu khi video ở phần 1 đã `READY` và không còn gì trong hàng đợi.

- **Làm, trong PowerShell (thay `EMAIL` bằng email của Owner; mật khẩu gõ vào dấu nhắc `Password:`):**
  ```powershell
  .\.venv\Scripts\python.exe scripts\failure_drill.py --base-url $site --email EMAIL --clip CLIP_NANG.mp4 --on-processing "powershell -File scripts\azure\Stop-TranscodeExecution.ps1 -Apply"
  ```
  Nếu `az` không có trên PATH, thêm `-AzPython .tools\azcli\python.exe` vào trước `-Apply`.
- **Nói:** "Script tải một clip nặng lên, chờ tới khi trang báo FFmpeg đang chạy thật, rồi dừng chính lần chạy job đó trên Azure bằng `az containerapp job stop`. Sau đó nó chỉ quan sát."
- **Khán giả thấy trên terminal** (mỗi lần trạng thái đổi là một dòng có giờ UTC):
  - `QUEUED video … job …`
  - `PROCESSING  progress=…` sau khoảng 30 giây (lần đo trước: 26 giây sau khi tải xong);
  - `Running: videoportal-transcode-xxxxx …`, `stop requested for …`, rồi `stop command exit code 0 at progress …` (lần trước: dừng ở 22 %);
  - `RETRYING worker_failed` gần như ngay sau đó (lần trước: 0,9 giây).
- **Nói khi thấy `RETRYING`:** "Lần thử 1 đã chết giữa chừng. Kết quả dở dang không được công bố: trong lúc này mọi lần hỏi URL phát đều nhận 409. Bây giờ hệ thống chờ job bảo trì, chạy 5 phút một lần, đưa job trở lại hàng đợi. Lần đo trước mất 60 giây; xấu nhất là hơn 5 phút. Trong lúc chờ em xin chuyển sang phần giám sát."
- **Mẹo (suy ra từ một lần đo, không bảo đảm):** job bảo trì khởi động vào các phút chia hết cho 5 theo giờ UTC và cần khoảng 20–25 giây mới làm việc. Nếu chủ động được, hãy chạy lệnh khi đồng hồ ở phút thứ 3 hoặc thứ 8 (ví dụ 10:03, 10:08) để lần dừng rơi vào khoảng một phút trước mốc đó.
- **Nếu hỏng:**
  - Script in FAIL "worker stopped while FFmpeg was running": clip quá nhẹ, job đã xong trước khi dừng. Nói thẳng điều đó và mở bằng chứng.
  - Lệnh dừng báo lỗi đăng nhập: phiên `az` hết hạn. Không đăng nhập lại trước khán giả; mở bằng chứng.
  - Bằng chứng: `docs/EVIDENCE.md`, mục "failure drill": dòng thời gian từ 14:29:29 tới 14:31:05 UTC, lần chạy `t9fs5` bị dừng, lần chạy `h2js8` hoàn tất, `DRILL_RESULT` 6 passed.

### 4. Giám sát, nói trong lúc chờ (2:30)

Để terminal của phần 3 chạy tiếp, không đụng vào.

- **Làm:** mở tab **Monitor > Workbooks > Video Portal**. Lần lượt chỉ vào:
  1. "Tổng hợp các clip đã READY": p50/p95 thời gian xử lý, p50/p95 thời gian chờ trong hàng đợi, tổng dung lượng kết quả; hai cột egress và chi phí mỗi clip là **ước tính**.
  2. "Lỗi và lần thử lại": dòng `RETRYING worker_failed` kèm job ID, attempt ID và tên lần chạy job.
  3. "Job bảo trì: những lần có việc phải làm": dòng có `recovered` và `published`.
  4. "API: số request, lỗi 5xx và p95…" mỗi 5 phút.
- **Nói:** "Dashboard không dùng agent nào; nó đọc log JSON mà API và hai job ghi ra. Log tới chậm 1–3 phút, nên dòng của lần dừng vừa rồi có thể chưa hiện; dòng đang thấy là của buổi diễn tập ngày 21 tháng 11. Từ một request ID của người dùng, chúng em lần ra video, job, từng lần thử và tên lần chạy container."
- **Làm:** mở tab **Monitor > Alerts > Alert rules**, chọn rule "Video Portal: transcode attempt failed (system error, retry scheduled)" (tên tài nguyên `videoportal-transcode-system-failure`).
- **Nói:** "Một cảnh báo duy nhất, và nó đòi hành động: nổ khi một lần chuyển mã hỏng vì lỗi hệ thống hoặc khi job bảo trì phải thu hồi một lease. File sai định dạng của người dùng không làm nó nổ. Đánh giá mỗi 5 phút trên cửa sổ 5 phút, gửi email cho chủ dự án, dự kiến trễ 3–10 phút. Việc làm đầu tiên ghi ngay trong mô tả của rule: mở workbook, lấy job ID, kiểm tra lần thử sau đã `READY` và hàng đợi trống."
- **Câu phải nói đúng sự thật về cảnh báo:**
  - Đã đo một lần (2026-11-21): job bị dừng lúc 15:29:16 UTC, cảnh báo chuyển sang **Fired** lúc 15:32:35, tức sau 3 phút 19 giây. Nói: "Lần diễn tập trước cảnh báo nổ sau hơn 3 phút; lần dừng vừa rồi sẽ hiện ở Monitor > Alerts trong khoảng 3–10 phút, và email tới người vận hành." Nếu hết giờ mà chưa thấy thì chỉ vào dòng đã ghi trong `docs/EVIDENCE.md`.
  - Sau khi đã tập và ghi nhận ở `docs/EVIDENCE.md`, thay câu trên bằng số đo thật.
- **Nếu hỏng:** workbook không tải được hoặc phiên Azure Portal hết hạn: mở `docs/AZURE_MONITORING_COST.md` (bảng các ô và bảng cảnh báo) và nói rõ đang xem tài liệu, không phải dashboard sống. Trong `docs/EVIDENCE.md` chưa có ảnh chụp dashboard.

### 5. Diễn tập ngắt lỗi: kết quả (0:45)

- **Làm:** quay lại terminal của phần 3.
- **Khán giả thấy khi xong:** `QUEUED`, `PROCESSING` lần nữa, `READY`, sáu dòng `PASS`, rồi dòng `DRILL_RESULT {"passed": 6, "failed": 0, … "recovered_after_seconds": …}`.
- **Nói:** "Lần thử 2 đã xong. Sáu điều script kiểm: worker bị dừng lúc FFmpeg đang chạy; không có URL phát nào được cấp trong lúc hỏng; job được xử lý lại; trạng thái cuối là READY; có đúng một kết quả phát được; gọi lại `complete` vẫn trả về cùng một job. Số lần thử có giới hạn là 3."
- **Nói thêm một câu về giới hạn:** "Đây là dừng êm: container nhận SIGTERM và worker kịp ghi lỗi. Trường hợp bị giết hẳn, phục hồi nhờ lease hết hạn, chúng em mới chạy trên máy cục bộ; đường dead-letter chưa được kích hoạt trên Azure."
- **Nếu chưa xong:** nói "job bảo trì chưa tới lượt", **làm phần 7 (chi phí) trước**, rồi quay lại terminal. Chưa bấm rollback ở phần 6 khi diễn tập chưa xong, vì rollback đổi image của cả job chuyển mã. Nếu hết giờ mà vẫn chưa `READY`, nói rõ là chưa xong và mở dòng thời gian trong `docs/EVIDENCE.md`. Script tự chờ tối đa 1.500 giây.

### 6. CI/CD và rollback (2:00)

Chỉ bấm chạy rollback khi phần 5 đã in `DRILL_RESULT`.

- **Làm:**
  1. Tab GitHub > **Actions** > workflow **ci** > mở lần chạy gần nhất trên `main`: ba job `test`, `images`, `deploy`.
  2. **Actions** > workflow **rollback** > **Run workflow** > nhánh `main`, ô `image_tag` dán SHA đầy đủ của commit **ngay trước đó** (đã ghi sẵn) > **Run workflow**.
  3. Chuyển sang phần 7 trong lúc chờ (lần đo trước: 87 giây), rồi quay lại xem lần chạy đã xanh và phần tóm tắt in "Deployed image tag …".
  4. Kiểm tra trang vẫn sống: `curl.exe -s "$site/health"`.
- **Nói:** "Mỗi lần push lên main: chạy test, build hai image gắn tag là SHA của commit, rồi một script đổi image của API và hai job, chờ revision mới khoẻ; không khoẻ trong 5 phút thì script tự đặt lại image cũ. GitHub đăng nhập Azure bằng OIDC, không có mật khẩu hay khoá nào được lưu. Rollback là workflow thứ hai dùng cùng script đó, không test và không build, nên main hỏng vẫn quay lại được."
- **Nếu hỏng hoặc không muốn rủi ro:** không bấm chạy; mở hai lần chạy đã có ngày 2026-11-21 (địa chỉ ở `docs/EVIDENCE.md`, mục "deploy and rollback through GitHub Actions"): `ci` lần chạy `44916112596` (deploy thành công, khoảng 5 phút từ push) và `rollback` lần chạy `44916720116` (87 giây). Nói rõ đây là lần chạy đã ghi lại.
- **Sau buổi demo:** đưa bản mới trở lại bằng chính workflow **rollback** với SHA của commit đang chạy lúc đầu (đã ghi sẵn).

### 7. Chi phí và dọn dẹp, một slide (1:00)

- **Slide ghi:**
  - Giá niêm yết, `malaysiawest`, ngày 2026-11-21: khoảng **67,8 USD/tháng (2,26 USD/ngày)** khi không có video nào; trong đó cố định 49,95, API luôn bật 15,55, job bảo trì 2,33.
  - Mỗi clip chuyển mã: khoảng 0,00095–0,00135 USD.
  - Số thật từ Cost Management ngày đầu: 0,0125 USD, **chưa đầy đủ** (chưa có PostgreSQL và Container Apps).
  - Dọn dẹp: `terraform destroy` trong `infra/azure`; giữ trang chạy rẻ hơn: `api_min_replicas = 0`. Chi tiết: `docs/CLEANUP.md`.
- **Nói:** "Đây là giá niêm yết nhân với cấu hình và số đo thật, chưa phải hoá đơn; ngày đầu Cost Management gần như chưa có dữ liệu. Khoản lớn nhất là database và load balancer mà Azure tạo ra vì chúng em giữ database trong mạng riêng. Chấm xong chúng em xoá toàn bộ bằng một lệnh Terraform và kiểm tra lại ở Cost Management ngày hôm sau."
- CHƯA CÓ: số Cost Management đọc lại sau ngày 2026-11-22. Khi có, thay dòng thứ ba của slide.

### 8. Hạn chế và kết (0:45)

- **Nói, không né:**
  - "Đăng nhập đang dùng tài khoản nội bộ trong PostgreSQL, không phải Microsoft Entra External ID như đề gợi ý; external tenant chưa được tạo."
  - "API chạy trên Container Apps chứ không phải App Service."
  - "Hệ thống chuyển mã mỗi lúc một video; mười clip mất khoảng mười phút."
  - "Kiểm thử tải là một lần chạy, chỉ gồm request đọc, trên một replica 0,5 vCPU: p95 285,9 ms, 0 lỗi trên 3.479 request."
  - "Trang chạy trên hostname mặc định của Azure; tên miền riêng chưa chuyển."
- **Kết:** chỉ tới `docs/DESIGN_REPORT.md` và `docs/EVIDENCE.md`.

## Sau buổi demo

- [ ] Đưa image mới trở lại nếu đã rollback (phần 6).
- [ ] Xoá các clip demo không cần giữ ("Failure drill clip", "Demo lớp") trong trang.
- [ ] Ghi kết quả của buổi demo (diễn tập, cảnh báo có nổ không, rollback) vào `docs/EVIDENCE.md` nếu muốn dùng làm bằng chứng.
- [ ] Giảm chi phí hoặc dọn dẹp theo `docs/CLEANUP.md`.
