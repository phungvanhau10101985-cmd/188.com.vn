'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { apiClient, type SearchHistoryItem } from '@/lib/api-client';
import { navigateProductTextSearch } from '@/lib/navigate-product-text-search';
import { buildMobileSearchHref } from '@/lib/mobile-search-path';
import { useAppCategoryTreeBase } from '@/lib/app-category-tree-context';
import { useAuth } from '@/features/auth/hooks/useAuth';
import type { Product } from '@/types/api';
import { hasValidProductImageUrl } from '@/lib/image-utils';
import CdnFillImage from '@/components/CdnFillImage';
import Button from '@/components/ui/Button';
import MobileImageSearchButton from '@/components/search/MobileImageSearchButton';
import { snapshotProductDataAsProduct } from '@/lib/viewed-product-card';
import { warehouseStandaloneSaleImage } from '@/lib/warehouse-clearance';

function dedupeSearchHistory(rows: SearchHistoryItem[]): SearchHistoryItem[] {
  const seen = new Set<string>();
  const out: SearchHistoryItem[] = [];
  for (const row of rows) {
    const q = row.search_query.trim();
    if (!q) continue;
    const key = q.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ ...row, search_query: q });
  }
  return out;
}

function productTileImage(product: Product): string | null {
  const warehouse = warehouseStandaloneSaleImage(product);
  const candidates = [
    product.main_image,
    warehouse,
    ...(product.images || []),
    ...(product.gallery || []),
  ];
  for (const c of candidates) {
    const u = (c || '').trim();
    if (hasValidProductImageUrl(u)) return u;
  }
  return null;
}

function searchQueryFromProduct(product: Product): string {
  const sub3 = (product.sub_subcategory || '').trim();
  const sub2 = (product.subcategory || '').trim();
  const cat = (product.category || '').trim();
  const name = (product.name || '').trim();
  return sub3 || sub2 || cat || name;
}

function productFromViewedRow(row: unknown): Product | null {
  if (!row || typeof row !== 'object') return null;
  const r = row as { product_id?: number; product_data?: Record<string, unknown> };
  const id = Number(r.product_id);
  if (!Number.isFinite(id) || id <= 0) return null;
  return snapshotProductDataAsProduct(id, r.product_data);
}

function pushUniqueSuggestProduct(out: Product[], seen: Set<number>, product: Product | null | undefined) {
  if (!product?.id || seen.has(product.id)) return;
  if (!String(product.name || '').trim() || !productTileImage(product)) return;
  seen.add(product.id);
  out.push(product);
}

async function loadPersonalizedSuggestProducts(): Promise<{ products: Product[]; fromViewed: boolean }> {
  const [viewedRes, feedRes] = await Promise.allSettled([
    apiClient.getViewedProducts(12),
    apiClient.getPersonalizedHomeFeed(0, 16),
  ]);

  const out: Product[] = [];
  const seen = new Set<number>();
  let fromViewed = false;

  if (viewedRes.status === 'fulfilled' && Array.isArray(viewedRes.value)) {
    for (const row of viewedRes.value) {
      if (out.length >= 12) break;
      const before = out.length;
      pushUniqueSuggestProduct(out, seen, productFromViewedRow(row));
      if (out.length > before) fromViewed = true;
    }
  }

  if (feedRes.status === 'fulfilled') {
    for (const p of feedRes.value.products || []) {
      if (out.length >= 12) break;
      pushUniqueSuggestProduct(out, seen, p);
    }
  }

  if (out.length < 12) {
    try {
      const popular = await apiClient.getProducts({
        limit: 16,
        skip: 0,
        is_active: true,
        skip_total: true,
        sort: 'views_desc',
      });
      for (const p of popular.products || []) {
        if (out.length >= 12) break;
        pushUniqueSuggestProduct(out, seen, p);
      }
    } catch {
      /* giữ những gì đã có */
    }
  }

  return { products: out.slice(0, 12), fromViewed };
}

function loadGuestSuggestions(): string[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem('latest_search_suggestions');
    const parsed = raw ? JSON.parse(raw) : null;
    return Array.isArray(parsed?.suggestions)
      ? parsed.suggestions.filter((s: unknown) => typeof s === 'string' && s.trim())
      : [];
  } catch {
    return [];
  }
}

