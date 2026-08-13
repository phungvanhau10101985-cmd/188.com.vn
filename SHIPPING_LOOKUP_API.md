# Cổng API tra cứu vận chuyển — hướng dẫn tích hợp

Trên admin: **API & tích hợp** → `/admin/api-keys` (mục «Cổng REST — Tra cứu vận chuyển»).

API này trả **đầy đủ dữ liệu vận chuyển** của 188.com.vn cho hệ thống ngoài (chatbot, CS, kho, đối tác).

Một endpoint, ba cách gọi:

| Đầu vào | Hành vi |
|---------|---------|
| **Mã đơn web** (`DH042`, `DC009`) | Trả chi tiết đơn + mã vận đơn + timeline shop + EMS (nếu có) |
| **Số điện thoại khách** | Trả **đơn gần nhất** (theo `created_at`) của SĐT đó, kèm vận chuyển |
| **Mã EMS** (`EH042737692VN`) | Tra **live MyEMS**: toàn bộ mốc trạng thái cụ thể + chi tiết đơn shop nếu đã ghép |

## 1. Endpoint

```
GET  https://188.com.vn/api/v1/shipping/lookup
POST https://188.com.vn/api/v1/shipping/lookup
```

Local:

```
http://localhost:8001/api/v1/shipping/lookup
```

Qua Next proxy (cùng path): `https://188.com.vn/api/v1/shipping/lookup`

## 2. Xác thực

Bắt buộc. Không có key → HTTP **503**. Sai key → HTTP **401**.

Header (chọn một):

```http
X-Api-Key: YOUR_SHIPPING_LOOKUP_API_KEY
```

hoặc

```http
Authorization: Bearer YOUR_SHIPPING_LOOKUP_API_KEY
```

Cấp key trên admin: **API & tích hợp** → form «Cấp API key» (có hiệu lực ngay, không cần restart).

Key trong `.env` vẫn nhận (cần restart backend):

```env
SHIPPING_LOOKUP_API_KEY=doi-mat-khau-dai-ngau-nhien
```

Nhiều key `.env`: cách nhau bằng dấu phẩy. Cả form lẫn `.env` đều trống = tắt API (503).

## 3. Cách gửi đầu vào

Ưu tiên trường tường minh (nếu gửi cùng lúc): **`ems_code` > `order_code` > `phone` > `q`**.

### GET

```http
GET /api/v1/shipping/lookup?q=DH042
GET /api/v1/shipping/lookup?q=0901234567
GET /api/v1/shipping/lookup?q=EH042737692VN
GET /api/v1/shipping/lookup?order_code=DH042
GET /api/v1/shipping/lookup?phone=0901234567
GET /api/v1/shipping/lookup?ems_code=EH042737692VN
```

### POST JSON

```json
{ "q": "DH042" }
```

```json
{ "phone": "0901234567" }
```

```json
{ "ems_code": "EH042737692VN" }
```

`q` tự nhận diện:

- `DHxxx` / `DCxxx` → mã đơn web
- `09…` / `84…` / `+84…` → SĐT (đơn gần nhất)
- `EHxxxxxxxxxVN` (mã EMS kết thúc `VN`) → tra EMS live + đơn

SĐT được chuẩn hoá: `0901234567`, `84901234567`, `+84 901 234 567` cùng một khách.

## 4. Ví dụ curl

Mã đơn web:

```bash
curl -sS -H "X-Api-Key: YOUR_KEY" \
  "https://188.com.vn/api/v1/shipping/lookup?q=DH042"
```

SĐT — đơn gần nhất:

```bash
curl -sS -H "X-Api-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"phone":"0901234567"}' \
  "https://188.com.vn/api/v1/shipping/lookup"
```

Mã EMS — hành trình đầy đủ:

```bash
curl -sS -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"ems_code":"EH042737692VN"}' \
  "https://188.com.vn/api/v1/shipping/lookup"
```

## 5. Phản hồi thành công (HTTP 200)

`ok: true`. Các khối luôn có mặt; khối không có dữ liệu = `null` / `[]`.

```json
{
  "ok": true,
  "query": "EH042737692VN",
  "query_type": "ems_code",
  "matched_by": "ems_tracking_code",
  "is_latest_order": false,
  "tracking_number": "EH042737692VN",
  "shipping_provider": "EMS",
  "order": {
    "id": 42,
    "order_code": "DH042",
    "status": "shipping",
    "status_label": "Đang giao hàng",
    "payment_method": "cod",
    "payment_status": "pending",
    "payment_status_label": "Chờ thanh toán",
    "customer_name": "Nguyễn Văn A",
    "customer_phone": "0901234567",
    "customer_email": "a@example.com",
    "customer_address": "…",
    "customer_note": null,
    "shipping_method": "EMS",
    "shipping_provider": "EMS",
    "tracking_number": "EH042737692VN",
    "subtotal": 300000,
    "shipping_fee": 0,
    "discount_amount": 0,
    "wallet_amount_used": 0,
    "total_amount": 300000,
    "requires_deposit": false,
    "deposit_amount": 0,
    "deposit_paid": 0,
    "remaining_amount": 300000,
    "created_at": "2026-08-01T10:00:00+07:00",
    "shipped_at": "2026-08-10T09:00:00+07:00",
    "delivered_at": null,
    "items": [
      {
        "product_id": 11,
        "product_name": "Áo thun",
        "product_image": "https://…",
        "product_slug": "ao-thun",
        "product_code": "C0156",
        "product_sku": "C0156/XL",
        "unit_price": 150000,
        "quantity": 2,
        "total_price": 300000,
        "selected_size": "XL",
        "selected_color": "den",
        "selected_color_name": "Đen"
      }
    ]
  },
  "shop_timeline": {
    "current_step_key": "domestic_shipping",
    "footer_note": "…",
    "waiting_admin_at_customs": false,
    "waiting_admin_domestic_delivery": false,
    "events": [
      { "step_key": "deposit_confirmed", "title": "…", "status": "completed", "completed_at": "…" }
    ]
  },
  "ems_record": {
    "reference_code": "…",
    "ems_tracking_code": "EH042737692VN",
    "ems_status": "Phát thành công",
    "ems_phase": "delivered",
    "ems_phase_label": "Phát thành công",
    "cod_amount": 300000,
    "cod_settlement_status": null
  },
  "ems_tracking": {
    "available": true,
    "tracking_code": "EH042737692VN",
    "reference_code": null,
    "weight_grams": "500",
    "receiver_address": "…",
    "current_status_description": "Phát thành công",
    "events": [
      {
        "status_code": null,
        "description": "Phát thành công",
        "address": "Bưu cục Hà Nội",
        "traced_at": "2026-08-12T14:30:00"
      },
      {
        "status_code": null,
        "description": "Giao bưu tá phát hàng",
        "address": "Hà Nội",
        "traced_at": "2026-08-12T08:10:00"
      }
    ],
    "error": null
  }
}
```

