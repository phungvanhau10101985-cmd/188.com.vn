# Huong dan them nguon import tu link san pham

Tai lieu nay ghi lai luong `Import tu link (1688 / Hibox)` de sau nay them nguon moi
(vi du Taobao, Tmall, Shopee, Hibox domain khac, v.v.) khong bi roi vao loi sai source
nhu `Link 1688 khong hop le hoac thieu offerId`.

## Muc tieu cua luong import link

Admin nhap mot URL san pham. Backend tao `ProductImportDraft`, scrape du lieu, chuan hoa ve
`product_data`, sau do admin co the:

- xem/sua draft truoc khi dang san pham;
- publish draft thanh product;
- export Excel dung format import san pham cua web.

Endpoint chinh:

- `POST /api/v1/import-1688/jobs`
- `GET /api/v1/import-1688/jobs/{job_id}`
- `GET /api/v1/import-1688/drafts/{draft_id}`
- `GET /api/v1/import-1688/drafts/{draft_id}/export-excel`
- `GET /api/v1/import-1688/debug/classify-url?url=...` de debug URL

Ten route van la `import-1688` vi day la luong cu, nhung hien tai route nay ho tro nhieu source.

## Port dev cho project nay (mac dinh repo)

- **Backend (FastAPI):** `8001` — `SERVER_PORT` trong `backend/.env`, `dev-clear-start.ps1`, `uvicorn ... --port 8001`.
- **Frontend (Next dev):** `3001` — `frontend/scripts/next-dev.cjs` va `npm run dev`.

Khi dev local, browser goi API (mac dinh khong can `.env.local`):

```text
http://localhost:8001/api/v1
```

Neu ban dung launcher nhieu project (`run_all_projects.bat`, v.v.) va gan port khac, **bat buoc** dat
`NEXT_PUBLIC_API_BASE_URL` + `API_INTERNAL_ORIGIN` trong `frontend/.env.local` **trung** port uvicorn,
roi restart Next. Xem them [HUONG_DAN_CAI_DAT.md](./HUONG_DAN_CAI_DAT.md).

Kiem tra khi lech port / loi `ERR_CONNECTION_REFUSED`:

- `frontend/lib/api-base.ts`
- `frontend/scripts/next-dev.cjs`
- `frontend/next.config.js`
- `frontend/app/api/v1/[[...path]]/route.ts`
- `frontend/.env.local` neu co

Sau khi doi port/env, phai restart Next dev. Next khong tu reload bien `NEXT_PUBLIC_*` da bundle.

## Khi chay tren server / VPS

Tren server, khong nen de frontend goi truc tiep `localhost` tu trinh duyet. Trinh duyet cua admin
nam tren may nguoi dung, nen `localhost` luc do la may cua admin, khong phai VPS. Hay dung mot
trong hai mo hinh duoi day.

### Mo hinh khuyen nghi: cung domain, reverse proxy `/api`

Frontend public:

```text
https://188.com.vn
```

Backend noi bo tren VPS (vi du — khop `SERVER_PORT` / `deploy/update-vps.sh`):

```text
http://127.0.0.1:8001
```

Nginx/Caddy proxy:

```text
https://188.com.vn/api/v1/* -> http://127.0.0.1:8001/api/v1/*
```

Frontend env production:

```env
NEXT_PUBLIC_API_NEXT_PROXY=1
API_INTERNAL_ORIGIN=http://127.0.0.1:8001
NEXT_PUBLIC_API_BASE_URL=
NEXT_PUBLIC_SITE_URL=https://188.com.vn
NEXT_PUBLIC_DOMAIN=https://188.com.vn
```

Ghi chu:

- Co the bo trong `NEXT_PUBLIC_API_BASE_URL` de browser dung cung host `/api/v1`.
- `API_INTERNAL_ORIGIN` chi dung o server Next / rewrite, khong public ra browser.
- Neu build Next voi `NEXT_PUBLIC_API_BASE_URL=http://localhost:8001/api/v1` (hoac bat ky localhost nao), production browser se goi sai — chi dung URL production hoac de trong + proxy.

Vi du Nginx rut gon:

