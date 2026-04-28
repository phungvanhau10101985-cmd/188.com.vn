# AI ANALYSIS SUMMARY

## PROJECT OVERVIEW
- **Path**: `G:\python-code\188-com-vn`
- **Total Files**: 193
- **Total Size**: 5.3 MB
- **Scanned Directories**: 70
- **Scanned Files**: 193

## PROJECT STRUCTURE
- `ai_analysis/` - 3 files (.md:1, .json:1, .txt:1)
- `backend/` - 105 files (.py:56, .backup:2, .original:1)
- `frontend/` - 79 files (.tsx:46, .ico:1, .css:1)

## KEY FILES IDENTIFIED
### 🔴 HIGH PRIORITY
- `backend/app/api/endpoints/__init__.py` - **code** - API endpoints - __init__.py
- `backend/app/api/endpoints/auth.py` - **code** - API endpoints - auth.py
- `backend/app/api/endpoints/cart.py` - **code** - API endpoints - cart.py
- `backend/app/api/endpoints/categories.py` - **code** - API endpoints - categories.py
- `backend/app/api/endpoints/debug.py` - **code** - API endpoints - debug.py
- `backend/app/api/endpoints/fallback.py` - **code** - API endpoints - fallback.py
- `backend/app/api/endpoints/filters.py` - **code** - API endpoints - filters.py
- `backend/app/api/endpoints/import_export.py` - **code** - API endpoints - import_export.py
- `backend/app/api/endpoints/orders.py` - **code** - API endpoints - orders.py
- `backend/app/api/endpoints/products.py` - **code** - API endpoints - products.py
- `backend/app/api/endpoints/user_behavior.py` - **code** - API endpoints - user_behavior.py
- `backend/app/api/__init__.py` - **code** - API endpoints - __init__.py
- `backend/app/api/api.py` - **code** - API endpoints - api.py
- `backend/app/core/__init__.py` - **code** - .py file - __init__.py
- `backend/app/core/config.py` - **code** - Application configuration

### 🟡 NORMAL PRIORITY
- `frontend/README.md` - documentation - Project documentation

## FILE TYPE DISTRIBUTION (Top 15)
- `.py`: 59 files (30.6%)
- `.tsx`: 46 files (23.8%)
- `.xlsx`: 35 files (18.1%)
- `.ts`: 16 files (8.3%)
- `.json`: 5 files (2.6%)
- `.svg`: 5 files (2.6%)
- `.md`: 3 files (1.6%)
- `.sql`: 3 files (1.6%)
- `.db`: 3 files (1.6%)
- `.js`: 3 files (1.6%)
- `.txt`: 2 files (1.0%)
- `.backup`: 2 files (1.0%)
- `.mjs`: 2 files (1.0%)
- `.original`: 1 files (0.5%)
- `[no_extension]`: 1 files (0.5%)

## BACKEND/FONTEND ANALYSIS
### Backend Files
- `.py`: 56 files

### Frontend Files
- `.tsx`: 46 files
- `.ts`: 16 files
- `.js`: 3 files
- `.css`: 1 files

## API ENDPOINTS FOUND
### `backend/app/api/endpoints/auth.py`
**5 endpoints**
- `POST` `/register` → `register` (line 20)
- `POST` `/login` → `login` (line 56)
- `GET` `/forgot-date-of-birth/{phone}` → `forgot_date_of_birth` (line 103)
- `GET` `/me` → `get_current_user_info` (line 119)
- `PUT` `/me` → `update_current_user_info` (line 124)

### `backend/app/api/endpoints/cart.py`
**7 endpoints**
- `GET` `/` → `get_user_cart` (line 17)
- `POST` `/items` → `add_item_to_cart` (line 68)
- `PUT` `/items/{item_id}` → `update_cart_item` (line 100)
- `DELETE` `/items/{item_id}` → `remove_item_from_cart` (line 134)
- `POST` `/migrate-guest` → `migrate_guest_cart` (line 152)
- ... and 2 more endpoints

### `backend/app/api/endpoints/categories.py`
**6 endpoints**
- `GET` `/` → `read_categories` (line 10)
- `GET` `/{category_id}` → `read_category` (line 18)
- `GET` `/slug/{slug}` → `read_category_by_slug` (line 28)
- `POST` `/` → `create_category` (line 38)
- `PUT` `/{category_id}` → `update_category` (line 45)
- ... and 1 more endpoints

