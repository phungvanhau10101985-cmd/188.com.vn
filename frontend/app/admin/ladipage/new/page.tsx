'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { getApiBaseUrl, ngrokFetchHeaders } from '@/lib/api-base';
import { ladipageAdminAPI, type AdminProduct } from '@/lib/admin-api';
import LadipageProductPicker from '@/components/ladipage/LadipageProductPicker';
import { useToast } from '@/components/ToastProvider';

interface CategoryTreeV2Node {
  id: number;
  parent_id: number | null;
  level: number;
  name: string;
  slug: string;
  full_slug: string;
  children?: CategoryTreeV2Node[];
}

interface Cat3Option {
  id: number;
  breadcrumb: string;
}

function flattenCat3(nodes: CategoryTreeV2Node[], trail: string[] = []): Cat3Option[] {
  const out: Cat3Option[] = [];
  for (const n of nodes) {
    const nextTrail = [...trail, n.name];
    if (n.level === 3 || !n.children || n.children.length === 0) {
      if (n.level === 3) out.push({ id: n.id, breadcrumb: nextTrail.join(' › ') });
    }
    if (n.children && n.children.length > 0) {
      out.push(...flattenCat3(n.children, nextTrail));
    }
  }
  return out;
}

type SourceMode = 'category' | 'product_single' | 'products_multi';