```nginx
server {
    server_name 188.com.vn www.188.com.vn;

    location /api/ {
        proxy_pass http://127.0.0.1:8001/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }

    location / {
        proxy_pass http://127.0.0.1:3001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Mo hinh tach API domain

Frontend:

```text
https://188.com.vn
```

API:

```text
https://api.188.com.vn/api/v1
```

Frontend env:

```env
NEXT_PUBLIC_API_NEXT_PROXY=0
NEXT_PUBLIC_API_BASE_URL=https://api.188.com.vn/api/v1
NEXT_PUBLIC_SITE_URL=https://188.com.vn
NEXT_PUBLIC_DOMAIN=https://188.com.vn
```

Backend `.env` can them CORS:

```env
BACKEND_CORS_ORIGINS=https://188.com.vn,https://www.188.com.vn
```

### Chay process tren server

Khuyen nghi dung PM2 hoac systemd, khong chay tay trong terminal.

Vi du PM2 cho backend:

```powershell
cd G:\python-code\188-com-vn\backend
pm2 start "python -m uvicorn main:app --host 0.0.0.0 --port 8001" --name 188-api
pm2 save
```

Neu Linux/VPS:

```bash
cd /path/to/188-com-vn/backend
pm2 start "python -m uvicorn main:app --host 0.0.0.0 --port 8001" --name 188-api
pm2 save
```

Frontend:

```bash
cd /path/to/188-com-vn/frontend
npm run build
pm2 start "npm run start -- -p 3001" --name 188-web
pm2 save
```

Sau moi lan sua code import source:

```bash
pm2 restart 188-api
pm2 restart 188-web
```

Neu co thay doi `NEXT_PUBLIC_*`, phai build lai frontend:

```bash
cd frontend
npm run build
pm2 restart 188-web
```

### Checklist verify sau deploy

1. Kiem tra backend live co schema moi:

```bash
curl https://188.com.vn/api/v1/openapi.json
```

Neu OpenAPI bi tat production, test route co token admin thay the.

2. Neu OpenAPI bat, dam bao schema co `source`:

```text
Import1688JobCreate: url, download_images, source
```

3. Test classify URL (can Bearer token admin vi route dung permission `products`):

```bash
curl -H "Authorization: Bearer <ADMIN_TOKEN>" \
  "https://188.com.vn/api/v1/import-1688/debug/classify-url?url=https%3A%2F%2Fhibox.mn%2Fv%2Fabb-922386436529"
```

Ket qua ky vong:

```json
{
  "is_hibox": true,
  "hibox_slug": "abb-922386436529",
  "would_accept_for_post_jobs": true
}
```

4. Test tao job:

```bash
curl -X POST "https://188.com.vn/api/v1/import-1688/jobs" \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d "{\"url\":\"https://hibox.mn/v/abb-922386436529\",\"download_images\":false,\"source\":\"hibox\"}"
```

Ky vong HTTP `202` va co `job_id`, `draft_id`.

5. Trong DevTools Network tren admin:

- Request phai di toi domain server dung, khong phai `localhost`.
- Path phai co `/api/v1/import-1688/jobs`.
- Body phai co `source: "hibox"` voi Hibox.

### Loi thuong gap tren server

| Loi | Nguyen nhan hay gap | Cach xu ly |
| --- | --- | --- |
| 404 `/api/v1/import-1688/jobs` | Nginx proxy sai path, goi nham app/web, backend chua restart | Kiem tra route trong OpenAPI, restart `188-api`, xem Nginx `location /api/` |
| 401 debug/classify-url | Thieu Bearer admin token | Login admin lay token hoac test bang UI admin |
| 400 `unsupported_import_link` | URL bi normalize sai hoac source moi chua branch backend | Xem `normalized_preview`, sua detector/normalizer |
| Van bao `thieu offerId` | Job roi vao `scrape_1688_product` | Kiem tra frontend co gui `source`, draft DB co `source`, worker branch source truoc 1688 |
| Browser goi `localhost` production | `NEXT_PUBLIC_API_BASE_URL` build sai | Sua env production, `npm run build`, restart web |
| Timeout khi scrape | Playwright/chromium thieu dependency hoac site cham | Cai Playwright/chromium, tang timeout/proxy_read_timeout |

### Ghi chu Playwright tren server

1688 va Hibox scraper dung Playwright. Server can cai dependency:

```bash
pip install -r backend/requirements.txt
python -m playwright install chromium
```

Tren Linux co the can:

```bash
python -m playwright install --with-deps chromium
```

Neu chay trong Docker/VPS toi gian, loi Playwright se hien trong job `errors` voi dang
`Loi Playwright/Hibox` hoac `Backend chua cai Playwright`.

## Source contract

Khong chi dua vao URL string de doan source. Frontend nen gui ro `source`, backend van phai
co fallback nhan dien URL.

Request body tao job:

```json
{
  "url": "https://hibox.mn/v/abb-922386436529",
  "download_images": false,
  "source": "hibox"
}
```

Quy uoc hien tai: **giu link anh goc** trong draft/export Excel. Khong tu tai anh ve Bunny
o luong import link nay, ke ca khi client gui `download_images=true`. Neu sau nay can upload
Bunny, nen lam thanh hanh dong rieng (vi du nut "Tai anh ve CDN") de admin chu dong chon.

Quy tac hien tai:

| Source | URL mau | `source` gui tu frontend | `download_images` |
| --- | --- | --- | --- |
| `1688` | `https://detail.1688.com/offer/123.html` hoac co `?offerId=123` | `1688` | `false` (giu link goc) |
| `hibox` | `https://hibox.mn/v/abb-922386436529` | `hibox` | `false` |

