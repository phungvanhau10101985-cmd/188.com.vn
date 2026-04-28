'use client';

import { useEffect, useState, useCallback } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { apiClient, NANOAI_TEXT_SEARCH_LIMIT } from '@/lib/api-client';
import NanoaiSimilarProductCard from '@/components/NanoaiSimilarProductCard';
import type { NanoaiSearchProduct, NanoaiSearchResponse } from '@/types/api';
import { useLazyRevealList } from '@/hooks/useLazyRevealList';

export default function TimTheoChuPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const qParam = (searchParams.get('q') ?? '').trim();

  const [input, setInput] = useState(qParam);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [softMessage, setSoftMessage] = useState<string | null>(null);
  const [products, setProducts] = useState<NanoaiSearchProduct[]>([]);

  useEffect(() => {
    setInput(qParam);
  }, [qParam]);

  const runSearch = useCallback(async (q: string) => {
    const t = q.trim();
    if (t.length < 2) {
      setProducts([]);
      setSoftMessage(null);
      setError(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    setSoftMessage(null);
    setProducts([]);
    try {
      const res: NanoaiSearchResponse = await apiClient.nanoaiTextSearch(t, NANOAI_TEXT_SEARCH_LIMIT);
      const list = Array.isArray(res.products) ? res.products : [];
      setProducts(list);
      if (res.error && list.length === 0) {
        setSoftMessage(res.error);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không tìm được. Vui lòng thử lại.');
      setProducts([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (qParam.length >= 2) {
      void runSearch(qParam);
    } else {
      setProducts([]);
      setSoftMessage(null);
      setError(null);
      setLoading(false);
    }
  }, [qParam, runSearch]);

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const t = input.trim();
    if (t.length < 2) {
      setError('Nhập ít nhất 2 ký tự để tìm trong kho gợi ý.');
      return;
    }
    setError(null);
    router.push(`/tim-theo-chu?q=${encodeURIComponent(t)}`);
  };

  const { revealed, hasMore, sentinelRef, total } = useLazyRevealList(products, {
    initial: 12,
    step: 12,
  });

  return (
    <div className="max-w-7xl mx-auto px-4 py-4 md:py-6">
      <h1 className="text-lg md:text-xl font-bold text-gray-900 border-b-2 border-[#ea580c] pb-1 w-fit mb-1">
        Tìm theo từ khóa (kho gợi ý NanoAI)
      </h1>
      <p className="text-sm text-gray-600 mb-4">
        Tìm theo ngữ nghĩa trên catalog đã đồng bộ với NanoAI — khác với ô tìm kiếm chính trên trang chủ.
      </p>

      <form onSubmit={onSubmit} className="mb-6 flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ví dụ: giày da nam, váy hè…"
          className="flex-1 min-w-0 px-4 py-3 rounded-xl border border-gray-200 bg-white text-gray-900 text-sm focus:outline-none focus:ring-2 focus:ring-[#ea580c]/40"
        />
        <button
          type="submit"
          className="flex-shrink-0 px-4 py-3 rounded-xl bg-[#ea580c] text-white text-sm font-semibold hover:bg-orange-600"
        >
          Tìm NanoAI
        </button>
      </form>

      {error && (
        <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
      )}

      {softMessage && !error && products.length === 0 && !loading && qParam.length >= 2 && (
        <div className="mb-4 rounded-lg border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          {softMessage}
        </div>
      )}

      <section aria-live="polite">
        <h2 className="text-base font-bold text-gray-900 mb-2">
          {loading ? 'Đang tìm…' : `Kết quả (${products.length})`}
        </h2>

        {loading ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 md:gap-4">
            {[...Array(8)].map((_, i) => (
              <div key={i} className="bg-white rounded-xl border border-gray-100 overflow-hidden animate-pulse">
                <div className="aspect-square bg-gray-100" />
                <div className="p-3 space-y-2">
                  <div className="h-3 bg-gray-100 rounded w-3/4" />
                  <div className="h-3 bg-gray-100 rounded w-full" />
                </div>
              </div>
            ))}
          </div>
        ) : products.length > 0 ? (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 gap-3 md:gap-4">
              {revealed.map((item, i) => (
                <NanoaiSimilarProductCard
                  key={item.inventory_id || `${item.sku || item.name || i}-${i}`}
                  item={item}
                />
              ))}
            </div>
            {hasMore ? (
              <p className="text-center text-xs text-gray-500 py-3" aria-live="polite">
                Đang hiển thị {revealed.length} / {total} — kéo xuống để xem thêm
              </p>
            ) : null}
            <div ref={sentinelRef} className="h-4 w-full" aria-hidden />
          </>
        ) : qParam.length >= 2 && !loading && !error ? (
          <p className="text-sm text-gray-600 py-6 text-center">Không có sản phẩm gợi ý cho từ khóa này.</p>
        ) : (
          <p className="text-sm text-gray-600 py-6 text-center">
            Nhập từ khóa (ít nhất 2 ký tự) và bấm &quot;Tìm NanoAI&quot;, hoặc dùng biểu tượng tia sét trên thanh tìm kiếm mobile.
          </p>
        )}
      </section>
    </div>
  );
}
