'use client';

import { type RefObject, useCallback, useEffect, useRef, useState } from 'react';
import { apiClient, type SearchHistoryItem } from '@/lib/api-client';
import Button from '@/components/ui/Button';

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

type SearchHistoryPanelProps = {
  open: boolean;
  onClose: () => void;
  onSelect: (query: string) => void;
  className?: string;
  zClass?: string;
  ignoreRefs?: Array<RefObject<HTMLElement | null>>;
};

export default function SearchHistoryPanel({
  open,
  onClose,
  onSelect,
  className = '',
  zClass = 'z-[120]',
  ignoreRefs = [],
}: SearchHistoryPanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const [items, setItems] = useState<SearchHistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [removingQuery, setRemovingQuery] = useState<string | null>(null);
  const [clearingAll, setClearingAll] = useState(false);

  const loadHistory = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await apiClient.getSearchHistory(30);
      setItems(dedupeSearchHistory(rows));
    } catch {
      setError('Không tải được lịch sử tìm kiếm');
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    void loadHistory();
  }, [open, loadHistory]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent | TouchEvent) => {
      const target = e.target as Node | null;
      if (panelRef.current?.contains(target)) return;
      for (const ref of ignoreRefs) {
        if (ref.current?.contains(target)) return;
      }
      onClose();
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('touchstart', onPointerDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('touchstart', onPointerDown);
    };
  }, [open, onClose, ignoreRefs]);

  const handleRemove = async (query: string) => {
    setRemovingQuery(query);
    setError(null);
    try {
      await apiClient.deleteSearchHistoryItem(query);
      setItems((prev) => prev.filter((row) => row.search_query !== query));
    } catch {
      setError('Không xóa được từ khóa. Thử lại.');
    } finally {
      setRemovingQuery(null);
    }
  };

  const handleClearAll = async () => {
    setClearingAll(true);
    setError(null);
    try {
      await apiClient.clearSearchHistory();
      setItems([]);
      onClose();
    } catch {
      setError('Không xóa được toàn bộ lịch sử. Thử lại.');
    } finally {
      setClearingAll(false);
    }
  };

  if (!open) return null;

  return (
    <div
      ref={panelRef}
      role="listbox"
      aria-label="Lịch sử tìm kiếm"
      className={[
        'absolute left-0 right-0 top-full mt-1 rounded-lg border border-gray-200 bg-white text-gray-800 shadow-lg',
        zClass,
        className,
      ].join(' ')}
      onMouseDown={(e) => e.preventDefault()}
    >
      <div className="flex items-center justify-between gap-2 border-b border-gray-100 px-3 py-2">
        <span className="text-xs font-semibold text-gray-700">Lịch sử tìm kiếm</span>
        {loading && <span className="text-[11px] text-gray-400">Đang tải…</span>}
      </div>

      {error && (
        <div className="mx-2 mt-2 rounded-md border border-red-200 bg-red-50 px-2.5 py-2 text-xs text-red-700">
          {error}{' '}
          <Button
            type="button"
            variant="ghost"
            size="inline"
            onClick={() => void loadHistory()}
            loading={loading}
            className="font-medium underline hover:bg-transparent"
          >
            Thử lại
          </Button>
        </div>
      )}

      {!loading && items.length === 0 && !error && (
        <p className="px-3 py-4 text-center text-xs text-gray-500">Chưa có từ khóa tìm kiếm</p>
      )}

      {items.length > 0 && (
        <ul className="max-h-64 overflow-y-auto py-1">
          {items.map((row) => (
            <li key={`${row.id}-${row.search_query}`} className="flex items-center gap-1 px-1">
              <button
                type="button"
                role="option"
                className="min-h-[40px] flex-1 truncate rounded-md px-2 text-left text-sm text-gray-800 hover:bg-orange-50 hover:text-[#c2410c]"
                onClick={() => {
                  onSelect(row.search_query);
                  onClose();
                }}
              >
                {row.search_query}
              </button>
              <button
                type="button"
                className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-gray-400 hover:bg-gray-100 hover:text-gray-700 disabled:opacity-40"
                aria-label={`Xóa ${row.search_query}`}
                disabled={removingQuery === row.search_query || clearingAll}
                onClick={() => void handleRemove(row.search_query)}
              >
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </li>
          ))}
        </ul>
      )}

      {items.length > 0 && (
        <div className="border-t border-gray-100 p-2">
          <Button
            type="button"
            variant="ghost"
            onClick={() => void handleClearAll()}
            loading={clearingAll}
            disabled={removingQuery != null}
            className="w-full min-h-[36px] rounded-md text-xs font-medium text-gray-600 hover:bg-gray-50 hover:text-red-600"
          >
            Xóa tất cả lịch sử
          </Button>
        </div>
      )}
    </div>
  );
}