export default function MobileSearchPageClient() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const categoryTree = useAppCategoryTreeBase();
  const { isAuthenticated } = useAuth();
  const inputRef = useRef<HTMLInputElement>(null);
  const qFromUrl = searchParams.get('q') ?? '';

  const [searchTerm, setSearchTerm] = useState(qFromUrl);
  const [viewportHeight, setViewportHeight] = useState<number | null>(null);
  const [history, setHistory] = useState<SearchHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [removingQuery, setRemovingQuery] = useState<string | null>(null);
  const [clearingAll, setClearingAll] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [suggestProducts, setSuggestProducts] = useState<Product[]>([]);
  const [suggestLoading, setSuggestLoading] = useState(true);
  const [suggestError, setSuggestError] = useState<string | null>(null);
  const [suggestFromViewed, setSuggestFromViewed] = useState(false);
  const [typedProducts, setTypedProducts] = useState<Product[]>([]);
  const [typedLoading, setTypedLoading] = useState(false);
  const [typedError, setTypedError] = useState<string | null>(null);

  const typed = searchTerm.trim();
  const typedKey = typed.toLowerCase();

  useEffect(() => {
    setSearchTerm(qFromUrl);
  }, [qFromUrl]);

  useEffect(() => {
    const apply = () => {
      const vv = window.visualViewport;
      setViewportHeight(vv ? Math.round(vv.height) : window.innerHeight);
    };
    apply();
    const vv = window.visualViewport;
    vv?.addEventListener('resize', apply);
    vv?.addEventListener('scroll', apply);
    window.addEventListener('resize', apply);
    return () => {
      vv?.removeEventListener('resize', apply);
      vv?.removeEventListener('scroll', apply);
      window.removeEventListener('resize', apply);
    };
  }, []);

  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    const focus = () => {
      el.focus({ preventScroll: true });
      const len = el.value.length;
      try {
        el.setSelectionRange(len, len);
      } catch {
        /* iOS older */
      }
    };
    focus();
    const t = window.setTimeout(focus, 50);
    return () => window.clearTimeout(t);
  }, []);

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const rows = await apiClient.getSearchHistory(30);
      setHistory(dedupeSearchHistory(rows));
    } catch {
      setHistoryError('Không tải được lịch sử tìm kiếm');
      setHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  useEffect(() => {
    let cancelled = false;
    if (isAuthenticated) {
      apiClient
        .getSearchSuggestions(12)
        .then((r) => {
          if (!cancelled) setSuggestions(r.suggestions || []);
        })
        .catch(() => {
          if (!cancelled) setSuggestions([]);
        });
    } else {
      setSuggestions(loadGuestSuggestions());
    }
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated]);

  useEffect(() => {
    let cancelled = false;
    setSuggestLoading(true);
    setSuggestError(null);
    void loadPersonalizedSuggestProducts()
      .then((result) => {
        if (cancelled) return;
        setSuggestProducts(result.products);
        setSuggestFromViewed(result.fromViewed);
      })
      .catch(() => {
        if (cancelled) return;
        setSuggestProducts([]);
        setSuggestFromViewed(false);
        setSuggestError('Không tải được gợi ý tìm kiếm');
      })
      .finally(() => {
        if (!cancelled) setSuggestLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated]);

  useEffect(() => {
    if (typed.length < 2) {
      setTypedProducts([]);
      setTypedLoading(false);
      setTypedError(null);
      return;
    }
    setTypedLoading(true);
    setTypedError(null);
    let cancelled = false;
    const t = window.setTimeout(async () => {
      try {
        const r = await apiClient.getProducts({
          q: typed,
          limit: 8,
          skip: 0,
          is_active: true,
          skip_total: true,
          sort: 'id_desc',
        });
        if (!cancelled) setTypedProducts(r.products || []);
      } catch {
        if (!cancelled) {
          setTypedProducts([]);
          setTypedError('Không tải được gợi ý sản phẩm');
        }
      } finally {
        if (!cancelled) setTypedLoading(false);
      }
    }, 280);
    return () => {
      cancelled = true;
      window.clearTimeout(t);
    };
  }, [typed]);

  const matchedHistory = useMemo(() => {
    if (!typedKey) return history;
    return history.filter((row) => row.search_query.toLowerCase().includes(typedKey));
  }, [history, typedKey]);

  const matchedSuggestions = useMemo(() => {
    const historyKeys = new Set(history.map((row) => row.search_query.toLowerCase()));
    const extra = suggestions.filter((s) => {
      const key = s.trim().toLowerCase();
      return key && !historyKeys.has(key);
    });
    if (!typedKey) return extra.slice(0, 12);
    return extra.filter((s) => s.toLowerCase().includes(typedKey)).slice(0, 12);
  }, [suggestions, history, typedKey]);

  const visibleProducts = typed.length >= 2 ? typedProducts : suggestProducts;

  const runSearch = useCallback(
    (raw: string) => {
      const term = raw.trim();
      if (!term) {
        router.push('/');
        return;
      }
      if (typeof window !== 'undefined') {
        const href = buildMobileSearchHref(term);
        const current = `${window.location.pathname}${window.location.search}`;
        if (current !== href) {
          window.history.replaceState(window.history.state, '', href);
        }
      }
      navigateProductTextSearch(router, term, categoryTree);
    },
    [router, categoryTree],
  );

  const handleBack = () => {
    if (typeof window !== 'undefined' && window.history.length <= 1) {
      router.push('/');
      return;
    }
    router.back();
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    runSearch(searchTerm);
  };

  const handleRemoveHistory = async (query: string) => {
    setRemovingQuery(query);
    setHistoryError(null);
    try {
      await apiClient.deleteSearchHistoryItem(query);
      setHistory((prev) => prev.filter((row) => row.search_query !== query));
    } catch {
      setHistoryError('Không xóa được từ khóa. Thử lại.');
    } finally {
      setRemovingQuery(null);
    }
  };

  const handleClearAll = async () => {
    setClearingAll(true);
    setHistoryError(null);
    try {
      await apiClient.clearSearchHistory();
      setHistory([]);
    } catch {
      setHistoryError('Không xóa được toàn bộ lịch sử. Thử lại.');
    } finally {
      setClearingAll(false);
    }
  };

  const retryTypedProducts = () => {
    setTypedError(null);
    setTypedLoading(true);
    apiClient
      .getProducts({
        q: typed,
        limit: 8,
        skip: 0,
        is_active: true,
        skip_total: true,
        sort: 'id_desc',
      })
      .then((r) => setTypedProducts(r.products || []))
      .catch(() => {
        setTypedProducts([]);
        setTypedError('Không tải được gợi ý sản phẩm');
      })
      .finally(() => setTypedLoading(false));
  };

  const retrySuggestProducts = () => {
    setSuggestLoading(true);
    setSuggestError(null);
    void loadPersonalizedSuggestProducts()
      .then((result) => {
        setSuggestProducts(result.products);
        setSuggestFromViewed(result.fromViewed);
      })
      .catch(() => {
        setSuggestProducts([]);
        setSuggestFromViewed(false);
        setSuggestError('Không tải được gợi ý tìm kiếm');
      })
      .finally(() => setSuggestLoading(false));
  };

  const showSuggestSection =
    typed.length >= 2 || suggestLoading || Boolean(suggestError) || suggestProducts.length > 0;

  return (
      <div
        className="fixed inset-0 z-[200] flex flex-col bg-gray-50"
        style={viewportHeight ? { height: viewportHeight } : { height: '100dvh' }}
      >
        <header className="shrink-0 border-b border-gray-100 bg-white pt-[env(safe-area-inset-top,0px)]">
          <form
            onSubmit={handleSubmit}
            className="mx-auto flex w-full max-w-3xl items-center gap-1.5 px-3 py-2.5 sm:px-4 md:py-3"
          >
            <button
              type="button"
              onClick={handleBack}
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-gray-800 hover:bg-gray-100 active:bg-gray-200"
              aria-label="Quay lại"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </button>

            <div className="flex h-11 min-w-0 flex-1 items-stretch overflow-hidden rounded-xl bg-gray-100 ring-1 ring-gray-200 focus-within:ring-2 focus-within:ring-orange-300">
              <div className="flex min-w-0 flex-1 items-center gap-1.5 pl-2.5 pr-1">
                <svg className="h-5 w-5 shrink-0 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
                <input
                  ref={inputRef}
                  type="text"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  placeholder="Tìm trên 188.COM.VN…"
                  autoComplete="off"
                  autoCorrect="off"
                  autoCapitalize="off"
                  spellCheck={false}
                  enterKeyHint="search"
                  inputMode="search"
                  aria-label="Từ khóa tìm kiếm"
                  className="min-w-0 flex-1 h-full bg-transparent text-[16px] text-gray-900 placeholder:text-gray-500 border-0 focus:ring-0 focus:outline-none"
                />
                {searchTerm ? (
                  <button
                    type="button"
                    onClick={() => {
                      setSearchTerm('');
                      inputRef.current?.focus();
                    }}
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-gray-500 hover:bg-gray-200"
                    aria-label="Xóa từ khóa"
                  >
                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                ) : null}
              </div>
              <MobileImageSearchButton
                className="flex h-full w-11 shrink-0 cursor-pointer items-center justify-center border-l border-gray-200 text-gray-600 hover:bg-orange-50 hover:text-[#ea580c] active:bg-orange-100"
                iconClassName="block size-6 shrink-0 pointer-events-none"
              />
              <button
                type="submit"
                className="flex h-full w-11 shrink-0 items-center justify-center bg-[#ea580c] text-white hover:bg-[#c2410c] active:bg-orange-800 md:w-14"
                aria-label="Tìm trên 188"
              >
                <svg className="size-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </button>
            </div>
          </form>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain bg-gray-50 pb-[max(16px,env(safe-area-inset-bottom))]">
          <div className="mx-auto w-full max-w-3xl px-3 pt-3 sm:px-4 md:pt-5">
          {historyError && (
            <div className="mb-3 rounded-xl border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700">
              {historyError}{' '}
              <button type="button" onClick={() => void loadHistory()} className="font-medium underline">
                Thử lại
              </button>
            </div>
          )}

          <section aria-label="Lịch sử tìm kiếm">
            <div className="mb-2 flex items-center justify-between gap-2">
              <h2 className="text-sm font-semibold text-gray-900">Lịch sử tìm kiếm</h2>
              {history.length > 0 && (
                <Button
                  type="button"
                  variant="ghost"
                  size="inline"
                  onClick={() => void handleClearAll()}
                  loading={clearingAll}
                  disabled={removingQuery != null}
                  className="text-xs font-medium text-gray-500 hover:text-red-600"
                >
                  Xóa tất cả
                </Button>
              )}
            </div>
            {historyLoading && <p className="py-2 text-xs text-gray-400">Đang tải…</p>}
            {!historyLoading && matchedHistory.length === 0 && !historyError && (
              <p className="py-2 text-xs text-gray-500">
                {typedKey ? 'Không có lịch sử khớp từ khóa' : 'Chưa có từ khóa tìm kiếm'}
              </p>
            )}
            {matchedHistory.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {matchedHistory.map((row) => (
                  <div
                    key={`${row.id}-${row.search_query}`}
                    className="inline-flex max-w-full items-center rounded-full bg-white pl-3 pr-1 py-1 shadow-sm ring-1 ring-gray-200"
                  >
                    <button
                      type="button"
                      onClick={() => runSearch(row.search_query)}
                      className="truncate text-sm text-gray-800"
                    >
                      {row.search_query}
                    </button>
                    <button
                      type="button"
                      className="ml-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-gray-400 hover:bg-gray-100 hover:text-gray-700 disabled:opacity-40"
                      aria-label={`Xóa ${row.search_query}`}
                      disabled={removingQuery === row.search_query || clearingAll}
                      onClick={() => void handleRemoveHistory(row.search_query)}
                    >
                      <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                ))}
              </div>
            )}
          </section>

          {matchedSuggestions.length > 0 && (
            <section className="pt-5" aria-label="Gợi ý từ khóa">
              <h2 className="mb-2 text-sm font-semibold text-gray-900">Gợi ý từ khóa</h2>
              <div className="flex flex-wrap gap-2">
                {matchedSuggestions.map((term) => (
                  <button
                    key={term}
                    type="button"
                    onClick={() => runSearch(term)}
                    className="max-w-full truncate rounded-full bg-orange-50 px-3 py-1.5 text-sm text-[#c2410c] ring-1 ring-orange-100 hover:bg-orange-100"
                  >
                    {term}
                  </button>
                ))}
              </div>
            </section>
          )}

          {showSuggestSection && (
          <section className="pt-5 pb-6" aria-label="Gợi ý tìm kiếm">
            <h2 className="text-sm font-semibold text-gray-900">Gợi ý tìm kiếm</h2>
            <p className="mt-0.5 mb-3 text-xs text-gray-500">
              {typed.length >= 2
                ? 'Bấm ảnh để tìm sản phẩm cùng kiểu'
                : suggestFromViewed
                  ? 'Dựa trên sản phẩm bạn đã xem — bấm ảnh để tìm'
                  : 'Bấm ảnh để tìm sản phẩm cùng loại'}
            </p>
            {suggestError && typed.length < 2 && (
              <div className="mb-3 rounded-xl border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700">
                {suggestError}{' '}
                <button type="button" onClick={retrySuggestProducts} className="font-medium underline">
                  Thử lại
                </button>
              </div>
            )}
            {typedError && (
              <div className="mb-3 rounded-xl border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700">
                {typedError}{' '}
                <button type="button" onClick={retryTypedProducts} className="font-medium underline">
                  Thử lại
                </button>
              </div>
            )}
            {((suggestLoading && typed.length < 2) ||
              (typedLoading && typed.length >= 2 && visibleProducts.length === 0)) && (
              <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 md:grid-cols-4">
                {Array.from({ length: 8 }).map((_, i) => (
                  <div key={i} className="overflow-hidden rounded-2xl bg-white ring-1 ring-gray-100">
                    <div className="aspect-[3/4] animate-pulse bg-gray-200" />
                    <div className="h-9 animate-pulse bg-gray-100" />
                  </div>
                ))}
              </div>
            )}
            {!typedLoading && typed.length >= 2 && visibleProducts.length === 0 && !typedError && (
              <p className="py-2 text-sm text-gray-500">
                Chưa thấy gợi ý khớp. Bấm nút tìm để xem kết quả đầy đủ.
              </p>
            )}
            {visibleProducts.length > 0 && !(suggestLoading && typed.length < 2) && (
              <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 md:grid-cols-4">
                {visibleProducts.map((product) => {
                  const img = productTileImage(product);
                  if (!img) return null;
                  const query =
                    typed.length >= 2
                      ? (product.name || '').trim() || searchQueryFromProduct(product)
                      : searchQueryFromProduct(product);
                  if (!query) return null;
                  return (
                    <button
                      key={product.id}
                      type="button"
                      onClick={() => runSearch(query)}
                      aria-label={`Tìm kiếm ${query}`}
                      className="group overflow-hidden rounded-2xl bg-white text-left shadow-sm ring-1 ring-gray-100 transition hover:-translate-y-0.5 hover:shadow-md hover:ring-orange-200 active:scale-[0.99]"
                    >
                      <div className="relative aspect-[3/4] bg-gray-50">
                        <CdnFillImage
                          rawSrc={img}
                          alt={query}
                          widthHint={320}
                          heightHint={420}
                          className="object-cover"
                          sizes="(min-width: 768px) 180px, 45vw"
                        />
                        <span className="absolute left-2 top-2 inline-flex items-center gap-1 rounded-full bg-white/95 px-2 py-0.5 text-[11px] font-semibold text-[#ea580c] shadow-sm">
                          <svg className="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                          </svg>
                          Tìm
                        </span>
                      </div>
                      <p className="line-clamp-2 px-2.5 py-2 text-xs font-medium leading-snug text-gray-800 group-hover:text-[#c2410c] sm:text-sm">
                        {query}
                      </p>
                    </button>
                  );
                })}
              </div>
            )}
          </section>
          )}
          </div>
        </div>
      </div>
  );
}
