# Đăng nhập Gmail — sửa lỗi `origin_mismatch`

Google chặn đăng nhập khi **URL trên thanh địa chỉ** (origin) **không trùng** danh sách **Authorized JavaScript origins** của OAuth client.

## Các bước (Google Cloud Console)

1. Mở [Google Cloud Console](https://console.cloud.google.com/) → chọn project (vd. `comvn-320603`).
2. **APIs & Services** → **Credentials**.
3. Mở **OAuth 2.0 Client ID** loại **Web application** (cùng Client ID với `GOOGLE_CLIENT_ID` / `NEXT_PUBLIC_GOOGLE_CLIENT_ID`).
4. **Authorized JavaScript origins** — thêm **đúng từng origin** bạn dùng (không có path `/`, không dấu `/` cuối):

| Môi trường | Thêm origin |
|------------|-------------|
| Production | `https://188.com.vn` |
| Production (www) | `https://www.188.com.vn` |
| Dev local | `http://localhost:3001` |
| Dev (cổng khác) | `http://localhost:3000` (nếu chạy Next cổng 3000) |
| Ngrok / tunnel | `https://xxxx.ngrok-free.app` (URL ngrok **đầy đủ**, đổi mỗi lần tạo tunnel mới) |

5. **Authorized redirect URIs** (nếu có): với Google Identity Services (nút Gmail) thường **không bắt buộc** redirect; nếu Google yêu cầu, thêm `https://188.com.vn` (không path).

6. **Save** — đợi **1–5 phút** rồi thử đăng nhập lại (tab ẩn danh hoặc Ctrl+F5).

## Kiểm tra trong project

- `frontend/.env.local`: `NEXT_PUBLIC_GOOGLE_CLIENT_ID=...` (cùng Web client ID).
- `backend/.env`: `GOOGLE_CLIENT_ID=...` (cùng giá trị).
- Sau khi sửa `.env`: restart **Next** (`npm run dev`) và **FastAPI** (port 8001).

## Lỗi thường gặp

| Triệu chứng | Nguyên nhân |
|-------------|-------------|
| `origin_mismatch` | Origin trang ≠ origin đã khai báo (http vs https, www, cổng, ngrok mới) |
| Đăng nhập OK trên production, lỗi trên máy dev | Thiếu `http://localhost:3001` trong origins |
| Đổi ngrok URL | Phải thêm origin ngrok mới vào Console |

Trên trang **Đăng nhập**, dòng «Origin hiện tại» cho biết chính xác chuỗi cần thêm vào Google Cloud.
