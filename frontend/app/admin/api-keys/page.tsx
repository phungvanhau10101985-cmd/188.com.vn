'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  adminIntegrationsAPI,
  type AdminIntegrationKeysOverview,
} from '@/lib/admin-api';
import { getApiBaseUrl, getBackendOriginUrl, getCatalogFeedApiBaseUrl } from '@/lib/api-base';

/** Base API công khai shop — dùng trong tài liệu tích hợp cho đối tác / cron server */
const PRODUCTION_PRODUCTS_API_BASE = 'https://188.com.vn/api/v1';
const PRODUCTION_SHIPPING_LOOKUP_URL = `${PRODUCTION_PRODUCTS_API_BASE}/shipping/lookup`;

const CURL_SHIPPING_ORDER = `curl -sS -H "X-Api-Key: YOUR_KEY" \\
  "${PRODUCTION_SHIPPING_LOOKUP_URL}?q=DH042"`;

const CURL_SHIPPING_PHONE = `curl -sS -H "X-Api-Key: YOUR_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"phone":"0901234567"}' \\
  "${PRODUCTION_SHIPPING_LOOKUP_URL}"`;

const CURL_SHIPPING_EMS = `curl -sS -H "Authorization: Bearer YOUR_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"ems_code":"EH042737692VN"}' \\
  "${PRODUCTION_SHIPPING_LOOKUP_URL}"`;

const SHIPPING_LOOKUP_ROWS: { method: string; suffix: string; note: string }[] = [
  {
    method: 'GET',
    suffix: '/shipping/lookup?q=DH042',
    note: 'Mã đơn web — chi tiết đơn + mã vận đơn + timeline shop + EMS (nếu có).',
  },
  {
    method: 'GET',
    suffix: '/shipping/lookup?q=0901234567',
    note: 'Số điện thoại khách — trả đơn gần nhất (chuẩn hoá 09 / 84 / +84).',
  },
  {
    method: 'GET',
    suffix: '/shipping/lookup?q=EH042737692VN',
    note: 'Mã EMS — hành trình live MyEMS (mọi mốc trạng thái) + đơn shop nếu đã ghép.',
  },
  {
    method: 'POST',
    suffix: '/shipping/lookup',
    note: 'JSON: { "q" } hoặc { "order_code" } / { "phone" } / { "ems_code" }. Ưu tiên ems_code > order_code > phone > q.',
  },
];

const CURL_FULL_LIST_EXAMPLE = `curl -sS "${PRODUCTION_PRODUCTS_API_BASE}/products/list/full?skip=0&limit=500&is_active=true"`;

const NODE_FETCH_PAGINATION_EXAMPLE = `const base = '${PRODUCTION_PRODUCTS_API_BASE}';
const limit = 500; // tối đa 1000 mỗi lần
let skip = 0;
const all = [];
for (;;) {
  const u = new URL(base + '/products/list/full');
  u.searchParams.set('skip', String(skip));
  u.searchParams.set('limit', String(limit));
  u.searchParams.set('is_active', 'true');
  const res = await fetch(u);
  if (!res.ok) throw new Error(await res.text());
  const data = await res.json();
  const batch = Array.isArray(data.products) ? data.products : [];
  all.push(...batch);
  const total = Number(data.total) || 0;
  skip += limit;
  if (batch.length === 0 || skip >= total) break;
}
// all: toàn bộ sản phẩm active`;

const PRODUCT_REST_ROWS: { method: string; suffix: string; note: string }[] = [
  {
    method: 'GET',
    suffix: '/products/',
    note: 'Danh sách + lọc: skip, limit, category, subcategory, shop_name, min_price, q, product_id, sort, order_random, … — trả về JSON (products, total, phân trang).',
  },
  {
    method: 'GET',
    suffix: '/products/list/full',
    note: 'Danh sách cùng bộ tham số như trên nhưng mỗi phần tử đủ trường schema Product (category_id, raw_*, product_info, SEO, ảnh, …); không đọc/ghi cache tìm theo q.',
  },
  {
    method: 'GET',
    suffix: '/products/search/',
    note: 'Tìm kiếm nâng cao (q, redirect danh mục, gợi ý…).',
  },
  {
    method: 'GET',
    suffix: '/products/{product_id}',
    note: 'Chi tiết: product_id (Excel) hoặc slug.',
  },
  {
    method: 'GET',
    suffix: '/products/by-slug/{slug}',
    note: 'Chi tiết theo slug (path).',
  },
  {
    method: 'GET',
    suffix: '/products/by-slug/?slug=',
    note: 'Chi tiết theo slug (query).',
  },
  {
    method: 'GET',
    suffix: '/products/by-code/{product_code}',
    note: 'Theo mã / product_id.',
  },
  {
    method: 'GET',
    suffix: '/products/by-id/{id}',
    note: 'Theo khóa số id trong CSDL.',
  },
];