Backend uu tien:

1. `payload.source == "hibox"` -> chay Hibox.
2. URL chua host `hibox.mn` -> chay Hibox.
3. Neu co `offerId` hoac `/offer/{id}.html` -> chay 1688.
4. Con lai -> 400 `unsupported_import_link`.

Nguyen tac quan trong: **neu URL thuoc source moi thi khong duoc roi xuong scraper 1688**.
Neu path cua source moi sai, hay bao loi source moi, khong bao `thieu offerId`.

## File backend can biet

### Schema request

`backend/app/schemas/import_1688.py`

```py
class Import1688JobCreate(BaseModel):
    url: str = Field(..., min_length=10)
    download_images: bool = True
    source: Optional[str] = None
```

Khi them source moi, khong nhat thiet phai tao endpoint moi. Co the them gia tri `source`
vao body hien tai.

### Router tao job / poll / export

`backend/app/api/endpoints/import_1688.py`

Can sua cac diem:

- import service moi;
- `create_import_1688_job`: phan loai source, tao draft voi `source=...`;
- `_run_import_1688_job`: branch theo `draft.source` hoac URL source moi;
- `_excel_row_from_product`: dam bao product data map dung cot Excel;
- `_publish_payload`: dam bao payload hop schema `ProductCreate`;
- `debug_classify_import_url`: them output debug cho source moi.

Khung them source moi:

```py
if requested_source == "new_source" or is_new_source_url(source_url):
    ext_id = extract_new_source_id(source_url) or "new_source_import"
    src = "new_source"
elif force_hibox or is_hibox_import_url(source_url):
    ext_id = extract_hibox_slug(source_url) or "hibox_import"
    src = "hibox"
else:
    offer_id = extract_offer_id(source_url)
    ...
```

Trong worker:

```py
if saved_source == "new_source" or is_new_source_url(norm_url):
    source = "new_source"
elif saved_source == "hibox" or "hibox.mn" in norm_url.lower() or is_hibox_import_url(norm_url):
    source = "hibox"
else:
    source = saved_source
```

### Service scraper / normalizer source

Moi source nen co service rieng trong:

```text
backend/app/services/import_<source>_scraper.py
```

Service nen expose it nhat 3 ham:

```py
def normalize_<source>_url(raw: str) -> str: ...
def extract_<source>_id(url: str) -> Optional[str]: ...
def scrape_<source>_for_import(source_url: str) -> tuple[dict, dict, list[str]]: ...
```

Trong do `scrape_<source>_for_import` tra ve:

```py
raw_payload, product_data, warnings
```

`product_data` phai tuong thich `ProductCreate` va Excel export.

## Product data shape bat buoc

Draft export dang dung `_excel_row_from_product`, vi vay moi source phai dien cac key chinh:

| Key | Y nghia | Ghi chu |
| --- | --- | --- |
| `product_id` | id san pham duy nhat | Nen prefix source, vd `hibox_<slug>` |
| `code` | SKU | Neu khong co, dung id/slug |
| `origin` | nguon | vd `hibox.mn`, `1688.com` |
| `name` | ten san pham | bat buoc |
| `description` | noi dung mo ta | co the gom thong so |
| `price` | gia numeric | float/int |
| `sizes` | list size | `List[str]` |
| `colors` | bien the mau | `ProductCreate` can `List[Dict]`, vd `{"name": "...", "label": "..."}` |
| `images` | gallery import chinh | Cot `gallery_images` |
| `carousel_images_1688` | anh carousel | Ten cot giu legacy 1688 nhung dung cho moi source |
| `color_swatch_images_1688` | anh mau/mau sac | Tach rieng, khong gop vao gallery |
| `gallery` | anh detail | Cot `detail_images` |
| `detail_block_images_1688` | anh khoi mo ta | Tach rieng |
| `main_image` | anh dai dien | URL dau tien neu co |
| `link_default` | URL nguon | URL da normalize |
| `product_info` | JSON metadata | Nen luu source/raw excerpt |