export default function AdminLadipageNewPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { pushToast } = useToast();

  const [sourceMode, setSourceMode] = useState<SourceMode>(() => {
    const mode = searchParams.get('mode');
    if (mode === 'category' || mode === 'product_single' || mode === 'products_multi') return mode;
    return 'product_single';
  });
  const [cat3Options, setCat3Options] = useState<Cat3Option[]>([]);
  const [categoriesLoading, setCategoriesLoading] = useState(true);
  const [categoryId, setCategoryId] = useState<number | ''>('');
  const [productsLimit, setProductsLimit] = useState(12);
  const [selectedProducts, setSelectedProducts] = useState<AdminProduct[]>([]);

  const [title, setTitle] = useState('');
  const [titleTouched, setTitleTouched] = useState(false);
  const [adminBrief, setAdminBrief] = useState('');
  const [includeMaterial, setIncludeMaterial] = useState(true);
  const [includeFaq, setIncludeFaq] = useState(true);
  const [materialImageSource, setMaterialImageSource] = useState<'ai' | 'product'>('product');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');

  useEffect(() => {
    let alive = true;
    fetch(`${getApiBaseUrl()}/categories/tree-v2`, { headers: { ...ngrokFetchHeaders() } })
      .then((r) => (r.ok ? r.json() : []))
      .then((data: CategoryTreeV2Node[]) => {
        if (!alive) return;
        setCat3Options(flattenCat3(Array.isArray(data) ? data : []));
      })
      .catch(() => {})
      .finally(() => {
        if (alive) setCategoriesLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (titleTouched) return;
    if (sourceMode === 'category') {
      const opt = cat3Options.find((c) => c.id === categoryId);
      if (opt) setTitle(`${opt.breadcrumb.split(' › ').pop()} - Bộ sưu tập mới`);
    } else if (sourceMode === 'product_single' && selectedProducts.length === 1) {
      setTitle(selectedProducts[0].name);
    } else if (sourceMode === 'products_multi' && selectedProducts.length >= 2) {
      setTitle(`${selectedProducts.length} sản phẩm nổi bật`);
    }
  }, [sourceMode, categoryId, cat3Options, selectedProducts, titleTouched]);

  const canSubmit = useMemo(() => {
    if (!title.trim()) return false;
    if (sourceMode === 'category') return !!categoryId;
    if (sourceMode === 'product_single') return selectedProducts.length === 1;
    return selectedProducts.length >= 2;
  }, [title, sourceMode, categoryId, selectedProducts]);

  const switchSourceMode = (mode: SourceMode) => {
    setSourceMode(mode);
    setFormError('');
    if (mode === 'category') setSelectedProducts([]);
  };

  const handleSubmit = async () => {
    setFormError('');
    if (!canSubmit) {
      if (sourceMode === 'product_single') setFormError('Vui lòng chọn đúng 1 sản phẩm.');
      else if (sourceMode === 'products_multi') setFormError('Vui lòng chọn ít nhất 2 sản phẩm.');
      else setFormError('Vui lòng điền tiêu đề và chọn danh mục.');
      return;
    }
    setSubmitting(true);
    try {
      const created = await ladipageAdminAPI.create({
        title: title.trim(),
        source_type: sourceMode === 'category' ? 'category' : 'products',
        category_id: sourceMode === 'category' ? (categoryId as number) : undefined,
        product_ids: sourceMode === 'category' ? undefined : selectedProducts.map((p) => p.id),
        admin_brief: adminBrief.trim(),
        include_material: includeMaterial,
        include_faq: includeFaq,
        products_limit: productsLimit,
        material_image_source: sourceMode === 'product_single' ? materialImageSource : 'ai',
      });
      pushToast({ title: 'Đã tạo bản nháp', description: 'Đang chuyển tới trình soạn thảo…', variant: 'success', durationMs: 2000 });
      router.push(`/admin/ladipage/${created.id}/edit?autogen=1`);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Tạo ladipage thất bại');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl p-4 md:p-6">
      <h1 className="text-xl font-bold text-gray-900 md:text-2xl">Tạo ladipage mới</h1>
      <p className="mt-1 text-sm text-gray-500">
        Chọn nguồn dữ liệu và ý tưởng nội dung — AI (DeepSeek) sẽ viết nội dung bán hàng; ảnh chất liệu dùng Gemini hoặc ảnh SP.
      </p>

      <div className="mt-6 space-y-6 rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
        <div>
          <label className="mb-2 block text-sm font-medium text-gray-700">Nguồn dữ liệu</label>
          <div className="flex flex-wrap gap-2">
            {(
              [
                ['category', 'Danh mục cấp 3'],
                ['product_single', 'Một sản phẩm'],
                ['products_multi', 'Nhiều sản phẩm'],
              ] as const
            ).map(([mode, label]) => (
              <button
                key={mode}
                type="button"
                onClick={() => switchSourceMode(mode)}
                className={`rounded-lg border px-3 py-2 text-sm font-medium ${
                  sourceMode === mode ? 'border-orange-500 bg-orange-50 text-orange-700' : 'border-gray-200 text-gray-600'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {sourceMode === 'category' ? (
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">Danh mục cấp 3</label>
            {categoriesLoading ? (
              <div className="h-10 animate-pulse rounded-md bg-gray-100" />
            ) : (
              <select
                value={categoryId}
                onChange={(e) => setCategoryId(e.target.value ? Number(e.target.value) : '')}
                className="w-full rounded-md border border-gray-300 p-2 text-sm outline-none focus:border-orange-400"
              >
                <option value="">— Chọn danh mục —</option>
                {cat3Options.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.breadcrumb}
                  </option>
                ))}
              </select>
            )}
            <div className="mt-3">
              <label className="mb-1 block text-sm font-medium text-gray-700">Số SP hiển thị tối đa (bán chạy)</label>
              <input
                type="number"
                min={1}
                max={60}
                value={productsLimit}
                onChange={(e) => setProductsLimit(Math.max(1, Math.min(60, Number(e.target.value) || 12)))}
                className="w-32 rounded-md border border-gray-300 p-2 text-sm outline-none focus:border-orange-400"
              />
            </div>
          </div>
        ) : (
          <LadipageProductPicker
            mode={sourceMode === 'product_single' ? 'single' : 'multi'}
            selectedProducts={selectedProducts}
            onChange={setSelectedProducts}
          />
        )}

        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">Tiêu đề ladipage</label>
          <input
            type="text"
            value={title}
            onChange={(e) => {
              setTitle(e.target.value);
              setTitleTouched(true);
            }}
            className="w-full rounded-md border border-gray-300 p-2 text-sm outline-none focus:border-orange-400"
          />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">Ý tưởng / định hướng nội dung (tùy chọn)</label>
          <textarea
            value={adminBrief}
            onChange={(e) => setAdminBrief(e.target.value)}
            rows={4}
            className="w-full rounded-md border border-gray-300 p-2 text-sm outline-none focus:border-orange-400"
          />
        </div>

        <div className="flex flex-wrap gap-6">
          <label className="flex items-center gap-2 text-sm text-gray-700">
            <input type="checkbox" checked={includeMaterial} onChange={(e) => setIncludeMaterial(e.target.checked)} />
            Bao gồm phần Chất liệu
          </label>
          <label className="flex items-center gap-2 text-sm text-gray-700">
            <input type="checkbox" checked={includeFaq} onChange={(e) => setIncludeFaq(e.target.checked)} />
            Bao gồm FAQ
          </label>
        </div>

        {sourceMode === 'product_single' && includeMaterial ? (
          <div>
            <p className="mb-2 text-sm font-medium text-gray-700">Ảnh phần Chất liệu (ladipage 1 sản phẩm)</p>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setMaterialImageSource('ai')}
                className={`rounded-lg border px-3 py-2 text-sm ${
                  materialImageSource === 'ai'
                    ? 'border-orange-500 bg-orange-50 text-orange-700'
                    : 'border-gray-200 text-gray-600'
                }`}
              >
                AI tạo ảnh minh họa chất liệu
              </button>
              <button
                type="button"
                onClick={() => setMaterialImageSource('product')}
                className={`rounded-lg border px-3 py-2 text-sm ${
                  materialImageSource === 'product'
                    ? 'border-orange-500 bg-orange-50 text-orange-700'
                    : 'border-gray-200 text-gray-600'
                }`}
              >
                Chọn ảnh từ sản phẩm (gallery / màu / chi tiết)
              </button>
            </div>
            <p className="mt-2 text-xs text-gray-500">
              Chế độ ảnh SP: autogen chỉ lấy ảnh gallery/màu/chi tiết — không gọi AI sinh ảnh. Có thể đổi ảnh và chỉnh crop trong trình soạn thảo.
            </p>
          </div>
        ) : null}

        {formError && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{formError}</div>
        )}

        <div className="flex justify-end gap-3 border-t border-gray-100 pt-4">
          <button type="button" onClick={() => router.push('/admin/ladipage')} className="rounded-md px-4 py-2 text-sm text-gray-600 hover:bg-gray-100">
            Hủy
          </button>
          <button
            type="button"
            disabled={!canSubmit || submitting}
            onClick={handleSubmit}
            className="rounded-md bg-orange-600 px-5 py-2 text-sm font-semibold text-white hover:bg-orange-700 disabled:opacity-50"
          >
            {submitting ? 'Đang tạo…' : 'Tạo bằng AI →'}
          </button>
        </div>
      </div>
    </div>
  );
}
