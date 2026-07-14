# Báo cáo và theo dõi bảo mật – 188-com-vn

**Cập nhật gần nhất:** 14/07/2026

**Phạm vi:** Static audit toàn bộ backend, frontend, cấu hình triển khai, script vận hành và dependency.

**Mức rủi ro tổng thể:** **CRITICAL**
**Trạng thái triển khai:** **Chưa đủ an toàn để deploy production nếu các lỗi Critical/High còn mở.**

> Báo cáo ngày 02/02/2025 đã được thay thế vì một số kết luận cũ như
> “JWT đã sửa” và “Admin routes đã được bảo vệ” không còn đúng với mã nguồn hiện tại.

## Quy ước trạng thái

- `OPEN`: Đã xác nhận trong mã nguồn, chưa có bản sửa.
- `IN PROGRESS`: Đang sửa nhưng chưa xác minh hoàn tất.
- `FIXED`: Đã sửa và đã kiểm tra lại bằng test hoặc review.
- `ACCEPTED`: Chấp nhận rủi ro có phê duyệt và lý do rõ ràng.

Chỉ chuyển sang `FIXED` khi có cả thay đổi mã nguồn và bước xác minh tương ứng.

## Tổng quan hiện tại

| Mức độ | Tổng số | OPEN | IN PROGRESS | FIXED |
|---|---:|---:|---:|---:|
| Critical | 6 | 4 | 0 | 2 |
| High | 6 | 6 | 0 | 0 |
| Medium | 5 | 5 | 0 | 0 |
| Low | 1 | 1 | 0 | 0 |
| **Tổng** | **18** | **16** | **0** | **2** |

## Việc phải làm ngay

1. Thu hồi và xoay vòng JWT secret, Firebase/Zalo/EMS credential và toàn bộ cookie marketplace đã commit.
2. Bắt buộc xác thực/phân quyền server-side cho import, export, category, category SEO, debug và maintenance endpoints.
3. Chặn các chuỗi XSS còn lại có khả năng chiếm tài khoản admin.
4. Nâng cấp `python-multipart` và các dependency có advisory đã xác minh.

## Danh sách phát hiện

### SEC-001 — Bỏ qua xác thực email

- **Mức độ:** Critical
- **Trạng thái:** FIXED
- **CWE:** CWE-287
- **Vị trí:** `backend/app/api/endpoints/auth_email.py:134-176`, `333-356`
- **Mô tả:** Email đã từng hoàn tất một challenge có thể nhận JWT mới mà không cần OTP,
  magic token, mật khẩu hoặc trusted-device proof.
- **Tác động:** Người chỉ biết email của khách hàng cũ có thể chiếm tài khoản. Nếu tài khoản
  liên kết admin, có thể tiếp tục lấy phiên admin.
- **Cách sửa:** Xóa `_auto_login_if_prior_email_challenge_consumed`; luôn yêu cầu challenge
  mới hoặc trusted-device credential có entropy cao; thu hồi các phiên hiện tại.
- **Xác minh FIXED:** Test đảm bảo email cũ vẫn phải nhập OTP/token mới và không nhận JWT trực tiếp.
- **Bản sửa 14/07/2026:** Đã xóa hoàn toàn nhánh auto-login theo challenge cũ. Thiết bị
  tin cậy dùng opaque token ngẫu nhiên do server cấp, lưu hash trong DB và cookie `HttpOnly`
  có hạn 30 ngày. Test `backend/tests/test_risk_based_auth.py` đã chạy thành công.

### SEC-002 — JWT secret và credential cố định trong source

- **Mức độ:** Critical
- **Trạng thái:** OPEN
- **CWE:** CWE-798, CWE-321
- **Vị trí:** `backend/app/core/config.py:174-178`, `588-605`;
  `backend/app/core/security.py:80-87`; các script `backend/scripts/probe_ems_*.py`
- **Mô tả:** Mã nguồn chứa fallback JWT key và credential dịch vụ bên thứ ba.
  Validator hiện không từ chối fallback JWT lịch sử.