Khong duoc gop tat ca anh vao mot field. Hien tai can tach:

- carousel/gallery dau trang -> `carousel_images_1688` va `images`;
- anh swatch/mau -> `color_swatch_images_1688`;
- anh mo ta/detail -> `gallery` va/hoac `detail_block_images_1688`.

## File frontend can sua khi them source moi

### Admin page

`frontend/app/admin/products/page.tsx`

Can sua:

- `resolveImportLinkUrl(raw)`: tach URL sach tu text admin dan vao;
- `isHiboxProductUrl` hoac them `isNewSourceProductUrl`;
- `handleImport1688`: gui `source` dung;
- text UI: label, placeholder, toast, error title.

Mau:

```ts
const fromNewSource = isNewSourceProductUrl(url);
const source = fromNewSource ? 'new_source' : fromHibox ? 'hibox' : '1688';
const started = await adminProductAPI.startImport1688(url, source === '1688', source);
```

### API client

`frontend/lib/admin-api.ts`

`startImport1688` phai giu body:

```ts
body: JSON.stringify({ url, download_images: downloadImages, source })
```

Neu them source moi, cap nhat type:

```ts
source?: '1688' | 'hibox' | 'new_source'
```

## Debug khi bi 400 / 404 / thieu offerId

### 400 Bad Request

Mo Network -> request `POST /api/v1/import-1688/jobs` -> tab Response.

Backend tra detail co cac truong:

- `reason`: `url_too_short` hoac `unsupported_import_link`;
- `normalized_preview`: backend nhin URL thanh gi;
- `hints`: goi y sua.

Neu `normalized_preview` khong phai URL mong muon, sua `resolveImportLinkUrl` frontend hoac
`normalize_product_import_url` backend.

### 404

404 khong lien quan offerId. Kiem tra URL chinh xac:

- Dung (mac dinh dev): `http://localhost:8001/api/v1/import-1688/jobs`
- Sai: thieu `/api/v1`, hoac goi nham port khac voi `uvicorn` dang chay

Kiem tra live backend:

```powershell
Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:8001/openapi.json" |
  Select-Object -ExpandProperty Content
```

Hoac xem nhanh schema co `source` chua:

```powershell
$r = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:8001/openapi.json"
$json = $r.Content | ConvertFrom-Json
$json.components.schemas.Import1688JobCreate.properties.PSObject.Properties.Name
```

Neu output khong co `source`, backend dang chay ban cu. Restart uvicorn dung thu muc `backend`.

### Van bao `Link 1688 khong hop le hoac thieu offerId`

Thong bao nay chi nam trong:

```text
backend/app/services/import_1688_scraper.py
```

Nghia la code da goi `scrape_1688_product`. Neu dang dan link source khac, can kiem tra:

- frontend co gui `source` khong;
- backend `create_import_1688_job` co set `src` dung khong;
- `ProductImportDraft.source` trong DB co dung source khong;
- worker `_run_import_1688_job` co branch source moi truoc khi goi 1688 khong;
- backend dang chay co phai code moi khong (`openapi.json` / schema).

## Checklist them source moi

1. Tao service `backend/app/services/import_<source>_scraper.py`.
2. Viet ham normalize URL va extract id.
3. Viet scraper tra `raw_payload, product_data, warnings`.
4. Dien du cac key product data bat buoc, dac biet anh tach cot.
5. Them `source` vao `Import1688JobCreate` type frontend neu can.
6. Sua `frontend/app/admin/products/page.tsx`:
   - detect URL;
   - gui source;
   - cap nhat copy UI.
7. Sua `backend/app/api/endpoints/import_1688.py`:
   - import service;
   - branch create job;
   - branch worker;
   - debug classify URL.
8. Test:
   - `GET /api/v1/import-1688/debug/classify-url?url=...`;
   - `POST /api/v1/import-1688/jobs`;
   - poll job;
   - xem draft;
   - export Excel;
   - publish draft neu source du du lieu.
9. Restart backend va frontend, verify live OpenAPI co schema/route moi.

## Test nhanh Hibox hien tai

URL:

```text
https://hibox.mn/v/abb-922386436529
```

Ky vong:

- frontend gui `source: "hibox"`;
- `download_images: false`;
- backend tao draft `source="hibox"`;
- worker chay `scrape_hibox_for_import`;
- khong bao `thieu offerId`.

Neu co loi scrape Hibox, message phai la `ImportHiboxError` / `Loi Playwright/Hibox`, khong phai loi 1688.
