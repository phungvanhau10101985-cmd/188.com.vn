# Tích hợp Open Catalog — 188.com.vn (kho khách) → NanoAI (nanoai.vn)

Tài liệu tham chiếu DUY NHẤT cho việc đồng bộ catalog 188.com.vn sang NanoAI. Bất kỳ backend/script
nào đọc/ghi theo hướng tích hợp này phải dùng đúng field mapping ở đây để tránh lệch dữ liệu.

## API đồng bộ gia tăng (NanoAI dùng từ nay)

```
GET https://188.com.vn/api/v1/products?updated_since=<ISO-8601-UTC>&page=1&limit=500
```

- `updated_since` là mốc UTC của **lần đồng bộ thành công trước đó**, ví dụ
  `2026-08-04T10:00:00Z`; bắt buộc có timezone.
- `page` bắt đầu từ 1; `limit` tối đa **500**.
- Không được lọc/loại các item có `is_deleted=true`: NanoAI phải dùng các item này để xóa bản ghi
  cũ đã bị hard-delete trên 188.
- Response:
  ```json
  {
    "success": true,
    "pagination": { "total_records": 120, "page": 1, "limit": 500, "total_pages": 1 },
    "data": [
      { "id": "PROD_9981", "updated_at": "2026-08-02T14:30:00Z", "is_deleted": false },
      { "id": "PROD_9980", "updated_at": "2026-08-02T14:31:00Z", "is_deleted": true }
    ]
  }
  ```

**Quy trình chạy NanoAI:**
1. Lần đầu (tạo baseline): gọi `updated_since=1970-01-01T00:00:00Z`, lặp `page=1..total_pages`.
2. Các lần sau: giữ lại mốc UTC trước khi job bắt đầu, gọi với mốc đó và lặp hết `total_pages`.
3. Chỉ lưu mốc mới sau khi tất cả trang xử lý thành công. Có thể nhận lại một số item trùng tại đúng
   ranh giới timestamp; cần upsert theo `id`, nên hoàn toàn an toàn.

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