- **Tác động:** Deployment thiếu biến môi trường có thể chấp nhận JWT user/admin giả mạo.
  Credential Firebase, Zalo hoặc EMS có thể bị sử dụng nếu còn hiệu lực.
- **Cách sửa:** Thu hồi/xoay vòng mọi secret; xóa default; fail startup khi thiếu secret;
  xóa secret khỏi Git history; tách khóa admin và customer.
- **Xác minh FIXED:** Secret scan sạch, startup thất bại khi thiếu key, JWT ký bằng key cũ bị từ chối.
- **Tiến độ 14/07/2026:** Đã xóa default JWT khỏi config và từ chối rõ ràng fallback
  lịch sử. Mục này vẫn `OPEN` cho tới khi secret production được xoay vòng, JWT cũ bị
  vô hiệu hóa và các credential Firebase/Zalo/EMS còn lại được xử lý.

### SEC-003 — Import Excel phá dữ liệu không cần đăng nhập

- **Mức độ:** Critical
- **Trạng thái:** OPEN
- **CWE:** CWE-306, CWE-862, CWE-400
- **Vị trí:** `backend/app/api/endpoints/import_export.py:455-531`, `577-710`
- **Mô tả:** Import đồng bộ và bất đồng bộ không có dependency xác thực/phân quyền.
  File được đọc toàn bộ vào RAM và có thể tạo, sửa hoặc xóa sản phẩm.
- **Tác động:** Kẻ tấn công từ xa có thể phá catalogue, sửa giá/nội dung hoặc gây cạn tài nguyên.
- **Cách sửa:** Yêu cầu quyền module sản phẩm; kiểm tra quyền create/update/delete; giới hạn body
  tại Nginx và ứng dụng; stream file; giới hạn số dòng/cột và số job đồng thời.
- **Xác minh FIXED:** Request anonymous nhận 401/403; test quyền CRUD; file vượt giới hạn nhận 413.

### SEC-004 — Cookie phiên marketplace được Git theo dõi

- **Mức độ:** Critical
- **Trạng thái:** OPEN
- **CWE:** CWE-522, CWE-798
- **Vị trí:** `backend/runtime/taobao_cookies_user.json`,
  `backend/runtime/taobao_cookies_session.json`,
  `backend/runtime/tmall_cookies_phungvanhau.json`
- **Mô tả:** Ba file chứa cookie phiên đã được xác nhận là tracked trong Git.
- **Tác động:** Người có repository có thể chiếm các phiên marketplace còn hiệu lực.
- **Cách sửa:** Thu hồi phiên; xóa file khỏi repository và Git history; thêm ignore pattern;
  lưu runtime credential ngoài project với quyền đọc hạn chế.
- **Xác minh FIXED:** `git ls-files` không còn file cookie, history scan sạch và phiên cũ hết hiệu lực.

### SEC-005 — XSS sau đăng nhập qua redirect admin

- **Mức độ:** Critical
- **Trạng thái:** FIXED
- **CWE:** CWE-79, CWE-601
- **Vị trí:** `frontend/app/admin/login/page.tsx:13`, `36-43`
- **Mô tả:** Query `redirect` được chuyển trực tiếp vào `router.push` sau khi token admin
  vừa được ghi vào `localStorage`.
- **Tác động:** URL có scheme nguy hiểm như `javascript:` có thể chạy trong origin admin
  và đánh cắp token mới.
- **Cách sửa:** Chỉ cho phép đường dẫn tương đối bắt đầu bằng đúng một `/`; từ chối `//`,
  scheme, control character và giá trị quá dài; ưu tiên allowlist route admin.
- **Xác minh FIXED:** Test các payload `javascript:`, `data:`, `//host` đều bị từ chối.
- **Bản sửa 14/07/2026:** `safeAdminRedirect` chỉ chấp nhận đường dẫn bắt đầu bằng
  `/admin`, từ chối `//` và mọi scheme. Frontend type-check đã thành công.

### SEC-006 — URL do khách hàng kiểm soát đi vào UI admin

