'use client';

import { useEffect, useState } from 'react';
import { adminProductAPI, type AdminProduct } from '@/lib/admin-api';

export type LadipageProductPickerMode = 'single' | 'multi';

type Props = {
  mode: LadipageProductPickerMode;
  selectedProducts: AdminProduct[];
  onChange: (products: AdminProduct[]) => void;
  disabled?: boolean;
};

export default function LadipageProductPicker({ mode, selectedProducts, onChange, disabled }: Props) {
  const [productQuery, setProductQuery] = useState('');
  const [productResults, setProductResults] = useState<AdminProduct[]>([]);
  const [productSearchLoading, setProductSearchLoading] = useState(false);

  useEffect(() => {
    if (!productQuery.trim()) {
      setProductResults([]);
      return;
    }
    let alive = true;
    setProductSearchLoading(true);
    const query = productQuery.trim();
    const looksLikeSku = /^[A-Za-z0-9]{4,8}$/.test(query);
    const t = setTimeout(() => {
      const requests = looksLikeSku
        ? [
            adminProductAPI.getProducts({ product_id: query, limit: 20 }),
            adminProductAPI.getProducts({ q: query, limit: 20 }),
          ]
        : [adminProductAPI.getProducts({ q: query, limit: 20 })];
      Promise.all(requests)
        .then((results) => {
          if (!alive) return;
          const merged = new Map<number, AdminProduct>();
          results.forEach((res) => {
            (res.products || []).forEach((p) => {
              if (!merged.has(p.id)) merged.set(p.id, p);
            });
          });
          setProductResults(Array.from(merged.values()).slice(0, 20));
        })
        .catch(() => {
          if (alive) setProductResults([]);
        })
        .finally(() => {
          if (alive) setProductSearchLoading(false);
        });
    }, 350);
    return () => {
      alive = false;
      clearTimeout(t);
    };
  }, [productQuery]);

  const pickProduct = (p: AdminProduct) => {
    if (disabled) return;
    if (mode === 'single') {
      onChange([p]);
      return;
    }
    onChange(
      selectedProducts.some((x) => x.id === p.id)
        ? selectedProducts.filter((x) => x.id !== p.id)
        : [...selectedProducts, p],
    );
  };

  const removeProduct = (id: number) => {
    if (disabled) return;
    onChange(selectedProducts.filter((p) => p.id !== id));
  };

  return (
    <div className={disabled ? 'opacity-60' : undefined}>
      <label className="mb-1 block text-sm font-medium text-gray-700">
        {mode === 'single' ? 'Tìm và chọn 1 sản phẩm' : 'Tìm và chọn nhiều sản phẩm'}
      </label>
      <input
        type="text"
        value={productQuery}
        onChange={(e) => setProductQuery(e.target.value)}
        disabled={disabled}
        placeholder="Nhập tên sản phẩm hoặc mã SKU…"
        className="w-full rounded-md border border-gray-300 p-2 text-sm outline-none focus:border-orange-400 disabled:bg-gray-50"
      />
      {mode === 'multi' && (
        <p className="mt-1 text-xs text-gray-500">
          Chọn từ 2 sản phẩm trở lên. Bấm dòng kết quả để thêm/bỏ — đã chọn{' '}
          <strong>{selectedProducts.length}</strong>.
        </p>
      )}
      {productSearchLoading && <p className="mt-1 text-xs text-gray-400">Đang tìm…</p>}
      {productResults.length > 0 && (
        <div className="mt-2 max-h-56 overflow-y-auto rounded-md border border-gray-200">
          {productResults.map((p) => {
            const checked = selectedProducts.some((x) => x.id === p.id);
            const sku = p.code || p.product_id;
            return (
              <button
                type="button"
                key={p.id}
                disabled={disabled}
                onClick={() => pickProduct(p)}
                className={`flex w-full items-center justify-between gap-3 border-b border-gray-100 px-3 py-2 text-left text-sm last:border-0 hover:bg-orange-50 disabled:cursor-not-allowed ${
                  checked ? 'bg-orange-50' : ''
                }`}
              >
                <span className="min-w-0">
                  <span className="line-clamp-1 block">{p.name}</span>
                  {sku && <span className="text-xs text-gray-400">Mã: {sku}</span>}
                </span>
                {checked ? (
                  <span className="shrink-0 text-orange-600">{mode === 'single' ? '✓ Đã chọn' : '✓'}</span>
                ) : mode === 'multi' ? (
                  <span className="shrink-0 text-gray-400">+ Thêm</span>
                ) : null}
              </button>
            );
          })}
        </div>
      )}
      {selectedProducts.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {selectedProducts.map((p) => (
            <span
              key={p.id}
              className="inline-flex max-w-full items-center gap-1.5 rounded-full bg-orange-100 px-3 py-1 text-xs font-medium text-orange-700"
            >
              <span className="line-clamp-1">{p.name}</span>
              {!disabled && (
                <button type="button" onClick={() => removeProduct(p.id)} className="shrink-0 text-orange-500 hover:text-orange-800">
                  ×
                </button>
              )}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
