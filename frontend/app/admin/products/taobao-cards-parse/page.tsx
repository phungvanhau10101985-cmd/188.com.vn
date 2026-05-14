'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  DEFAULT_VND_PER_CNY_FOR_LISTING_ESTIMATE,
  estimateListingVndRounded,
  parseTaobaoListingHtml,
  rowsToCsv,
  type ParsedTaobaoCardRow,
} from '@/lib/taobao-cards-html-parse';
import { adminProductAPI } from '@/lib/admin-api';

/** Chuẩn hoá như backend (A|T + chỉ chữ số). */
function normalizeListingParserItemId(raw: string): string {
  const t = raw.trim();
  const m = t.match(/^([aAtT])(\d+)$/);
  if (m) return `${m[1].toUpperCase()}${m[2]}`;
  return t;
}

/**
 * Kiểm tra các ký tự của needle (so khớp không phân biệt hoa thường Latin) xuất hiện
 * trong haystack đúng thứ tự — giữa hai ký tự được phép chen ký tự khác.
 */
function isSubsequenceIgnoreCase(needle: string, haystack: string): boolean {
  if (!needle) return true;
  const n = needle.toLowerCase();
  const h = (haystack || '').toLowerCase();
  let i = 0;
  for (let j = 0; j < h.length && i < n.length; j++) {
    if (h[j] === n[i]) i += 1;
  }
  return i === n.length;
}

/** Lọc tiêu đề không cần liên tục; vài cụm cách bằng khoảng trắng → mỗi cụm phải thỏa (AND). */
function titleMatchesFlexibleFilter(titleRaw: string, filterTrimmed: string): boolean {
  const parts = filterTrimmed.toLowerCase().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return true;
  const title = titleRaw || '';
  return parts.every((chunk) => isSubsequenceIgnoreCase(chunk, title));
}

function formatVndApproxCell(n: number | null): string {
  if (n == null || !Number.isFinite(n)) return '—';
  return new Intl.NumberFormat('vi-VN').format(n) + ' ₫';
}