- **Mức độ:** Critical
- **Trạng thái:** OPEN
- **CWE:** CWE-79
- **Vị trí:** `frontend/components/orders/OrderItemVariantMeta.tsx:15-54`;
  `backend/app/schemas/cart.py:12-21`; `backend/app/crud/cart.py:118-130`
- **Mô tả:** `line_image_url` do khách hàng cung cấp được lưu vào đơn hàng và render thành link
  trong giao diện admin mà không kiểm tra scheme.
- **Tác động:** Admin bấm link `javascript:` có thể bị chiếm token hoặc thực hiện API đặc quyền.
- **Cách sửa:** Backend chỉ nhận HTTPS và host ảnh cho phép; lấy ảnh từ dữ liệu sản phẩm server-side;
  frontend parse URL và chỉ render link khi protocol/host hợp lệ.
- **Xác minh FIXED:** API từ chối scheme/host lạ và UI không tạo anchor cho dữ liệu không hợp lệ.

### SEC-007 — API quản trị category và category SEO công khai

- **Mức độ:** High
- **Trạng thái:** OPEN
- **CWE:** CWE-862
- **Vị trí:** `backend/app/api/endpoints/categories.py:290-316`;
  `backend/app/api/endpoints/category_seo.py:503-1756`
- **Mô tả:** Nhiều endpoint tạo/sửa/xóa category, redirect và SEO chỉ phụ thuộc `get_db`.
- **Tác động:** Có thể phá navigation, canonical, index SEO hoặc di chuyển sản phẩm hàng loạt.
- **Cách sửa:** Tách public read routes; áp dụng quyền `taxonomy`/`category_seo` và CRUD cụ thể.
- **Xác minh FIXED:** Anonymous và admin thiếu module nhận 401/403 cho mọi mutation.

### SEC-008 — Export catalogue và file export công khai

- **Mức độ:** High
- **Trạng thái:** OPEN
- **CWE:** CWE-200, CWE-862
- **Vị trí:** `backend/app/api/endpoints/import_export.py:751-873`, `959-1027`;
  `backend/main.py:84-87`
- **Mô tả:** Export toàn bộ catalogue không yêu cầu đăng nhập; file tạo ra nằm dưới static
  và các endpoint download cũng công khai.
- **Tác động:** Lộ nguồn hàng, link gốc, tên tiếng Trung, trạng thái vận hành và dữ liệu nội bộ.
- **Cách sửa:** Bắt buộc quyền export; lưu ngoài static; download có xác thực/thời hạn;
  chỉ export allowlist cột được phép.
- **Xác minh FIXED:** Anonymous không tạo/tải file; URL cũ không còn truy cập được.

### SEC-009 — `python-multipart` có lỗ hổng ReDoS

- **Mức độ:** High
- **Trạng thái:** OPEN
- **CWE:** CWE-1333
- **Vị trí:** `backend/requirements.txt:22`
- **Mô tả:** `python-multipart==0.0.6` khớp các advisory remote DoS, gồm
  CVE-2024-24762 và CVE-2024-53981. Dự án có multipart endpoint công khai.
- **Tác động:** Request được chế tạo có thể khóa worker FastAPI và làm API mất khả dụng.
- **Cách sửa:** Nâng lên bản hiện hành đã vá; thêm giới hạn header/body, timeout và rate limit.
- **Xác minh FIXED:** Dependency scanner sạch và regression test multipart độc hại không khóa worker.

### SEC-010 — Stored XSS trong mô tả sản phẩm

- **Mức độ:** High
- **Trạng thái:** OPEN
- **CWE:** CWE-79
- **Vị trí:** `frontend/components/product-detail/DescriptionHtmlSafeImages.tsx:60-75`;
  `frontend/components/product-detail/ProductTabs.tsx:350`, `379-387`
- **Mô tả:** HTML mô tả/import được render bằng `dangerouslySetInnerHTML` mà không sanitize.
- **Tác động:** Payload lưu trữ chạy với mọi khách truy cập sản phẩm và có thể nhắm tới admin cùng origin.
- **Cách sửa:** Sanitize tại backend khi nhập và trước render bằng allowlist nghiêm ngặt;
  loại script, event attributes, SVG, iframe, form và URL scheme nguy hiểm.
