# Tích hợp Open Catalog — 188.com.vn (kho khách) → NanoAI (nanoai.vn)

Tài liệu tham chiếu DUY NHẤT cho việc đồng bộ catalog 188.com.vn sang NanoAI. Bất kỳ backend/script
nào đọc/ghi theo hướng tích hợp này phải dùng đúng field mapping ở đây để tránh lệch dữ liệu.

## API nguồn (188.com.vn cung cấp — "kho khách")

```
GET https://188.com.vn/api/v1/products/list/full?is_active=true&skip={skip}&limit={limit}
```

- Phân trang: `skip` (mặc định 0), `limit` (mặc định 100, **tối đa 1000** — đã ĐO THỰC TẾ: 1000 SP
  ~30s/response, 100 SP ~4s. **KHÔNG tăng quá 1000** — Cloudflare cắt kết nối origin sau ~100s
  (edge timeout gói Free/Pro), limit lớn hơn dễ khiến 1 request vượt ngưỡng và trả lỗi
  `502 origin_bad_gateway` cho đối tác dù backend vẫn xử lý bình thường, không phải lỗi treo).
- Không yêu cầu xác thực (public GET). Chỉ trả SP `is_active=true` khi truyền đúng query này.
- Response: `{"products": [...], "total": <int>, ...}` — mỗi phần tử trong `products` có shape
  khớp schema `Product` đầy đủ (`backend/app/schemas/product.py`), nhiều hơn 14 trường NanoAI dùng.
- Endpoint dùng session/pool DB **riêng** (tách khỏi pool chính phục vụ khách duyệt web) — xem
  `backend/app/api/endpoints/products.py::read_products_full_list` +
  `backend/app/db/export_session.py`. Mục đích: NanoAI quét chậm/nhiều trang không gây 503 cho
  khách hàng đang mua sắm, và ngược lại không bị timeout do tranh chấp pool giờ cao điểm.

**Khuyến nghị vòng lặp phân trang cho NanoAI/cron:**
1. Gọi `?is_active=true&skip=0&limit=1000` (KHÔNG vượt 1000 — xem lý do ở trên), đọc `total`.
2. Lặp `skip += 1000` cho tới khi `skip >= total` (~100 trang cho 100k SP).
3. Gộp toàn bộ `products` từ các trang thành 1 snapshot `items` duy nhất trước khi POST lên
   Open Catalog (đúng nguyên tắc "kho khách là nguồn chuẩn" — không gửi từng đợt thiếu).
4. Set timeout mỗi trang ≥ 45s (mỗi trang 1000 SP đo thực tế ~30s) và tổng thời gian job đủ lớn
   cho ~100 trang tuần tự (khuyến nghị ≥ 15–20 phút, hoặc gọi song song có kiểm soát 3–5 trang
   cùng lúc nếu hệ thống NanoAI hỗ trợ, để rút ngắn tổng thời gian).

## Field mapping — Trường kho NanoAI ↔ Trường JSON kho khách (188)

Dùng dot-notation cho object lồng (vd `product_info.sku`). `slug` trong API **luôn là URL đầy đủ**
(`https://188.com.vn/products/...`) — dùng thẳng làm link trang sản phẩm, không cần tự ghép domain.

| Trường kho NanoAI | Vector | JSON field (188) | Ghi chú |
|---|---|---|---|
| Mã SKU (tuỳ chọn) | — | `code` | |
| Remarketing / content ID | — | `product_id` | Khoá chính để so khớp thêm/xoá (ưu tiên SKU trước, không có thì khớp tên) |
| Tên hàng / sản phẩm | Văn bản | `name` | |
| Mô tả sản phẩm | — | `description` | |
| Giá (ghi chú text) | Văn bản | `price` | |
| Số lượng tồn (stock_qty) | — | `available` | |
| Size (JSON) | — | `sizes` | Mảng string, vd `["37","38","39"]` |
| Màu sắc (JSON) | — | `colors` | Mảng object `{"name":"Đen","img":"https://..."}`  |
| Ảnh sản phẩm (URL) | Ảnh | `main_image` | |
| Slug (đoạn URL sản phẩm) | — | `slug` | API trả **URL đầy đủ**, không phải chỉ đoạn slug |
| Video sản phẩm (URL) | — | `video_link` | |
| Ghi chú khi tư vấn | Văn bản | `product_info.sku` (hoặc để nguyên object `product_info`) | |
| Thứ tự | — | `id` | id nội bộ DB (số nguyên) |
| Đang bán (trạng thái) | — | `is_active` | |

Vector text (dùng để tìm kiếm/tư vấn AI) = ghép `name` + `price` + `product_info` rồi embed —
không dùng `description`/`sizes`/`colors`/`slug`/`video_link`/`id`/`is_active` làm nguồn vector.

### ⚠️ Cần kiểm tra lại trên form NanoAI

Bảng cấu hình NanoAI gửi ngày 2026-08-04 có 2 dòng khả năng bị lệch — nhờ kiểm tra lại trên UI
NanoAI (`Tích hợp kho web khách → kho NanoAI`):

- Dòng **"Size (JSON)"** đang map tới `description` (nên map tới `sizes`).
- Dòng **"Màu sắc (JSON)"** (dòng đầu, không có ví dụ mẫu) đang map tới `sizes` (nên map tới `colors`
  hoặc bỏ nếu trùng với dòng "Màu sắc (JSON) — vd [...]" thứ hai đã map đúng `colors`).

Nếu không sửa, NanoAI sẽ hiển thị mô tả sản phẩm ở vị trí "size" và không có dữ liệu size thật.

## Quy tắc đồng bộ (phía NanoAI, ghi lại để backend/script tham chiếu)

- So khớp theo `product_id` (SKU/Remarketing ID) sau khi trim; không có thì so khớp theo `name`.
- Mã đã có trong kho NanoAI + còn trong snapshot → giữ nguyên, cập nhật theo dữ liệu mới nhất.
- Mã mới trong snapshot → thêm.
- Mã có trong kho NanoAI nhưng **không còn** trong snapshot → xoá toàn bộ dòng trùng mã.
- Snapshot rỗng (`total=0` hoặc `products=[]`) → **giữ nguyên kho, không xoá gì** (an toàn khi API
  188 lỗi tạm thời — tránh xoá nhầm toàn bộ catalog NanoAI).
- SP không map được `product_id`/`code` → bỏ qua khi build snapshot (không đẩy lên NanoAI).

## Lịch sử thay đổi liên quan

- 2026-08-04 (đợt 1): `/api/v1/products/list/full` chuyển sang pool export riêng, khắc phục lỗi
  "Hết thời gian khi tải danh sách từ kho khách" do tranh chấp pool DB chính.
- 2026-08-04 (đợt 2, revert): từng tăng `limit` tối đa 1000 → 5000 để giảm số trang, nhưng đo thực
  tế cho thấy 1000 SP đã mất ~30s/response — ngoại suy 5000 SP sẽ mất ~150s, **vượt ngưỡng timeout
  origin ~100s của Cloudflare** và gây lỗi `502 origin_bad_gateway` phía NanoAI ngay sau khi tăng.
  Đã **revert về tối đa 1000** (mức đã đo an toàn, ~30s, có đệm dưới ngưỡng Cloudflare).
