# Hướng dẫn đồng bộ catalog 188.com.vn — gửi đội kỹ thuật NanoAI

Kính gửi đội kỹ thuật NanoAI,

188.com.vn đã bổ sung API đồng bộ gia tăng, nhằm không phải quét toàn bộ 100.000 sản phẩm ở mỗi
lần cron và bảo đảm bên NanoAI nhận được cả tín hiệu xóa sản phẩm.

## 1. API lấy danh sách sản phẩm

```
GET https://188.com.vn/api/v1/products?updated_since=<ISO-8601-UTC>&page=1&limit=500
```

- `updated_since`: mốc UTC lần đồng bộ thành công trước đó, ví dụ `2026-08-04T10:00:00Z`.
- `page`: bắt đầu từ 1; `limit` tối đa **500**.
- Không cần xác thực (public GET).
- Response mẫu:
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

## 2. Cách phân trang và lưu mốc đồng bộ

1. Lần chạy đầu: dùng `updated_since=1970-01-01T00:00:00Z`; gọi `page=1`, sau đó tăng page đến
   `pagination.total_pages`.
2. Lần chạy sau: dùng timestamp UTC của **lần chạy thành công trước đó**; vẫn lặp hết các page.
3. Chỉ cập nhật timestamp lưu trữ sau khi toàn bộ page chạy thành công. API trả inclusive ở mốc thời
   gian nên NanoAI có thể nhận lại item trùng; hãy upsert theo `id`.
4. **Bắt buộc xử lý `is_deleted=true`**: xóa toàn bộ bản ghi cùng `id`/`product_id` tại kho NanoAI.
   Không được lọc các item này trước khi xử lý.

> Lưu ý: tín hiệu `is_deleted=true` được ghi nhận kể từ khi API mới được deploy. Vì vậy, lần chạy
> đầu cần đồng bộ baseline đầy đủ bằng mốc `1970-01-01T00:00:00Z`.

## 3. Cấu hình timeout/thời lượng job

| Thông số | Giá trị đo thực tế | Khuyến nghị cấu hình |
|---|---|---|
| Kích thước trang | Tối đa 500 thay đổi | `limit=500` |
| Timeout mỗi request | — | ≥45 giây |
| Đồng bộ định kỳ | Chỉ lấy phần thay đổi | Không cần quét 100k SP mỗi lần |

Không gọi song song các page của cùng một mốc nếu chưa bảo đảm thứ tự xử lý/idempotency.

## 4. Mapping trường dữ liệu (tham khảo, đã áp dụng đúng ở phần lớn cấu hình)

| Trường kho NanoAI | JSON field (188) | Ghi chú |
|---|---|---|
| Mã SKU (tuỳ chọn) | `code` | |
| Remarketing / content ID | `product_id` | Khoá chính để so khớp thêm/xoá |
| Tên hàng / sản phẩm | `name` | |
| Mô tả sản phẩm | `description` | |
| Giá | `price` | |
| Số lượng tồn (stock_qty) | `available` | |
| Size (JSON) | `sizes` | Mảng string, vd `["37","38","39"]` |
| Màu sắc (JSON) | `colors` | Mảng object `{"name":"Đen","img":"https://..."}` |
| Ảnh sản phẩm (URL) | `main_image` | |
| Slug / link sản phẩm | `slug` | API trả **URL đầy đủ**, dùng thẳng không cần ghép domain |
| Video sản phẩm (URL) | `video_link` | |
| Ghi chú khi tư vấn | `product_info.sku` | |
| Thứ tự | `id` | |
| Đang bán (trạng thái) | `is_active` | |

### Lưu ý cần chỉnh trên form cấu hình NanoAI

Qua rà soát bảng cấu hình đội gửi ngày 2026-08-04, phát hiện 2 dòng bị lệch mapping:
- Dòng **"Size (JSON)"** hiện đang map tới `description` → cần sửa thành `sizes`.
- Dòng **"Màu sắc (JSON)"** (dòng không có ví dụ mẫu) hiện đang map tới `sizes` → cần sửa thành
  `colors`, hoặc xoá bớt vì đã có 1 dòng "Màu sắc (JSON)" khác map đúng tới `colors` rồi.

Nếu chưa sửa, sản phẩm hiển thị bên NanoAI sẽ bị lẫn mô tả vào ô "size" và thiếu dữ liệu size thật.

## 5. Quy tắc thêm/xoá sản phẩm khi đồng bộ

- So khớp theo `product_id` (ưu tiên) hoặc `code`; không có thì so khớp theo `name`.
- Có trong snapshot mới + đã có trong kho NanoAI → cập nhật theo dữ liệu mới nhất.
- Có trong snapshot mới, chưa có trong kho NanoAI → thêm mới.
- Item `is_deleted=true` → xoá toàn bộ bản ghi cùng `id`/`product_id` trong kho NanoAI.
- Không map được `product_id`/`code` → bỏ qua, không đẩy lên.

Rất mong đội kỹ thuật NanoAI chuyển cron sang API mới và xử lý tombstone `is_deleted=true` theo
hướng dẫn trên. Có vấn đề gì cần trao đổi thêm, xin liên hệ lại.

Trân trọng,
188.com.vn