- **Xác minh FIXED:** Bộ payload XSS phổ biến bị loại và nội dung hợp lệ vẫn render đúng.

### SEC-011 — Token localStorage bị phơi cho script bên thứ ba

- **Mức độ:** High
- **Trạng thái:** OPEN
- **CWE:** CWE-922
- **Vị trí:** `frontend/lib/api-client.ts:195-208`; `frontend/lib/admin-api.ts:71-74`;
  `frontend/components/SiteEmbedsRoot.client.tsx:18-154`; `frontend/app/layout.tsx:150-204`
- **Mô tả:** Token customer/admin nằm trong `localStorage`, trong khi script/embed bên thứ ba
  được chạy toàn cục, kể cả route admin.
- **Tác động:** Compromise một widget hoặc cấu hình embed có thể làm lộ mọi phiên.
- **Cách sửa:** Chuyển sang cookie `HttpOnly`, `Secure`, `SameSite`; tách admin sang origin riêng;
  loại free-form JavaScript và dùng allowlist script.
- **Xác minh FIXED:** JavaScript client không đọc được token và admin không tải storefront embeds.

### SEC-012 — Backup chứa secret không mã hóa

- **Mức độ:** High
- **Trạng thái:** OPEN
- **CWE:** CWE-311, CWE-276
- **Vị trí:** `deploy/backup-vps.sh:196-296`
- **Mô tả:** Backup gồm DB, env, PM2 và TLS private key nhưng archive gzip không được mã hóa,
  không ép `umask 077` hoặc mode `0600`.
- **Tác động:** Local user, backup agent hoặc Drive ACL sai có thể lấy toàn bộ secret và dữ liệu.
- **Cách sửa:** Đặt quyền 0700/0600; mã hóa trước khi lưu/upload; hạn chế principal và retention;
  tránh backup TLS key nếu không cần.
- **Xác minh FIXED:** Archive được mã hóa, permission đúng và restore test thành công.

### SEC-013 — SSRF qua mẫu QR ngân hàng

- **Mức độ:** Medium
- **Trạng thái:** OPEN
- **CWE:** CWE-918
- **Vị trí:** `backend/app/services/sepay.py:160-189`;
  `backend/app/api/endpoints/bank_accounts.py:42-50`
- **Mô tả:** `qr_template_url` không giới hạn scheme/host; backend tải URL với redirect bật.
- **Tác động:** Nhân sự có quyền module ngân hàng có thể truy cập service nội bộ hoặc cloud metadata.
- **Cách sửa:** Allowlist HTTPS host; chặn IP private/loopback/link-local trước mọi redirect;
  giới hạn kích thước và kiểm tra MIME/magic bytes.
- **Xác minh FIXED:** Test localhost, private IP, DNS rebinding và redirect sang private IP đều bị chặn.

### SEC-014 — Credential và token bị ghi console production

- **Mức độ:** Medium
- **Trạng thái:** OPEN
- **CWE:** CWE-532
- **Vị trí:** `frontend/features/auth/api/auth-api.ts:51-310`;
  `frontend/lib/api-client.ts:1078-1095`
- **Mô tả:** Login/register/profile payload và response chứa token được ghi console không có production guard.
- **Tác động:** Dữ liệu có thể đi vào extension, diagnostics, remote support hoặc bản ghi trình duyệt.
- **Cách sửa:** Xóa log; nếu cần debug thì chỉ bật development và luôn redact PII/token.
- **Xác minh FIXED:** Production build không log token, OTP, email, điện thoại hoặc hồ sơ.

### SEC-015 — Xóa cache không cần xác thực

- **Mức độ:** Medium
- **Trạng thái:** OPEN
- **CWE:** CWE-306, CWE-400
- **Vị trí:** `frontend/app/api/clear-cache/route.ts:5-16`
- **Mô tả:** Mọi caller có thể POST để gọi `revalidateTag`.
- **Tác động:** Request lặp lại làm vô hiệu cache và tăng tải backend/database.
- **Cách sửa:** Yêu cầu admin hoặc internal secret; kiểm tra Origin; rate limit endpoint.
- **Xác minh FIXED:** Anonymous nhận 401/403 và request hợp lệ có giới hạn tốc độ.