export default function AdminApiKeysPage() {
  const [data, setData] = useState<AdminIntegrationKeysOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [apiBase, setApiBase] = useState('');
  const [docsOrigin, setDocsOrigin] = useState('');
  const [catalogPublicBase, setCatalogPublicBase] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const out = await adminIntegrationsAPI.getApiKeysOverview();
      setData(out);
    } catch (e) {
      setError((e as Error)?.message || 'Không tải được dữ liệu');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    setApiBase(getApiBaseUrl());
    setDocsOrigin(getBackendOriginUrl());
    setCatalogPublicBase(getCatalogFeedApiBaseUrl());
  }, []);

  const productExampleUrls = useMemo(() => {
    if (!apiBase) return [];
    const base = apiBase.replace(/\/$/, '');
    return PRODUCT_REST_ROWS.map((r) => ({
      ...r,
      full: `${base}${r.suffix.replace(/\/{2,}/g, '/')}`,
    }));
  }, [apiBase]);

  const shippingExampleUrls = useMemo(() => {
    if (!apiBase) return [];
    const base = apiBase.replace(/\/$/, '');
    return SHIPPING_LOOKUP_ROWS.map((r) => ({
      ...r,
      full: `${base}${r.suffix}`,
    }));
  }, [apiBase]);

  const shippingKeyRow = useMemo(
    () =>
      data?.groups
        ?.flatMap((g) => g.items)
        .find((row) => row.env_var === 'SHIPPING_LOOKUP_API_KEY') ?? null,
    [data],
  );

  return (
    <div className="p-6 max-w-4xl">
      <h1 className="text-xl font-bold text-gray-900 mb-1">API &amp; tích hợp</h1>
      <p className="text-sm text-gray-600 mb-6">
        Tra cứu cổng REST (sản phẩm, vận chuyển) và trạng thái cấu hình khóa trên backend.
      </p>

      <section className="mb-10" aria-labelledby="shipping-api-heading">
        <h2 id="shipping-api-heading" className="text-sm font-semibold text-gray-800 mb-2">
          Cổng REST — Tra cứu vận chuyển (partner)
        </h2>
        <p className="text-sm text-gray-600 mb-3">
          Một endpoint cho chatbot / CS / kho: mã đơn web, SĐT khách (đơn gần nhất), hoặc mã EMS (hành trình đầy đủ).
          Cần API key — không gọi từ trình duyệt khách.
        </p>
        <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
          {shippingKeyRow ? (
            shippingKeyRow.configured ? (
              <span className="inline-flex items-center rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-medium text-emerald-900">
                Đã cấu hình SHIPPING_LOOKUP_API_KEY
              </span>
            ) : (
              <span className="inline-flex items-center rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-950">
                Chưa bật — thiếu SHIPPING_LOOKUP_API_KEY
              </span>
            )
          ) : loading ? (
            <span className="text-xs text-gray-500">Đang kiểm tra cấu hình…</span>
          ) : null}
          {apiBase ? (
            <code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">{apiBase}/shipping/lookup</code>
          ) : (
            <span className="text-gray-400 text-xs">(đang xác định base URL…)</span>
          )}
        </div>
        {docsOrigin ? (
          <p className="text-xs text-gray-600 mb-4">
            OpenAPI (Swagger):{' '}
            <a
              href={`${docsOrigin.replace(/\/$/, '')}/docs#/shipping-lookup`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-700 underline"
            >
              {docsOrigin.replace(/\/$/, '')}/docs
            </a>{' '}
            — nhóm tag <strong>shipping-lookup</strong>.
          </p>
        ) : null}
        <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white shadow-sm">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50 text-left text-gray-600">
                <th className="px-4 py-2 font-medium whitespace-nowrap">Method</th>
                <th className="px-4 py-2 font-medium">Đường dẫn &amp; ví dụ URL</th>
                <th className="px-4 py-2 font-medium">Ghi chú</th>
              </tr>
            </thead>
            <tbody>
              {(shippingExampleUrls.length
                ? shippingExampleUrls
                : SHIPPING_LOOKUP_ROWS.map((r) => ({ ...r, full: '' }))
              ).map((row) => (
                <tr key={`${row.method}-${row.suffix}`} className="border-b border-gray-100 last:border-0">
                  <td className="px-4 py-3 align-top whitespace-nowrap">
                    <span className="rounded bg-slate-200 px-2 py-0.5 text-xs font-mono">{row.method}</span>
                  </td>
                  <td className="px-4 py-3 align-top">
                    <code className="text-xs text-gray-900 break-all">{row.suffix}</code>
                    {row.full ? (
                      <div className="mt-1 text-[11px] text-gray-500 break-all">{row.full}</div>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 align-top text-gray-700 text-xs">{row.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs text-gray-600">
          Auth: header <code className="bg-gray-100 px-1 rounded">X-Api-Key</code> hoặc{' '}
          <code className="bg-gray-100 px-1 rounded">Authorization: Bearer {'<'}key{'>'}</code>. Key đặt trong{' '}
          <code className="bg-gray-100 px-1 rounded">SHIPPING_LOOKUP_API_KEY</code> (nhiều key cách nhau bằng dấu phẩy).
        </p>

        <div className="mt-8 rounded-lg border border-blue-200 bg-blue-50/80 px-4 py-4 text-sm text-gray-800">
          <h3 id="integration-guide-shipping" className="text-base font-semibold text-gray-900 mb-2">
            Hướng dẫn tích hợp: tra cứu vận chuyển
          </h3>
          <p className="text-gray-700 mb-3">
            Dùng cho đối tác, chatbot, CS — <strong>bắt buộc API key</strong>. Gọi từ server, không nhúng key lên frontend
            khách.
          </p>
          <ol className="list-decimal pl-5 space-y-3 text-gray-800">
            <li>
              <strong>Base URL production</strong>
              <p className="mt-1 text-xs text-gray-600">
                <code className="bg-white/90 px-1.5 py-0.5 rounded text-[13px]">{PRODUCTION_SHIPPING_LOOKUP_URL}</code>
              </p>
            </li>
            <li>
              <strong>Ba kiểu đầu vào</strong>
              <ul className="mt-1 list-disc pl-5 text-xs text-gray-600 space-y-1">
                <li>
                  <code className="bg-white/80 px-1 rounded">q=DH042</code> hoặc{' '}
                  <code className="bg-white/80 px-1 rounded">order_code</code> — chi tiết đơn + vận chuyển.
                </li>
                <li>
                  <code className="bg-white/80 px-1 rounded">q=0901234567</code> hoặc{' '}
                  <code className="bg-white/80 px-1 rounded">phone</code> — đơn gần nhất của SĐT.
                </li>
                <li>
                  <code className="bg-white/80 px-1 rounded">q=EH…VN</code> hoặc{' '}
                  <code className="bg-white/80 px-1 rounded">ems_code</code> — live EMS (mọi mốc) + đơn shop nếu có.
                </li>
              </ul>
            </li>
            <li>
              <strong>Trường dùng ngay</strong>
              <ul className="mt-1 list-disc pl-5 text-xs text-gray-600 space-y-1">
                <li>
                  <code className="bg-white/80 px-1 rounded">tracking_number</code>,{' '}
                  <code className="bg-white/80 px-1 rounded">order.status_label</code>,{' '}
                  <code className="bg-white/80 px-1 rounded">order.items</code>
                </li>
                <li>
                  <code className="bg-white/80 px-1 rounded">ems_tracking.current_status_description</code> +{' '}
                  <code className="bg-white/80 px-1 rounded">ems_tracking.events</code> (mới nhất trước)
                </li>
                <li>
                  Tra SĐT: <code className="bg-white/80 px-1 rounded">is_latest_order: true</code>
                </li>
              </ul>
            </li>
            <li>
              <strong>Ví dụ — mã đơn</strong>
              <pre className="mt-2 overflow-x-auto rounded-md bg-slate-900 text-slate-100 p-3 text-[11px] leading-relaxed whitespace-pre">
                {CURL_SHIPPING_ORDER}
              </pre>
            </li>
            <li>
              <strong>Ví dụ — số điện thoại (đơn gần nhất)</strong>
              <pre className="mt-2 overflow-x-auto rounded-md bg-slate-900 text-slate-100 p-3 text-[11px] leading-relaxed whitespace-pre">
                {CURL_SHIPPING_PHONE}
              </pre>
            </li>
            <li>
              <strong>Ví dụ — mã EMS (hành trình đầy đủ)</strong>
              <pre className="mt-2 overflow-x-auto rounded-md bg-slate-900 text-slate-100 p-3 text-[11px] leading-relaxed whitespace-pre">
                {CURL_SHIPPING_EMS}
              </pre>
            </li>
            <li>
              <strong>Lỗi thường gặp</strong>
              <ul className="mt-1 list-disc pl-5 text-xs text-gray-600 space-y-1">
                <li>
                  <code className="bg-white/80 px-1 rounded">401</code> sai/thiếu key ·{' '}
                  <code className="bg-white/80 px-1 rounded">404</code> không tìm thấy ·{' '}
                  <code className="bg-white/80 px-1 rounded">503</code> chưa đặt{' '}
                  <code className="bg-white/80 px-1 rounded">SHIPPING_LOOKUP_API_KEY</code> (cần restart backend sau khi sửa
                  .env).
                </li>
                <li>CORS: gọi từ domain khác có thể bị chặn — gọi từ server đối tác.</li>
              </ul>
            </li>
          </ol>
        </div>
      </section>

      <section className="mb-10" aria-labelledby="product-api-heading">
        <h2 id="product-api-heading" className="text-sm font-semibold text-gray-800 mb-2">
          Cổng REST — Sản phẩm (đọc công khai)
        </h2>
        <p className="text-sm text-gray-600 mb-3">
          Các endpoint dưới đây không cần đăng nhập để đọc. Base URL hiện tại trên trình duyệt:{' '}
          {apiBase ? (
            <code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">{apiBase}</code>
          ) : (
            <span className="text-gray-400">(đang xác định…)</span>
          )}
        </p>
        {docsOrigin ? (
          <p className="text-xs text-gray-600 mb-4">
            OpenAPI (Swagger):{' '}
            <a
              href={`${docsOrigin.replace(/\/$/, '')}/docs`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-700 underline"
            >
              {docsOrigin.replace(/\/$/, '')}/docs
            </a>{' '}
            — nhóm tag <strong>products</strong>. Trên dev, nếu Next chỉ proxy <code className="text-[11px]">/api/v1</code>, trang{' '}
            <code className="text-[11px]">/docs</code> thường mở trực tiếp cổng FastAPI (vd.{' '}
            <code className="text-[11px]">http://127.0.0.1:8001/docs</code>).
          </p>
        ) : null}
        <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white shadow-sm">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50 text-left text-gray-600">
                <th className="px-4 py-2 font-medium whitespace-nowrap">Method</th>
                <th className="px-4 py-2 font-medium">Đường dẫn &amp; ví dụ URL</th>
                <th className="px-4 py-2 font-medium">Ghi chú</th>
              </tr>
            </thead>
            <tbody>
              {(productExampleUrls.length ? productExampleUrls : PRODUCT_REST_ROWS.map((r) => ({ ...r, full: '' }))).map(
                (row) => (
                <tr key={row.suffix} className="border-b border-gray-100 last:border-0">
                  <td className="px-4 py-3 align-top whitespace-nowrap">
                    <span className="rounded bg-slate-200 px-2 py-0.5 text-xs font-mono">{row.method}</span>
                  </td>
                  <td className="px-4 py-3 align-top">
                    <code className="text-xs text-gray-900 break-all">{row.suffix}</code>
                    {row.full ? (
                      <div className="mt-1 text-[11px] text-gray-500 break-all">{row.full}</div>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 align-top text-gray-700 text-xs">{row.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs text-gray-600">
          Thao tác ghi (tạo / sửa / xóa sản phẩm) cần header{' '}
          <code className="bg-gray-100 px-1 rounded">Authorization: Bearer {'<'}admin_token{'>'}</code>.
        </p>

        <div className="mt-8 rounded-lg border border-blue-200 bg-blue-50/80 px-4 py-4 text-sm text-gray-800">
          <h3 id="integration-guide-products" className="text-base font-semibold text-gray-900 mb-2">
            Hướng dẫn tích hợp: đọc toàn bộ danh sách sản phẩm (188.com.vn)
          </h3>
          <p className="text-gray-700 mb-3">
            Dùng cho đối tác, feed nội bộ, hoặc script trên server — API đọc danh sách/ chi tiết sản phẩm{' '}
            <strong>không yêu cầu API key</strong>. Chỉ các thao tác quản trị ghi dữ liệu mới cần JWT admin.
          </p>

          <ol className="list-decimal pl-5 space-y-3 text-gray-800">
            <li>
              <strong>Base URL production (HTTPS công khai)</strong>
              <p className="mt-1 text-xs text-gray-600">
                Gọi từ cron / backend đối tác:{' '}
                <code className="bg-white/90 px-1.5 py-0.5 rounded text-[13px]">{PRODUCTION_PRODUCTS_API_BASE}</code>
              </p>
              {catalogPublicBase && catalogPublicBase !== PRODUCTION_PRODUCTS_API_BASE ? (
                <p className="mt-1 text-xs text-amber-900">
                  Build / env hiện tại dùng catalog:{' '}
                  <code className="bg-amber-100/80 px-1 rounded">{catalogPublicBase}</code> — khi test staging hãy
                  thay thế cho URL production trong ví dụ.
                </p>
              ) : null}
            </li>
            <li>
              <strong>Endpoint khuyến nghị cho danh sách đầy đủ trường</strong>
              <p className="mt-1 text-xs text-gray-600">
                <code className="bg-white/90 px-1.5 py-0.5 rounded">GET /products/list/full</code> — cùng bộ tham số
                lọc như <code className="bg-white/90 px-1 rounded">GET /products/</code> nhưng mỗi phần tử đủ các trường
                khớp schema (danh mục, SEO, ảnh, <code className="text-[11px]">product_info</code>, …). Với danh sách
                gọn hơn (ít trường hơn khi serialize cache), dùng <code className="bg-white/90 px-1 rounded">GET /products/</code>.
              </p>
            </li>
            <li>
              <strong>Phân trang — lấy hết catalog</strong>
              <ul className="mt-1 list-disc pl-5 text-xs text-gray-600 space-y-1">
                <li>
                  Tham số <code className="bg-white/80 px-1 rounded">skip</code> (bắt đầu từ 0) và{' '}
                  <code className="bg-white/80 px-1 rounded">limit</code> (từ 1 đến <strong>1000</strong> mỗi request).
                </li>
                <li>
                  Response có <code className="bg-white/80 px-1 rounded">total</code>,{' '}
                  <code className="bg-white/80 px-1 rounded">products</code>, <code className="bg-white/80 px-1 rounded">page</code>,{' '}
                  <code className="bg-white/80 px-1 rounded">size</code>, <code className="bg-white/80 px-1 rounded">total_pages</code>.
                </li>
                <li>
                  Lặp: tăng <code className="bg-white/80 px-1 rounded">skip</code> sau mỗi lần (vd.{' '}
                  <code className="bg-white/80 px-1 rounded">skip += limit</code>) cho đến khi đã tải đủ{' '}
                  <code className="bg-white/80 px-1 rounded">total</code> phần tử hoặc batch rỗng.
                </li>
                <li>
                  Mặc định <code className="bg-white/80 px-1 rounded">is_active=true</code> — chỉ sản phẩm đang bật. Đặt{' '}
                  <code className="bg-white/80 px-1 rounded">is_active=false</code> nếu cần cả SP tắt (khi có quyền / use
                  case nội bộ).
                </li>
              </ul>
            </li>
            <li>
              <strong>Ví dụ — dòng lệnh (curl)</strong>
              <pre className="mt-2 overflow-x-auto rounded-md bg-slate-900 text-slate-100 p-3 text-[11px] leading-relaxed">
                {CURL_FULL_LIST_EXAMPLE}
              </pre>
            </li>
            <li>
              <strong>Ví dụ — Node.js / server (fetch + vòng lặp)</strong>
              <pre className="mt-2 overflow-x-auto rounded-md bg-slate-900 text-slate-100 p-3 text-[11px] leading-relaxed whitespace-pre-wrap">
                {NODE_FETCH_PAGINATION_EXAMPLE}
              </pre>
            </li>
            <li>
              <strong>Chi tiết một sản phẩm</strong>
              <p className="mt-1 text-xs text-gray-600">
                Sau khi có <code className="bg-white/90 px-1 rounded">slug</code> hoặc{' '}
                <code className="bg-white/90 px-1 rounded">product_id</code> từ danh sách:{' '}
                <code className="bg-white/90 px-1 rounded">GET …/products/by-slug/?slug=...</code> hoặc{' '}
                <code className="bg-white/90 px-1 rounded">GET …/products/{'{'}product_id{'}'}</code> (xem bảng phía trên).
              </p>
            </li>
            <li>
              <strong>Lưu ý kỹ thuật</strong>
              <ul className="mt-1 list-disc pl-5 text-xs text-gray-600 space-y-1">
                <li>
                  <strong>CORS:</strong> gọi API từ trình duyệt trên <em>domain khác</em> 188.com.vn có thể bị chặn. Cách
                  an toàn: gọi từ server đối tác (cron, worker) hoặc yêu cầu kỹ thuật bổ sung origin vào{' '}
                  <code className="bg-white/80 px-1 rounded">BACKEND_CORS_ORIGINS</code> trên backend.
                </li>
                <li>
                  <strong>Cache:</strong> một số request có <code className="bg-white/80 px-1 rounded">Cache-Control: public</code>{' '}
                  ngắn; <code className="bg-white/80 px-1 rounded">/products/list/full</code> không dùng cache tìm theo{' '}
                  <code className="bg-white/80 px-1 rounded">q</code> như bản list thường.
                </li>
                <li>
                  <strong>Tải có trách nhiệm:</strong> tránh vòng lặp song song lớn; giữ <code className="bg-white/80 px-1 rounded">limit</code>{' '}
                  hợp lý (vd. 200–500) để giảm tải server.
                </li>
              </ul>
            </li>
          </ol>
        </div>
      </section>

      <h2 className="text-sm font-semibold text-gray-800 mb-2">Trạng thái biến môi trường (backend)</h2>
      <p className="text-sm text-gray-600 mb-4">
        Không hiển thị giá trị bí mật — chỉ đã cấu hình hay chưa.
      </p>

      {loading ? (
        <p className="text-sm text-gray-500" role="status">
          Đang tải…
        </p>
      ) : null}

      {error ? (
        <div
          className="mb-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
          role="alert"
        >
          {error}{' '}
          <button type="button" onClick={() => void load()} className="underline font-medium">
            Thử lại
          </button>
        </div>
      ) : null}

      {data?.disclaimer ? (
        <p className="mb-6 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
          {data.disclaimer}
        </p>
      ) : null}

      {data?.groups?.length ? (
        <div className="space-y-8">
          {data.groups.map((g) => (
            <section key={g.title} aria-labelledby={`grp-${g.title}`}>
              <h2 id={`grp-${g.title}`} className="text-sm font-semibold text-gray-800 mb-3">
                {g.title}
              </h2>
              <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white shadow-sm">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 bg-gray-50 text-left text-gray-600">
                      <th className="px-4 py-2 font-medium">Biến môi trường</th>
                      <th className="px-4 py-2 font-medium">Mô tả</th>
                      <th className="px-4 py-2 font-medium whitespace-nowrap">Trạng thái</th>
                      <th className="px-4 py-2 font-medium">Gợi ý</th>
                    </tr>
                  </thead>
                  <tbody>
                    {g.items.map((row) => (
                      <tr key={row.env_var} className="border-b border-gray-100 last:border-0">
                        <td className="px-4 py-3 align-top">
                          <code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded text-gray-800">
                            {row.env_var}
                          </code>
                        </td>
                        <td className="px-4 py-3 align-top text-gray-800">{row.label}</td>
                        <td className="px-4 py-3 align-top whitespace-nowrap">
                          {row.configured ? (
                            <span className="inline-flex items-center rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-medium text-emerald-900">
                              Đã cấu hình
                            </span>
                          ) : (
                            <span className="inline-flex items-center rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-950">
                              Chưa / thiếu
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3 align-top text-gray-600 text-xs">
                          {row.hint || '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ))}
        </div>
      ) : null}

      {!loading && !error && !data?.groups?.length ? (
        <p className="text-sm text-gray-500">Không có dữ liệu nhóm.</p>
      ) : null}
    </div>
  );
}