### `backend/app/api/endpoints/debug.py`
**4 endpoints**
- `GET` `/debug/slug-test/{slug:path}` → `debug_slug` (line 9)
- `GET` `/debug/products/count` → `debug_products_count` (line 44)
- `GET` `/debug/products/sample-slugs` → `debug_sample_slugs` (line 59)
- `GET` `/debug/products/search-by-slug/{slug_part:path}` → `debug_search_by_slug` (line 76)

### `backend/app/api/endpoints/fallback.py`
**1 endpoints**
- `GET` `/products/fallback/{product_id}` → `get_product_fallback` (line 8)

### `backend/app/api/endpoints/filters.py`
**1 endpoints**
- `GET` `/filters` → `get_all_filters` (line 11)

### `backend/app/api/endpoints/import_export.py`
**6 endpoints**
- `POST` `/import/excel` → `import_excel` (line 83)
- `GET` `/export/excel` → `UNKNOWN` (line 208)
- `GET` `/export/sample` → `export_sample_excel` (line 320)
- `GET` `/download/export/{filename}` → `download_export_file` (line 367)
- `GET` `/download/latest-export` → `download_latest_export` (line 402)
- ... and 1 more endpoints

### `backend/app/api/endpoints/orders.py`
**10 endpoints**
- `POST` `/` → `create_order` (line 16)
- `GET` `/` → `read_orders` (line 110)
- `GET` `/{order_id}` → `read_order` (line 126)
- `POST` `/{order_id}/pay-deposit` → `pay_deposit` (line 146)
- `POST` `/{order_id}/cancel` → `cancel_order` (line 205)
- ... and 5 more endpoints

### `backend/app/api/endpoints/products.py`
**9 endpoints**
- `GET` `/` → `read_products` (line 12)
- `POST` `/` → `create_product` (line 51)
- `GET` `/{product_id}` → `read_product` (line 61)
- `PUT` `/{product_id}` → `update_product` (line 74)
- `DELETE` `/{product_id}` → `delete_product` (line 88)
- ... and 4 more endpoints

### `backend/app/api/endpoints/user_behavior.py`
**17 endpoints**
- `POST` `/products/view` → `track_product_view` (line 28)
- `GET` `/products/viewed` → `get_viewed_products` (line 38)
- `POST` `/products/favorite` → `add_to_favorites` (line 48)
- `DELETE` `/products/favorite/{product_id}` → `remove_from_favorites` (line 57)
- `GET` `/products/favorites` → `get_favorite_products` (line 69)
- ... and 12 more endpoints

**Total API Endpoints**: 66

## AVAILABLE FILE CONTENTS
**170 files with readable content:**

### `` files (1)
- `backend/.env` (127 lines, 6374 bytes)

### `.backup` files (1)
- `backend/app/api/endpoints/products.py.backup` (120 lines, 3758 bytes)

### `.css` files (1)
- `frontend/app/globals.css` (160 lines, 2941 bytes)

### `.ico` files (1)
- `frontend/app/favicon.ico` (297 lines, 25931 bytes)

### `.js` files (3)
- `frontend/next.config.js` (21 lines, 396 bytes)
- `frontend/postcss.config.js` (7 lines, 142 bytes)
- `frontend/tailwind.config.js` (34 lines, 835 bytes)

### `.json` files (3)
- `backend/api_test_report_20251029_145549.json` (157 lines, 4127 bytes)
- `frontend/package.json` (34 lines, 860 bytes)
- `frontend/tsconfig.json` (44 lines, 778 bytes)

### `.md` files (3)
- `ai_analysis/ai_summary.md` (237 lines, 10327 bytes)
- `frontend/README.md` (36 lines, 1450 bytes)
- `CART_TEST_INSTRUCTIONS.md` (44 lines, 1606 bytes)

### `.mjs` files (1)
- `frontend/postcss.config.mjs` (7 lines, 94 bytes)

### `.original` files (1)
- `backend/app/api/endpoints/products.py.original` (110 lines, 3438 bytes)