### SEC-016 — Debug endpoint công khai

- **Mức độ:** Medium
- **Trạng thái:** OPEN
- **CWE:** CWE-489, CWE-200
- **Vị trí:** `backend/app/api/endpoints/debug.py:9-110`; `backend/app/api/api.py:30`
- **Mô tả:** Debug router luôn được mount và công khai count, ID, tên sản phẩm và kết quả tìm kiếm.
- **Tác động:** Lộ dữ liệu nội bộ và hỗ trợ trinh sát hệ thống.
- **Cách sửa:** Không mount router ở production hoặc yêu cầu quyền admin; mặc định tắt docs production.
- **Xác minh FIXED:** Route không tồn tại hoặc trả 401/403 trong production.

### SEC-017 — Cron secret xuất hiện trong argv và output

- **Mức độ:** Medium
- **Trạng thái:** OPEN
- **CWE:** CWE-522
- **Vị trí:** `deploy/enable-product-catalog-sheet-sync.sh:38-51`
- **Mô tả:** Script chèn secret thật vào crontab, truyền qua `curl` argv và in cron line.
- **Tác động:** Token có thể lộ qua process listing, crontab, terminal capture và log vận hành.
- **Cách sửa:** Đọc token từ file mode 0600 tại runtime hoặc dùng internal scheduler/helper.
- **Xác minh FIXED:** Secret không xuất hiện trong argv, crontab output hoặc log.

### SEC-018 — Lộ chi tiết exception nội bộ

- **Mức độ:** Low
- **Trạng thái:** OPEN
- **CWE:** CWE-209
- **Vị trí:** `backend/main.py:394-421`, `772-799`;
  `backend/app/middleware/http_safe.py:119-138`
- **Mô tả:** Một số public handler và middleware trả raw exception; health DB trả lỗi hạ tầng.
- **Tác động:** Lộ driver DB, đường dẫn, schema, upstream response và trạng thái vận hành.
- **Cách sửa:** Trả error ID/message ổn định; giữ exception đầy đủ trong log bảo vệ;
  giới hạn health chi tiết cho monitoring nội bộ.
- **Xác minh FIXED:** Public response không còn raw exception nhưng log nội bộ vẫn đủ chẩn đoán.

## Dependency cần nâng cấp

| Dependency | Phiên bản hiện tại | Tình trạng |
|---|---|---|
| `python-multipart` | `0.0.6` | Có advisory remote DoS, trực tiếp reachable |
| `python-jose` | `3.3.0` | Có advisory; flow HS256 hiện tại giảm khả năng khai thác |
| `cryptography` | `41.0.7` | Khớp advisory; chưa thấy call site dễ khai thác |
| `jinja2` | `3.1.2` | Khớp advisory; chưa thấy ứng dụng sử dụng trực tiếp |
| `Pillow` | `10.3.0` | Khớp advisory xử lý ảnh; cần nâng cấp |
| `next` | `16.2.6` | Chưa thấy advisory áp dụng cho đúng bản khóa hiện tại |

Sau khi nâng cấp phải chạy test backend/frontend và quét lại bằng công cụ SCA.

## Kiểm soát tích cực đang có

- CORS giới hạn theo domain cấu hình.
- Backend/frontend được cấu hình bind loopback dưới PM2.
- HTTPS termination và Nginx reverse proxy đã có mẫu cấu hình.
- Truy vấn SQLAlchemy thông thường dùng bound parameters.
- CDN proxy dùng upstream cố định, không phải open proxy.
- Có rate limiting ở một số đường dẫn, nhưng chưa bao phủ đầy đủ endpoint nhạy cảm.

Các điểm này không bù được các lỗi Critical/High đang mở.

## Bảo vệ đăng nhập theo rủi ro đã triển khai

- Thiết bị khách mới luôn phải hoàn tất OTP; email đã từng đăng nhập không còn là bằng chứng.
- Thiết bị khách chỉ được tin cậy bằng opaque token ngẫu nhiên trong cookie `HttpOnly`,
  có hạn 30 ngày và chỉ lưu hash ở server.