### Trường dùng ngay khi tích hợp chatbot / CS

| Trường | Ý nghĩa |
|--------|---------|
| `query_type` | `order_code` / `phone` / `ems_code` |
| `is_latest_order` | `true` khi tra bằng SĐT (đơn mới nhất) |
| `tracking_number` | Mã vận đơn (ưu tiên EMS) |
| `order.status` + `order.status_label` | Trạng thái đơn shop |
| `order.items` | Sản phẩm, size, màu, giá |
| `ems_tracking.current_status_description` | Trạng thái EMS hiện tại (tiếng Việt) |
| `ems_tracking.events` | **Toàn bộ mốc** MyEMS, mới nhất trước |
| `shop_timeline.events` | Các bước nội bộ shop (cọc → TQ → hải quan → nội địa) |

Khi tra **mã EMS**: luôn gọi live MyEMS. `events` là danh sách trạng thái cụ thể (chấp nhận gửi, đến bưu cục, giao bưu tá, phát thành công, …). Nếu mã EMS chưa ghép đơn shop, `order` có thể `null` nhưng `ems_tracking` vẫn đủ hành trình.

Khi tra **SĐT**: chỉ một đơn — đơn tạo gần nhất của số đó.

## 6. Lỗi

| HTTP | Khi nào | `detail` |
|------|---------|----------|
| 400 | Thiếu `q` / `order_code` / `phone` / `ems_code` | Thiếu đầu vào |
| 401 | Sai hoặc thiếu API key | `Unauthorized` |
| 404 | Không tìm thấy đơn / SĐT / vận đơn | Thông báo tiếng Việt |
| 429 | Vượt rate limit IP | Thử lại sau vài giây |
| 503 | Chưa cấu hình `SHIPPING_LOOKUP_API_KEY` | API chưa bật |

Ví dụ 404 (đơn / SĐT / EMS không có dữ liệu — **không** phải «Endpoint not found»):

```json
{
  "ok": false,
  "detail": "Không tìm thấy đơn hàng với số điện thoại này.",
  "query": "0901234567",
  "query_type": "phone"
}
```

`error: "Endpoint not found"` chỉ khi URL sai path (route không tồn tại). Tra `?phone=` / `?q=09…` mà không có đơn vẫn là 404 với `detail` tiếng Việt như trên.

## 7. Trạng thái đơn shop (`order.status`)

| `status` | `status_label` |
|----------|----------------|
| `pending` | Chờ xác nhận |
| `waiting_deposit` | Chờ đặt cọc |
| `deposit_paid` | Đã đặt cọc |
| `confirmed` | Đã xác nhận |
| `processing` | Đang xử lý |
| `shipping` | Đang giao hàng |
| `delivered` | Đã nhận hàng |
| `completed` | Đã đánh giá |
| `returned` | Đơn hoàn đã trả shop |
| `cancelled` | Đã hủy |

## 8. Phase EMS đã cache (`ems_record.ems_phase`)

| `ems_phase` | `ems_phase_label` |
|-------------|-------------------|
| `posted` | Đã chấp nhận gửi |
| `in_transit` | Đang vận chuyển |
| `out_for_delivery` | Đang giao bưu tá |
| `delivered` | Phát thành công |
| `cod_collected` | Đã thu COD |
| `cod_settled` | Đã đối soát COD |
| `unknown` | Chưa xác định |

`ems_record` là bản ghi shop đã import/đối soát. **Hành trình realtime** nằm ở `ems_tracking.events`.

## 9. Gợi ý tích hợp

1. Gửi nguyên chuỗi khách nhập vào `q` — server tự phân loại.
2. Ưu tiên hiển thị: `ems_tracking.current_status_description` → danh sách `ems_tracking.events` → `order.status_label`.
3. Cache phía client 1–2 phút (server cũng cache MyEMS ~120 giây).
4. Không log API key. Không đưa key vào frontend public.
5. SĐT là dữ liệu nhạy cảm: chỉ dùng kênh server-to-server.

## 10. Bật trên production

1. Thêm `SHIPPING_LOOKUP_API_KEY` vào `backend/.env` trên VPS.
2. Restart `188-api` (PM2) để nạp env.
3. Smoke test:

```bash
curl -sS -o /dev/null -w "%{http_code}" \
  -H "X-Api-Key: YOUR_KEY" \
  "https://188.com.vn/api/v1/shipping/lookup?q=DH001"
```

`200` (có đơn) hoặc `404` (không có đơn) = API đã bật. `401` = sai key. `503` = chưa nạp env.
