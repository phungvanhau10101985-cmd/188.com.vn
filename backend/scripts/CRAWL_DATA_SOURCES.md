# Danh mục crawl / export dữ liệu (188-com-vn)

Tất cả lệnh mẫu chạy từ thư mục **`backend`** (Windows): `cd backend` và `PYTHONPATH=.` trước khi gọi `python scripts/…` nếu script import `app.*`.

**Chung**

- **`pip install playwright pandas openpyxl`** (Tuỳ script thêm deps.)
- **`playwright install chromium`** cho script dùng Playwright.
- **Cookie Taobao**: file JSON kiểu export Playwright; **không commit**; có thể dùng `runtime/taobao_cookies_session.json`.
- Tuân thủ ToS/Bản quyền từng nền (Taobao, 1688, Hi-box).

---

## 1. Taobao (`backend/scripts/`)

### 1.1 Tìm kiếm SERP — nhiều trang → Excel

| Mục | File | Ghi chú |
|-----|------|--------|
| Kết quả `s.taobao.com/search?…` | `taobao_search_pages_to_excel.py` | N trang, gộp unique `item_id`; giá/card mới (`priceInt--`, shop); phân trang **`url`** (`page` + **`s`**, `--page-step`) hoặc **`click`**; outbound Google **`google.com/url?…`** khi không dùng `--google-search-mode none`. Chi tiết: **`TAOBAO_SEARCH_GOOGLE_REDIRECT.md`**. |

### 1.2 Trang cửa hàng (category listing) → Excel

| Mục | File | Ghi chú |
|-----|------|--------|
| `shop*.taobao.com/category.htm` | `taobao_shop_category_to_excel.py` | Cookie + cuộn “infinite”; Google referer **`serp`** / **`synthetic`** / **`none`** (qua docstring script). Mặc định không headless một số trường hợp. |

### 1.3 Chi tiết một SP (item) → một dòng Excel

| Mục | File | Ghi chú |
|-----|------|--------|
| `item.taobao.com/item.htm?id=…` | `taobao_item_detail_to_excel.py` | DOM + lazy + tab 图文详情 + XHR hints; SKU/参数/gallery/详情图; **`--google-search-mode`** SERP synthetic none. |

---

## 2. Hi-box (`hibox.mn`, Nuxt SPA)

| Mục | File | Ghi chú |
|-----|------|--------|
| Trang shop (danh sách `/v/…`) | `hibox_shop_list_to_excel.py` | Playwright, cuộn lazy; URL dạng `https://hibox.mn/shop/…`. |
| Một trang SP (`/v/slug`) | `export_hibox_item_excel.py` | Một dòng Excel: gallery, specs, variant màu/cỡ, video Taobao nếu có; hỗ trợ link nguồn 1688/Taobao qua Hi-box. |

---

## 3. 1688

| Mục | File / vị trí | Ghi chú |
|-----|----------------|--------|
| Một offer → Excel mẫu (giống export draft) | `export_1688_excel_preview.py` | Gọi `app.services.import_1688_scraper.scrape_1688_product`; ghi `app/static/uploads/sample_1688_export_*.xlsx`. |
| Lọc offer **chưa có PDP** trên [vipomall.vn](https://vipomall.vn/) → Excel Hibox | `filter_1688_not_on_vipomall.py` | Playwright probe PDP Vipomall; giữ dòng chưa list, đổi Link → `hibox.mn/v/abb-{offerId}` để import admin. |
| Import có auth / batch | API **`/import-1688`** | `app/api/endpoints/import_1688.py` + `import_1688_scraper.py`, `import_hibox_scraper.py` — crawl 1688 / Hi-box phục vụ draft sản phẩm (không phải một file script độc lập “chạy tay” đầy đủ như bảng trên; dùng admin/API). |

---

## 4. “Chọn loại crawl” nhanh

- **Nhiều SP từ từ khoá Taobao (SERP):** `taobao_search_pages_to_excel.py` + doc **`TAOBAO_SEARCH_GOOGLE_REDIRECT.md`**.
- **Nhiều SP một shop TB:** `taobao_shop_category_to_excel.py`.
- **Chi tiết 1 TB:** `taobao_item_detail_to_excel.py`.
- **Nhiều SP shop Hi-box:** `hibox_shop_list_to_excel.py`.
- **Chi tiết 1 SP Hi-box (kèm 1688/TB overlay):** `export_hibox_item_excel.py`.
- **Xem trước cấu trúc Excel 1688 một offer:** `export_1688_excel_preview.py`.
- **Đưa vào hệ thống sản phẩm:** luồng admin **import 1688 / Hi-box** (API trong repo).