- JWT phát từ email OTP/trusted device cũng bị giới hạn tối đa 30 ngày để thời hạn phiên
  không vượt quá chính sách tin cậy thiết bị.
- Đổi email, rút tiền và chuyển phiên khách sang admin yêu cầu step-up OTP gần đây;
  challenge lưu DB, dùng một lần theo cập nhật atomic, giới hạn gửi/nhập sai, dùng
  opaque public ID và có purpose riêng.
- Admin trên thiết bị mới phải qua username/password và OTP email. Thiết bị admin tin cậy
  được tách khỏi thiết bị khách và có hạn 30 ngày.
- Admin JWT mặc định có hạn 8 giờ thay vì dùng chung TTL 7 ngày.
- `ADMIN_MFA_ENABLED` là feature flag rollout; production chỉ nên tắt tạm thời khi cần
  bổ sung email hợp lệ cho admin và phải bật lại ngay sau đó.

## Checklist trước khi deploy production

### Bắt buộc

- [ ] Tất cả SEC-001 đến SEC-012 chuyển sang `FIXED` hoặc có phê duyệt `ACCEPTED`.
- [ ] Xoay vòng toàn bộ secret/cookie đã lộ và vô hiệu hóa giá trị cũ.
- [ ] Xóa secret/cookie khỏi Git history, không chỉ commit mới nhất.
- [ ] Chạy test xác thực/phân quyền cho mọi mutation endpoint.
- [ ] Chạy test XSS, SSRF, upload limit và multipart DoS.
- [ ] Chạy dependency audit và secret scan trong CI.
- [ ] Kiểm tra header bảo mật, CSP, HSTS và cấu hình Nginx/CDN thực tế.
- [ ] Kiểm tra permission của `.env`, backup, credential và runtime files.

### Khuyến nghị

- [ ] Tách origin admin khỏi storefront.
- [ ] Dùng cookie HttpOnly thay cho token trong localStorage.
- [ ] Thêm JWT `jti`, revoke list, issuer, audience và rút ngắn thời hạn token.
- [ ] Dùng rate limit dùng chung giữa nhiều worker thay vì chỉ in-memory.
- [ ] Tắt Swagger/ReDoc và debug route theo mặc định ở production.
- [ ] Thêm SAST, SCA, secret scanning, SBOM và dependency update bot vào CI.

## Cách cập nhật trạng thái

Khi sửa một phát hiện:

1. Đổi `OPEN` thành `IN PROGRESS` khi bắt đầu.
2. Ghi commit/PR và test liên quan ngay dưới mục phát hiện.
3. Chỉ đổi thành `FIXED` sau khi test và review lại thành công.
4. Cập nhật số liệu trong “Tổng quan hiện tại”.
5. Ghi ngày và nội dung thay đổi trong lịch sử bên dưới.

## Giới hạn của báo cáo

- Đây là static audit; chưa gửi exploit payload tới production.
- Chưa kiểm tra VPS, firewall, CDN, PM2 user, database role, IAM và ACL Drive thực tế.
- Chưa kiểm tra credential còn hiệu lực hay không; phải coi mọi credential đã commit là bị lộ.
- Chưa quét đầy đủ Git history và dependency tree bằng CI scanner.
- Không thể kết luận đã tìm thấy mọi lỗ hổng.

## Lịch sử cập nhật

- **14/07/2026:** Hoàn tất đợt củng cố đăng nhập theo rủi ro. SEC-001 và SEC-005
  chuyển sang `FIXED`; thêm trusted-device token server-issued, step-up OTP, admin MFA
  theo thiết bị và admin session 8 giờ. Kiểm tra: 5 backend tests pass, compile backend
  và frontend type-check thành công.
- **14/07/2026:** Audit lại toàn repository; thay thế báo cáo 2025; ghi nhận
  6 Critical, 6 High, 5 Medium và 1 Low.
- **02/02/2025:** Báo cáo ban đầu trước production.