export default function TaobaoCardsParsePage() {
  const [raw, setRaw] = useState('');
  const [rows, setRows] = useState<ParsedTaobaoCardRow[]>([]);
  const [shopFilter, setShopFilter] = useState('');
  const [titleFilter, setTitleFilter] = useState('');
  const [rateInput, setRateInput] = useState(() => String(DEFAULT_VND_PER_CNY_FOR_LISTING_ESTIMATE));
  const [onlyMissingInDb, setOnlyMissingInDb] = useState(true);
  const [dbExistingSet, setDbExistingSet] = useState<Set<string>>(() => new Set());
  const [presenceFetchKey, setPresenceFetchKey] = useState<string | null>(null);
  const [dbLookupPending, setDbLookupPending] = useState(false);
  const [dbLookupError, setDbLookupError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const parse = useCallback(() => {
    setError(null);
    setCopied(false);
    setDbLookupError(null);
    setPresenceFetchKey(null);
    setDbExistingSet(new Set());
    const t = raw.trim();
    if (!t) {
      setRows([]);
      setError('Hãy dán HTML hoặc đoạn DOM (View Source / Copy outerHTML) vào ô bên dưới.');
      return;
    }
    try {
      const out = parseTaobaoListingHtml(t);
      setRows(out);
      setShopFilter('');
      setTitleFilter('');
      if (out.length === 0) {
        setError(
          'Không trích được dòng nào từ HTML này. Taobao listing PC 2025+: `<a class="doubleCardWrapperAdapt…">`, `id="item_id_…"`, `mainPic`/`priceInt`. 1688 selloffer (s.1688.com): `<a class="search-offer-wrapper…">`, `offerId=` / `detail.m.1688.com`, `img.main-img`, `offer-title-row`. Cũng hỗ trợ cardContainer / mainImage / ảnh alicdn kèm giá-tiêu đề. Copy outerHTML `#content_items_wrapper` hoặc nhiều card; nếu không có `item.htm`/`offerId`/ảnh hoặc chỉ text SPA thì không có dữ liệu.',
        );
      }
    } catch (e) {
      setRows([]);
      setPresenceFetchKey(null);
      setDbExistingSet(new Set());
      setError(e instanceof Error ? e.message : 'Lỗi parse');
    }
  }, [raw]);

  const shopFilterTrimmed = shopFilter.trim();
  const titleFilterTrimmed = titleFilter.trim();

  const effectiveRate = useMemo(() => {
    const n = Number(String(rateInput ?? '').trim().replace(/\s+/g, '').replace(',', '.'));
    if (!Number.isFinite(n) || n <= 0) return DEFAULT_VND_PER_CNY_FOR_LISTING_ESTIMATE;
    return n;
  }, [rateInput]);

  /** Sau lọc shop + tiêu đề (trước lọc DB). */
  const preDbFilteredRows = useMemo(() => {
    let xs = rows;
    if (shopFilterTrimmed) {
      const q = shopFilterTrimmed.toLowerCase();
      xs = xs.filter((r) => (r.shop_name || '').toLowerCase().includes(q));
    }
    if (titleFilterTrimmed) {
      xs = xs.filter((r) => titleMatchesFlexibleFilter(r.title || '', titleFilterTrimmed));
    }
    return xs;
  }, [rows, shopFilterTrimmed, titleFilterTrimmed]);

  const idsForDbLookupKey = useMemo(
    () =>
      [...new Set(rows.map((r) => normalizeListingParserItemId(r.item_id)).filter(Boolean))]
        .sort()
        .join('|'),
    [rows],
  );

  useEffect(() => {
    if (!onlyMissingInDb || rows.length === 0 || !idsForDbLookupKey) {
      return;
    }
    const ids = idsForDbLookupKey.split('|').filter(Boolean);
    let active = true;
    setDbLookupPending(true);
    setDbLookupError(null);
    void adminProductAPI
      .listingParserDbPresence(ids)
      .then((res) => {
        if (!active) return;
        setDbExistingSet(new Set(res.existing_normalized ?? []));
        setPresenceFetchKey(idsForDbLookupKey);
      })
      .catch((err: unknown) => {
        if (!active) return;
        const msg =
          err instanceof Error
            ? err.message
            : 'Không đối chiếu được DB (kiểm tra mạng và quyền module sản phẩm).';
        setDbLookupError(msg);
        setOnlyMissingInDb(false);
        setPresenceFetchKey(null);
        setDbExistingSet(new Set());
      })
      .finally(() => {
        if (active) setDbLookupPending(false);
      });
    return () => {
      active = false;
    };
  }, [onlyMissingInDb, idsForDbLookupKey, rows.length]);

  const dbPresenceReady =
    onlyMissingInDb &&
    presenceFetchKey === idsForDbLookupKey &&
    !dbLookupPending &&
    !!idsForDbLookupKey;

  const displayRows = useMemo(() => {
    let xs = preDbFilteredRows;
    if (onlyMissingInDb && dbPresenceReady) {
      xs = xs.filter((r) => !dbExistingSet.has(normalizeListingParserItemId(r.item_id)));
    }
    return xs;
  }, [preDbFilteredRows, onlyMissingInDb, dbPresenceReady, dbExistingSet]);

  const csv = useMemo(
    () => (displayRows.length ? rowsToCsv(displayRows, effectiveRate) : ''),
    [displayRows, effectiveRate],
  );

  const downloadCsv = useCallback(() => {
    if (!csv) return;
    const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `taobao_listing_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [csv]);

  const copyCsv = useCallback(async () => {
    if (!csv) return;
    try {
      await navigator.clipboard.writeText(csv);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      setError('Không copy được vào clipboard (trình duyệt chặn). Dùng «Tải CSV».');
    }
  }, [csv]);

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">HTML listing → một dòng một sản phẩm</h1>
        <p className="text-sm text-slate-600 mt-1 max-w-3xl">
          Dán HTML (hoặc outerHTML của vùng danh sách) từ trang Taobao/Tmall — công cụ khớp{' '}
          <code className="text-xs bg-slate-100 px-1 rounded">cardContainer–…</code>,{' '}
          <code className="text-xs bg-slate-100 px-1 rounded">doubleCardWrapperAdapt</code>,{' '}
          <code className="text-xs bg-slate-100 px-1 rounded">mainImg</code> hoặc ảnh alicdn trong cùng
          một khối có giá/tiêu đề.{' '}
          Mỗi card → một hàng: ID sản phẩm, link SP, ảnh chính, tiêu đề, tên shop, tag, giá nhân dân tệ, cột quy đổi{' '}
          ~VNĐ ≈ làm tròn(CN¥ × hệ số lưới × tỷ giá ô trên toolbar; VNĐ / 1 CN¥). CSV thêm các cột
          price_cny_approx, cny_exchange_multiplier, vnd_per_cny_used, approx_vnd.
          {' '}
          <span className="text-slate-700">
            Mặc định sau khi parse, danh sách chỉ giữ các ID chưa có trong DB (có thể bỏ chọn để xem cả lô).
          </span>
        </p>
      </div>

      <textarea
        className="w-full min-h-[200px] rounded-lg border border-slate-300 px-3 py-2 text-sm font-mono"
        placeholder="Dán HTML vào đây…"
        value={raw}
        onChange={(e) => setRaw(e.target.value)}
        aria-label="HTML listing Taobao để parse"
      />

      <div className="flex flex-wrap gap-2 items-center">
        <button
          type="button"
          onClick={parse}
          className="px-4 py-2 rounded-lg bg-slate-800 text-white text-sm font-medium hover:bg-slate-900"
        >
          Parse → bảng
        </button>
        <button
          type="button"
          disabled={!displayRows.length}
          onClick={downloadCsv}
          className="px-4 py-2 rounded-lg border border-slate-300 text-sm font-medium disabled:opacity-50"
        >
          Tải CSV (UTF‑8 BOM)
        </button>
        <button
          type="button"
          disabled={!displayRows.length}
          onClick={() => void copyCsv()}
          className="px-4 py-2 rounded-lg border border-slate-300 text-sm font-medium disabled:opacity-50"
        >
          {copied ? 'Đã copy' : 'Copy CSV'}
        </button>
        <span className="text-sm text-slate-500">
          {rows.length > 0 ? (
            <>
              Hiển thị{' '}
              <span className="font-medium tabular-nums text-slate-700">{displayRows.length}</span>
              {rows.length !== displayRows.length ? (
                <>
                  {' '}
                  / <span className="tabular-nums">{rows.length}</span> đã parse
                </>
              ) : null}
            </>
          ) : null}
        </span>
        <label className="flex items-center gap-2 text-sm shrink-0 cursor-pointer">
          <input
            type="checkbox"
            checked={onlyMissingInDb}
            onChange={(e) => {
              const on = e.target.checked;
              setOnlyMissingInDb(on);
              if (!on) setDbLookupError(null);
            }}
            disabled={rows.length === 0}
            className="rounded border-slate-300"
            title="Bật: chỉ hiện ID chưa có trong DB. Tắt: hiện toàn bộ lô sau parse."
            aria-label="Chỉ hiện sản phẩm ID chưa có trong cửa hàng; bỏ chọn để xem cả lô"
          />
          <span className="text-sm text-slate-700 whitespace-nowrap">Chỉ ID chưa có trong DB</span>
          {onlyMissingInDb && dbLookupPending ? (
            <span className="text-xs text-slate-500">Đang đối chiếu…</span>
          ) : null}
        </label>
        <label className="flex items-center gap-2 text-sm shrink-0">
          <span className="text-slate-600 whitespace-nowrap hidden sm:inline">Tỷ giá</span>
          <input
            type="text"
            inputMode="decimal"
            value={rateInput}
            onChange={(e) => setRateInput(e.target.value)}
            placeholder="VNĐ / 1 CN¥"
            autoComplete="off"
            aria-label="Tỷ giá VNĐ trên một nhân dân tệ CN¥ để ước lượng cột VNĐ và CSV"
            className="w-[6.75rem] tabular-nums rounded-md border border-slate-300 px-2 py-1.5 text-sm disabled:bg-slate-100 disabled:text-slate-400"
          />
        </label>
        <label className="flex items-center gap-2 text-sm shrink-0 min-w-[12rem] sm:min-w-[16rem] max-w-[20rem]">
          <span className="sr-only">Lọc theo tên shop</span>
          <span className="text-slate-600 whitespace-nowrap hidden sm:inline">Lọc shop</span>
          <input
            type="search"
            value={shopFilter}
            onChange={(e) => setShopFilter(e.target.value)}
            placeholder="Tên shop…"
            autoComplete="off"
            aria-label="Lọc danh sách theo tên shop"
            disabled={rows.length === 0}
            className="flex-1 min-w-0 rounded-md border border-slate-300 px-2 py-1.5 text-sm disabled:bg-slate-100 disabled:text-slate-400"
          />
        </label>
        <label className="flex items-center gap-2 text-sm shrink-0 min-w-[12rem] sm:min-w-[16rem] max-w-[20rem]">
          <span className="sr-only">Lọc theo tiêu đề sản phẩm</span>
          <span className="text-slate-600 whitespace-nowrap hidden sm:inline">Lọc tiêu đề</span>
          <input
            type="search"
            value={titleFilter}
            onChange={(e) => setTitleFilter(e.target.value)}
            placeholder="Chữ trong tiêu đề… (không cần liền)"
            autoComplete="off"
            aria-label="Lọc tiêu đề: ký tự đúng thứ tự, không cần liên tục; nhiều cụm cách nhau bằng khoảng trắng"
            disabled={rows.length === 0}
            className="flex-1 min-w-0 rounded-md border border-slate-300 px-2 py-1.5 text-sm disabled:bg-slate-100 disabled:text-slate-400"
          />
        </label>
      </div>

      {error && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 text-amber-900 text-sm px-4 py-3">
          {error}
        </div>
      )}

      {dbLookupError && (
        <div className="rounded-lg border border-red-200 bg-red-50 text-red-800 text-sm px-4 py-3">
          {dbLookupError}
        </div>
      )}
      {rows.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-slate-200">
          {(shopFilterTrimmed || titleFilterTrimmed) &&
            rows.length > 0 &&
            preDbFilteredRows.length === 0 && (
              <div className="px-4 py-3 text-sm text-slate-600 border-b border-slate-100 bg-slate-50">
                Không có dòng nào khớp
                {shopFilterTrimmed ? (
                  <>
                    {' '}
                    shop <span className="font-medium">{shopFilterTrimmed}</span>
                  </>
                ) : null}
                {shopFilterTrimmed && titleFilterTrimmed ? ' và' : ''}
                {titleFilterTrimmed ? (
                  <>
                    {' '}
                    cụm tiêu đề <span className="font-medium">{titleFilterTrimmed}</span> (chữ không cần liền)
                  </>
                ) : null}
                .
              </div>
            )}
          {preDbFilteredRows.length > 0 && dbPresenceReady && displayRows.length === 0 && (
            <div className="px-4 py-3 text-sm text-slate-600 border-b border-slate-100 bg-slate-50">
              Mọi sản phẩm trong lô đang lọc đều đã có trong DB (theo ID SP).
            </div>
          )}
          {!shopFilterTrimmed &&
            !titleFilterTrimmed &&
            dbPresenceReady &&
            displayRows.length === 0 &&
            rows.length > 0 && (
              <div className="px-4 py-3 text-sm text-slate-600 border-b border-slate-100 bg-slate-50">
                Mọi ID trong lô parse đều đã có trong DB.
              </div>
            )}
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-600">
              <tr>
                <th className="p-2 w-12">#</th>
                <th className="p-2">ID SP</th>
                <th className="p-2 max-w-[220px]">Link SP</th>
                <th className="p-2 w-20">Ảnh</th>
                <th className="p-2 min-w-[200px]">Tiêu đề</th>
                <th className="p-2 min-w-[120px]">Shop</th>
                <th className="p-2 min-w-[120px]">Tag</th>
                <th className="p-2 min-w-[120px]">Giá (raw)</th>
                <th className="p-2 min-w-[120px]" title="CN¥ × hệ số lưới × tỷ giá (VNĐ/CN¥), làm tròn">
                  ~VNĐ
                </th>
              </tr>
            </thead>
            <tbody>
              {displayRows.map((r, i) => (
                <tr
                  key={r.item_id ? `row-${r.row}-id-${r.item_id}` : `${r.row}-${r.main_image_url.slice(0, 64)}`}
                  className="border-t border-slate-100 align-top"
                >
                  <td className="p-2 text-slate-500">{i + 1}</td>
                  <td className="p-2 font-mono text-xs text-slate-800 whitespace-nowrap">{r.item_id || '—'}</td>
                  <td className="p-2 text-xs break-all max-w-[220px]">
                    {r.item_url ? (
                      <a
                        href={r.item_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-600 hover:underline line-clamp-2"
                      >
                        {r.item_url}
                      </a>
                    ) : (
                      <span className="text-slate-400">—</span>
                    )}
                  </td>
                  <td className="p-2">
                    {r.main_image_url ? (
                      <img
                        src={r.main_image_url}
                        alt=""
                        className="w-14 h-14 object-cover rounded border border-slate-200"
                      />
                    ) : (
                      <span className="text-slate-400">—</span>
                    )}
                  </td>
                  <td className="p-2 text-slate-800 max-w-xl">{r.title || '—'}</td>
                  <td className="p-2 text-slate-700 max-w-[180px]">{r.shop_name || '—'}</td>
                  <td className="p-2 text-slate-600 text-xs">{r.tags || '—'}</td>
                  <td className="p-2 font-mono text-xs text-slate-700 break-all max-w-[200px]">
                    {r.price_raw || '—'}
                  </td>
                  <td
                    className="p-2 text-xs text-slate-800 whitespace-nowrap"
                    title={
                      r.price_cny_approx != null && r.cny_exchange_multiplier != null
                        ? `CN¥ ${r.price_cny_approx} × ${r.cny_exchange_multiplier} × ${effectiveRate} VNĐ/CN¥`
                        : undefined
                    }
                  >
                    {formatVndApproxCell(estimateListingVndRounded(r, effectiveRate))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
