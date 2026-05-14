# Hướng dẫn crawl Taobao search qua Google (mỗi trang SERP TB)

> **Toàn bộ kiểu crawl khác trong repo:** xem `CRAWL_DATA_SOURCES.md`.

Script: `taobao_search_pages_to_excel.py`.

Taobao thường phân biệt truy cập “từ Google” với truy cập trực tiếp. Để **mỗi lần mở URL `s.taobao.com/search?...` đều đi qua Google**, script dùng **redirect chuẩn** `https://www.google.com/url?sa=t&source=web&rct=j&url=<URL_TB_mã_hóa>` (trình duyệt theo chuỗi 302 rồi vào Taobao), **không** chỉ gắn header `Referer` giả.

## Bắt buộc: không để `--google-search-mode none`

| Giá trị | Ý nghĩa |
|--------|---------|
| **`serp`** (khuyến nghị) | Một lần đầu mở trang **kết quả tìm Google** (`google.com/search?...`), sau đó **mọi trang SERP TB** được mở qua `google.com/url?...`. |
| **`synthetic`** | Không vào SERP Google; chỉ dùng `google.com/url?...` trước mỗi URL Taobao. |
| **`none`** | Không đi Google — **không** dùng khi yêu cầu outbound từ Google. |

Luôn có cookie session hợp lệ: `--cookies path/to/taobao_cookies_session.json`.

## Mỗi trang TB đều “từ trang SERP Google”

Nếu cần **trước mỗi trang SERP TB** đều quay lại **đúng tab kết quả Google** (referer của bước tiếp theo là SERP):

```powershell
python scripts/taobao_search_pages_to_excel.py `
  --cookies runtime\taobao_cookies_session.json `
  --url "https://s.taobao.com/search?page=1&q=Từ_KHOÁ&tab=all" `
  --google-search-mode serp `
  --google-serp-each-page `
  --pagination-nav url `
  --page-step 48 `
  --pages 4 `
  --out runtime\taobao_search.xlsx
```

- Bỏ `--google-serp-each-page` nếu chỉ cần redirect Google **mà không** cần lặp lại SERP trước từng trang TB (nhẹ và nhanh hơn; mở TB vẫn qua `google.com/url?...`).
- **`--pagination-nav url`**: mỗi trang SERP được mở bằng URL Taobao có cả **`page`** và **`s`** (offset). Chỉ đổi `page` không đổi ô kết quả; nếu lệch trang hãy thử `--page-step` (thường 44–48).
- **`--pagination-nav click`**: chỉ các lần **fallback**/`goto` mới đi Google redirect; bấm số trang trong UI không đi qua redirect. Khi headless hay lỗi, ưu tiên **`url`** cùng `page-step`.

## Kiểm tra nhanh

- Trong đầu output Excel/log, `pagination_note` hoặc số ô unique theo **`search_page`** thay đổi đúng từng trang chứ không dừng ở ~một ô trang như một trang SERP cố định.
- Nếu chỉ được vài ô: làm mới cookie, tăng `--wait-ms`, thử tắt `--headless`, hoặc bật `--google-serp-each-page` với `serp`.

## Yêu cầu môi trường

```text
pip install playwright pandas openpyxl
playwright install chromium
```

Chạy từ thư mục `backend` (để đường dẫn `runtime\...` đúng) hoặc chỉnh lại `--cookies` / `--out` theo chỗ đặt file thật của bạn.