### `.py` files (59)
- `backend/app/api/endpoints/__init__.py` (0 lines, 0 bytes)
- `backend/app/api/endpoints/auth.py` (137 lines, 5019 bytes)
- `backend/app/api/endpoints/cart.py` (205 lines, 8133 bytes)
- `backend/app/api/endpoints/categories.py` (63 lines, 2477 bytes)
- `backend/app/api/endpoints/debug.py` (111 lines, 3620 bytes)
- `backend/app/api/endpoints/fallback.py` (28 lines, 1014 bytes)
- `backend/app/api/endpoints/filters.py` (82 lines, 3100 bytes)
- `backend/app/api/endpoints/import_export.py` (513 lines, 18210 bytes)
- `backend/app/api/endpoints/orders.py` (368 lines, 13310 bytes)
- `backend/app/api/endpoints/products.py` (154 lines, 5140 bytes)
- ... and 49 more

### `.sql` files (3)
- `backend/database_migrations/002_add_category_image.sql` (48 lines, 1732 bytes)
- `backend/database_migrations/002_add_user_id_to_cart_items.sql` (25 lines, 818 bytes)
- `backend/database_migrations/003_add_updated_at.sql` (10 lines, 380 bytes)

### `.ts` files (16)
- `frontend/features/auth/api/auth-api.ts` (175 lines, 5034 bytes)
- `frontend/features/auth/api/otp-api.ts` (83 lines, 2429 bytes)
- `frontend/features/auth/types/auth.ts` (44 lines, 1008 bytes)
- `frontend/features/cart/api/cart-api.ts` (96 lines, 2921 bytes)
- `frontend/features/cart/types/cart.ts` (69 lines, 1394 bytes)
- `frontend/features/product/api/product-api.ts` (281 lines, 8833 bytes)
- `frontend/lib/optimization/cache-manager.ts` (70 lines, 1603 bytes)
- `frontend/lib/optimization/image-optimizer.ts` (62 lines, 1747 bytes)
- `frontend/lib/optimization/performance-hooks.ts` (143 lines, 3836 bytes)
- `frontend/lib/api-client.ts` (281 lines, 8409 bytes)
- ... and 6 more

### `.tsx` files (46)
- `frontend/app/admin/orders/page.tsx` (674 lines, 23556 bytes)
- `frontend/app/auth/forgot-date-of-birth/page.tsx` (142 lines, 5747 bytes)
- `frontend/app/auth/login/page.tsx` (15 lines, 485 bytes)
- `frontend/app/auth/register/page.tsx` (15 lines, 500 bytes)
- `frontend/app/cart/page.tsx` (227 lines, 10099 bytes)
- `frontend/app/checkout/page.tsx` (530 lines, 22029 bytes)
- `frontend/app/products/[slug]/components/ErrorState/ErrorState.tsx` (24 lines, 748 bytes)
- `frontend/app/products/[slug]/components/LoadingState/ProductLoading.tsx` (23 lines, 909 bytes)
- `frontend/app/products/[slug]/components/ProductGallery/ProductGallery.tsx` (103 lines, 3784 bytes)
- `frontend/app/products/[slug]/components/ProductHeader/ProductHeader.tsx` (32 lines, 1030 bytes)
- ... and 36 more

### `.txt` files (2)
- `ai_analysis/project_tree.txt` (302 lines, 11972 bytes)
- `backend/requirements.txt` (40 lines, 606 bytes)

### `.xlsx` files (29)
- `backend/app/static/templates/sample_import_template.xlsx` (173 lines, 5914 bytes)
- `backend/app/static/uploads/export_products_20251109_221953.xlsx` (681 lines, 20370 bytes)
- `backend/app/static/uploads/export_products_20251109_221959.xlsx` (685 lines, 20370 bytes)
- `backend/app/static/uploads/export_products_20251109_225844.xlsx` (732 lines, 23833 bytes)
- `backend/app/static/uploads/export_products_20251109_225849.xlsx` (732 lines, 23833 bytes)
- `backend/app/static/uploads/export_products_20251109_233655.xlsx` (711 lines, 23971 bytes)
- `backend/app/static/uploads/export_products_20251109_233700.xlsx` (714 lines, 23971 bytes)
- `backend/app/static/uploads/export_products_20251109_233703.xlsx` (716 lines, 23971 bytes)
- `backend/app/static/uploads/export_products_20251109_234523.xlsx` (797 lines, 24206 bytes)
- `backend/app/static/uploads/export_products_20251109_234528.xlsx` (794 lines, 24203 bytes)
- ... and 19 more