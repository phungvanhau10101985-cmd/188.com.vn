'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import {
  adminProductAPI,
  ladipageAdminAPI,
  type AdminProduct,
  type LadipageCategoryMaterialItem,
  type LadipageDetail,
  type LadipageRegenerateTarget,
  type LadipageSection,
} from '@/lib/admin-api';
import LadipageProductPicker from '@/components/ladipage/LadipageProductPicker';
import { useToast } from '@/components/ToastProvider';
import HeroSection from '@/components/ladipage/HeroSection';
import HighlightsSection from '@/components/ladipage/HighlightsSection';
import MaterialSection from '@/components/ladipage/MaterialSection';
import TrustCtaSection from '@/components/ladipage/TrustCtaSection';
import FaqSection from '@/components/ladipage/FaqSection';
import ProductsGridSection from '@/components/ladipage/ProductsGridSection';
import type {
  FaqSectionData,
  HeroImageOption,
  HeroSectionData,
  HighlightsSectionData,
  MaterialSectionData,
  TrustCtaSectionData,
} from '@/components/ladipage/types';
import { buildHeroImageOptionsFromProducts } from '@/lib/ladipage-utils';

const SECTION_LABELS: Record<string, string> = {
  hero: 'Mở đầu (Hero)',
  highlights: 'Điểm nổi bật',
  material: 'Chất liệu',
  products_grid: 'Danh sách sản phẩm',
  trust_cta: 'Kêu gọi hành động',
  faq: 'Câu hỏi thường gặp',
};

const REGENERATE_ALL_CONFIRM_PHRASE = 'tạo lại toàn bộ';
const DELETE_LADIPAGE_CONFIRM_PHRASE = 'xóa ladipage';

function normalizeConfirmPhrase(raw: string): string {
  return raw
    .trim()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/\u0111/g, 'd')
    .replace(/\u0110/g, 'd')
    .toLowerCase()
    .replace(/\s+/g, ' ');
}

function confirmPhraseMatches(raw: string, expected: string): boolean {
  return normalizeConfirmPhrase(raw) === normalizeConfirmPhrase(expected);
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

export default function AdminLadipageEditPage() {
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const { pushToast } = useToast();
  const ladipageId = Number(params.id);

  const [ladipage, setLadipage] = useState<LadipageDetail | null>(null);
  const [loadStatus, setLoadStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [loadError, setLoadError] = useState('');
  const [sectionBusy, setSectionBusy] = useState<Record<number, boolean>>({});
  const [autogen, setAutogen] = useState<{ running: boolean; current: number; total: number; label: string } | null>(
    null,
  );
  const autogenStartedRef = useRef(false);
  const seoAutoStartedRef = useRef(false);

  const [titleDraft, setTitleDraft] = useState('');
  const [briefDraft, setBriefDraft] = useState('');
  const [slugDraft, setSlugDraft] = useState('');
  const [metaTitleDraft, setMetaTitleDraft] = useState('');
  const [metaDescriptionDraft, setMetaDescriptionDraft] = useState('');
  const [materialFilterDraft, setMaterialFilterDraft] = useState('');
  const [materialOptions, setMaterialOptions] = useState<LadipageCategoryMaterialItem[]>([]);
  const [materialsLoading, setMaterialsLoading] = useState(false);
  const [selectedProducts, setSelectedProducts] = useState<AdminProduct[]>([]);
  const [productsLoadStatus, setProductsLoadStatus] = useState<'idle' | 'loading' | 'ready'>('idle');
  const [savingProducts, setSavingProducts] = useState(false);
  const [generatingSeo, setGeneratingSeo] = useState(false);
  const [savingMeta, setSavingMeta] = useState(false);
  const [heroProducts, setHeroProducts] = useState<AdminProduct[]>([]);
  const [heroProductsStatus, setHeroProductsStatus] = useState<'idle' | 'loading' | 'ready'>('idle');
  const [publishBusy, setPublishBusy] = useState(false);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [regenerateModalOpen, setRegenerateModalOpen] = useState(false);
  const [regenerateConfirmText, setRegenerateConfirmText] = useState('');
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState('');

  const load = useCallback(async () => {
    setLoadStatus('loading');
    setLoadError('');
    try {
      const detail = await ladipageAdminAPI.get(ladipageId);
      setLadipage(detail);
      setTitleDraft(detail.title);
      setBriefDraft(detail.admin_brief || '');
      setSlugDraft(detail.slug);
      setMetaTitleDraft(detail.meta_title || '');
      setMetaDescriptionDraft(detail.meta_description || '');
      setMaterialFilterDraft(detail.material_filter || '');
      setLoadStatus('ready');
    } catch (err) {
      setLoadError(errorMessage(err));
      setLoadStatus('error');
    }
  }, [ladipageId]);

  useEffect(() => {
    if (Number.isFinite(ladipageId)) load();
  }, [ladipageId, load]);

  useEffect(() => {
    if (!ladipage || ladipage.source_type !== 'category' || !ladipage.category_id) {
      setMaterialOptions([]);
      setMaterialsLoading(false);
      return;
    }
    const savedFilter = (ladipage.material_filter || '').trim();
    let alive = true;
    setMaterialsLoading(true);
    ladipageAdminAPI
      .listCategoryMaterials(ladipage.category_id)
      .then((res) => {
        if (!alive) return;
        const items = res.items || [];
        if (savedFilter && !items.some((m) => m.material === savedFilter)) {
          setMaterialOptions([{ material: savedFilter, count: 0 }, ...items]);
        } else {
          setMaterialOptions(items);
        }
      })
      .catch(() => {
        if (alive) setMaterialOptions(savedFilter ? [{ material: savedFilter, count: 0 }] : []);
      })
      .finally(() => {
        if (alive) setMaterialsLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [ladipage?.id, ladipage?.source_type, ladipage?.category_id, ladipage?.material_filter]);

  useEffect(() => {
    if (!ladipage || ladipage.source_type !== 'products') {
      setSelectedProducts([]);
      setProductsLoadStatus('idle');
      return;
    }
    const ids = ladipage.product_ids || [];
    if (ids.length === 0) {
      setSelectedProducts([]);
      setProductsLoadStatus('ready');
      return;
    }
    let alive = true;
    setProductsLoadStatus('loading');
    Promise.all(ids.map((id) => adminProductAPI.getProductByDatabaseId(id).catch(() => null)))
      .then((rows) => {
        if (!alive) return;
        const order = new Map(ids.map((id, i) => [id, i]));
        const sorted = rows
          .filter((p): p is AdminProduct => p != null)
          .sort((a, b) => (order.get(a.id) ?? 999) - (order.get(b.id) ?? 999));
        setSelectedProducts(sorted);
        setProductsLoadStatus('ready');
      })
      .catch(() => {
        if (alive) setProductsLoadStatus('ready');
      });
    return () => {
      alive = false;
    };
  }, [ladipage]);

  useEffect(() => {
    if (!ladipage) {
      setHeroProducts([]);
      setHeroProductsStatus('idle');
      return;
    }
    if (ladipage.source_type === 'products' && productsLoadStatus === 'ready') {
      setHeroProducts(selectedProducts);
      setHeroProductsStatus('ready');
      return;
    }
    const ids = ladipage.resolved_product_ids || [];
    if (ids.length === 0) {
      setHeroProducts([]);
      setHeroProductsStatus('ready');
      return;
    }
    let alive = true;
    setHeroProductsStatus('loading');
    Promise.all(ids.slice(0, 60).map((id) => adminProductAPI.getProductByDatabaseId(id).catch(() => null)))
      .then((rows) => {
        if (!alive) return;
        const order = new Map(ids.map((id, i) => [id, i]));
        setHeroProducts(
          rows
            .filter((p): p is AdminProduct => p != null)
            .sort((a, b) => (order.get(a.id) ?? 999) - (order.get(b.id) ?? 999)),
        );
        setHeroProductsStatus('ready');
      })
      .catch(() => {
        if (alive) setHeroProductsStatus('ready');
      });
    return () => {
      alive = false;
    };
  }, [ladipage, selectedProducts, productsLoadStatus]);

  const heroImageOptions: HeroImageOption[] = buildHeroImageOptionsFromProducts(heroProducts);

  const isSingleProductLadipage =
    ladipage?.source_type === 'products' &&
    ((ladipage.product_ids?.length ?? 0) === 1 || (ladipage.resolved_product_ids?.length ?? 0) === 1);

  const patchSectionLocal = (updated: LadipageSection) => {
    setLadipage((prev) =>
      prev ? { ...prev, sections: prev.sections.map((s) => (s.id === updated.id ? updated : s)) } : prev,
    );
  };

  const generateSection = useCallback(
    async (sectionId: number) => {
      setSectionBusy((s) => ({ ...s, [sectionId]: true }));
      try {
        const updated = await ladipageAdminAPI.generateSection(ladipageId, sectionId);
        patchSectionLocal(updated);
        return updated;
      } catch (err) {
        pushToast({ title: 'Tạo nội dung AI thất bại', description: errorMessage(err), variant: 'error', durationMs: 4000 });
        throw err;
      } finally {
        setSectionBusy((s) => ({ ...s, [sectionId]: false }));
      }
    },
    [ladipageId, pushToast],
  );

  const regenerateSection = useCallback(
    async (sectionId: number, opts: { target?: LadipageRegenerateTarget; custom_prompt?: string }) => {
      setSectionBusy((s) => ({ ...s, [sectionId]: true }));
      try {
        const updated = await ladipageAdminAPI.regenerateSection(ladipageId, sectionId, opts);
        patchSectionLocal(updated);
        pushToast({ title: 'Đã tạo lại nội dung', variant: 'success', durationMs: 2000 });
      } catch (err) {
        pushToast({ title: 'Tạo lại thất bại', description: errorMessage(err), variant: 'error', durationMs: 4000 });
      } finally {
        setSectionBusy((s) => ({ ...s, [sectionId]: false }));
      }
    },
    [ladipageId, pushToast],
  );

  const saveSectionField = useCallback(
    async (section: LadipageSection, field: string, value: unknown) => {
      setSectionBusy((s) => ({ ...s, [section.id]: true }));
      try {
        const updated = await ladipageAdminAPI.updateSection(ladipageId, section.id, { [field]: value });
        patchSectionLocal(updated);
      } catch (err) {
        pushToast({ title: 'Lưu thất bại', description: errorMessage(err), variant: 'error', durationMs: 3500 });
      } finally {
        setSectionBusy((s) => ({ ...s, [section.id]: false }));
      }
    },
    [ladipageId, pushToast],
  );

  const saveArrayItemField = useCallback(
    async (section: LadipageSection, arrayKey: string, index: number, itemField: string, value: string) => {
      const raw = section.data?.[arrayKey];
      const items = Array.isArray(raw) ? [...(raw as Record<string, unknown>[])] : [];
      items[index] = { ...(items[index] || {}), [itemField]: value };
      await saveSectionField(section, arrayKey, items);
    },
    [saveSectionField],
  );

  const generateSeoFromAi = useCallback(
    async (opts?: { onlyMissing?: boolean; silent?: boolean }) => {
      setGeneratingSeo(true);
      try {
        const updated = await ladipageAdminAPI.generateSeo(ladipageId, { onlyMissing: opts?.onlyMissing });
        setLadipage(updated);
        setMetaTitleDraft(updated.meta_title || '');
        setMetaDescriptionDraft(updated.meta_description || '');
        if (!opts?.silent) {
          if (updated.seo_collision_warning) {
            pushToast({
              title: 'AI đã tạo SEO (đã chỉnh USP)',
              description: updated.seo_collision_warning,
              variant: 'success',
              durationMs: 5000,
            });
          } else {
            pushToast({ title: 'AI đã tạo SEO', variant: 'success', durationMs: 2500 });
          }
        }
      } catch (err) {
        if (!opts?.silent) {
          pushToast({ title: 'Tạo SEO thất bại', description: errorMessage(err), variant: 'error', durationMs: 4000 });
        }
      } finally {
        setGeneratingSeo(false);
      }
    },
    [ladipageId, pushToast],
  );

  const ladipageNeedsSeo = useCallback((detail: LadipageDetail) => {
    return !(detail.meta_title || '').trim() || !(detail.meta_description || '').trim();
  }, []);

  // Tự động bù meta SEO còn thiếu (ladipage cũ hoặc lần autogen SEO trước đó thất bại).
  useEffect(() => {
    if (loadStatus !== 'ready' || !ladipage || seoAutoStartedRef.current) return;
    if (searchParams.get('autogen') === '1') return;
    if (!ladipageNeedsSeo(ladipage)) return;

    const pending = ladipage.sections.filter((s) => s.section_type !== 'products_grid' && s.status === 'pending');
    if (pending.length > 0) return;

    seoAutoStartedRef.current = true;
    void generateSeoFromAi({ onlyMissing: true, silent: true });
  }, [loadStatus, ladipage, searchParams, ladipageNeedsSeo, generateSeoFromAi]);

  // Tự động sinh nội dung tuần tự cho các section đang pending (ngay sau khi tạo bản nháp từ wizard).
  useEffect(() => {
    if (!ladipage || autogenStartedRef.current) return;
    if (searchParams.get('autogen') !== '1') return;
    const pending = ladipage.sections.filter((s) => s.status === 'pending');
    const needsSeo = ladipageNeedsSeo(ladipage);
    if (pending.length === 0 && !needsSeo) return;
    autogenStartedRef.current = true;

    (async () => {
      setAutogen({ running: true, current: 0, total: pending.length, label: '' });
      for (let i = 0; i < pending.length; i++) {
        setAutogen({
          running: true,
          current: i + 1,
          total: pending.length,
          label: SECTION_LABELS[pending[i].section_type] || pending[i].section_type,
        });
        try {
          // eslint-disable-next-line no-await-in-loop
          await generateSection(pending[i].id);
        } catch {
          // Lỗi đã toast trong generateSection — tiếp tục các mục còn lại.
        }
      }
      if (needsSeo) {
        setAutogen({
          running: true,
          current: pending.length,
          total: pending.length,
          label: 'SEO (meta title & mô tả)',
        });
        try {
          const fresh = await ladipageAdminAPI.get(ladipageId);
          if (ladipageNeedsSeo(fresh)) {
            seoAutoStartedRef.current = true;
            const updated = await ladipageAdminAPI.generateSeo(ladipageId, { onlyMissing: true });
            setLadipage(updated);
            setMetaTitleDraft(updated.meta_title || '');
            setMetaDescriptionDraft(updated.meta_description || '');
          } else {
            setLadipage(fresh);
            setMetaTitleDraft(fresh.meta_title || '');
            setMetaDescriptionDraft(fresh.meta_description || '');
          }
        } catch {
          // SEO thất bại — admin có thể bấm tạo lại thủ công hoặc effect bù SEO sẽ chạy sau redirect.
        }
      }
      setAutogen(null);
      router.replace(`/admin/ladipage/${ladipageId}/edit`);
    })();
  }, [ladipage, searchParams, generateSection, router, ladipageId, ladipageNeedsSeo]);

  const saveMeta = async () => {
    if (!ladipage) return;
    const slug = slugDraft.trim().toLowerCase();
    if (slug.length < 3) {
      pushToast({ title: 'Slug không hợp lệ', description: 'Slug cần ít nhất 3 ký tự.', variant: 'error', durationMs: 3500 });
      return;
    }
    if (
      ladipage.source_type === 'category' &&
      ladipage.include_material &&
      !materialFilterDraft.trim()
    ) {
      pushToast({
        title: 'Thiếu chất liệu',
        description: 'Ladipage danh mục có phần Chất liệu cần chọn lọc chất liệu.',
        variant: 'error',
        durationMs: 3500,
      });
      return;
    }
    const prevMaterial = (ladipage.material_filter || '').trim();
    const nextMaterial = materialFilterDraft.trim();
    setSavingMeta(true);
    try {
      const updated = await ladipageAdminAPI.update(ladipage.id, {
        title: titleDraft.trim(),
        admin_brief: briefDraft.trim(),
        slug,
        meta_title: metaTitleDraft.trim() || undefined,
        meta_description: metaDescriptionDraft.trim() || undefined,
        ...(ladipage.source_type === 'category'
          ? { material_filter: nextMaterial || '' }
          : {}),
      });
      setLadipage((prev) => (prev ? { ...prev, ...updated } : prev));
      setSlugDraft(updated.slug);
      setMaterialFilterDraft(updated.material_filter || '');
      setMetaTitleDraft(updated.meta_title || '');
      setMetaDescriptionDraft(updated.meta_description || '');
      if (updated.seo_collision_warning) {
        pushToast({
          title: 'Đã lưu — SEO đã chỉnh để tránh trùng danh mục',
          description: updated.seo_collision_warning,
          variant: 'success',
          durationMs: 5000,
        });
      } else if (
        ladipage.source_type === 'category' &&
        prevMaterial.toLowerCase() !== nextMaterial.toLowerCase()
      ) {
        pushToast({
          title: 'Đã lưu lọc chất liệu',
          description: 'Grid SP đã đổi theo chất liệu mới. Nên tạo lại phần Chất liệu (AI) cho khớp.',
          variant: 'success',
          durationMs: 4500,
        });
      } else {
        pushToast({ title: 'Đã lưu', variant: 'success', durationMs: 2000 });
      }
    } catch (err) {
      pushToast({ title: 'Lưu thất bại', description: errorMessage(err), variant: 'error', durationMs: 3500 });
    } finally {
      setSavingMeta(false);
    }
  };

  const fillSeoFromTitle = () => {
    void generateSeoFromAi();
  };

  const saveProducts = async () => {
    if (!ladipage || ladipage.source_type !== 'products') return;
    if (selectedProducts.length === 0) {
      pushToast({ title: 'Chưa chọn sản phẩm', description: 'Cần ít nhất 1 sản phẩm.', variant: 'error', durationMs: 3500 });
      return;
    }
    setSavingProducts(true);
    try {
      const updated = await ladipageAdminAPI.update(ladipage.id, {
        product_ids: selectedProducts.map((p) => p.id),
      });
      setLadipage((prev) => (prev ? { ...prev, ...updated } : prev));
      pushToast({ title: 'Đã cập nhật danh sách sản phẩm', variant: 'success', durationMs: 2000 });
    } catch (err) {
      pushToast({ title: 'Lưu thất bại', description: errorMessage(err), variant: 'error', durationMs: 3500 });
    } finally {
      setSavingProducts(false);
    }
  };

  const regenerateAllLadipage = useCallback(async () => {
    if (!ladipage) return;
    const targets = [...ladipage.sections]
      .sort((a, b) => a.order_index - b.order_index)
      .filter((s) => s.section_type !== 'products_grid');
    const totalSteps = targets.length + 1;

    setRegenerateModalOpen(false);
    setRegenerateConfirmText('');
    setAutogen({ running: true, current: 0, total: totalSteps, label: '' });

    let hadError = false;
    for (let i = 0; i < targets.length; i++) {
      const sec = targets[i];
      setAutogen({
        running: true,
        current: i + 1,
        total: totalSteps,
        label: SECTION_LABELS[sec.section_type] || sec.section_type,
      });
      setSectionBusy((s) => ({ ...s, [sec.id]: true }));
      try {
        const updated = await ladipageAdminAPI.regenerateSection(ladipageId, sec.id, { target: 'all' });
        patchSectionLocal(updated);
      } catch {
        hadError = true;
      } finally {
        setSectionBusy((s) => ({ ...s, [sec.id]: false }));
      }
    }

    setAutogen({
      running: true,
      current: totalSteps,
      total: totalSteps,
      label: 'SEO (meta title & mô tả)',
    });
    try {
      const updated = await ladipageAdminAPI.generateSeo(ladipageId, { onlyMissing: false });
      setLadipage(updated);
      setMetaTitleDraft(updated.meta_title || '');
      setMetaDescriptionDraft(updated.meta_description || '');
    } catch {
      hadError = true;
    }

    setAutogen(null);
    if (hadError) {
      pushToast({
        title: 'Tạo lại xong một phần',
        description: 'Một số section hoặc SEO thất bại — kiểm tra từng mục và thử lại.',
        variant: 'error',
        durationMs: 4500,
      });
    } else {
      pushToast({ title: 'Đã tạo lại toàn bộ ladipage', variant: 'success', durationMs: 3000 });
    }
  }, [ladipage, ladipageId, pushToast]);

  const deleteCurrentLadipage = useCallback(async () => {
    setDeleteBusy(true);
    try {
      await ladipageAdminAPI.remove(ladipageId);
      pushToast({ title: 'Đã xóa ladipage', variant: 'success', durationMs: 2500 });
      router.push('/admin/ladipage');
    } catch (err) {
      pushToast({
        title: 'Không xóa được',
        description: errorMessage(err),
        variant: 'error',
        durationMs: 4000,
      });
    } finally {
      setDeleteBusy(false);
      setDeleteModalOpen(false);
      setDeleteConfirmText('');
    }
  }, [ladipageId, pushToast, router]);

  const togglePublish = async () => {
    if (!ladipage) return;
    setPublishBusy(true);
    try {
      const nextStatus = ladipage.status === 'published' ? 'draft' : 'published';
      const updated = await ladipageAdminAPI.update(ladipage.id, { status: nextStatus });
      setLadipage((prev) => (prev ? { ...prev, ...updated } : prev));
      if (nextStatus === 'published') {
        setMetaTitleDraft(updated.meta_title || '');
        setMetaDescriptionDraft(updated.meta_description || '');
      }
      pushToast({
        title: nextStatus === 'published' ? 'Đã đăng trang' : 'Đã gỡ đăng',
        description: nextStatus === 'published' ? `Xem tại ${updated.public_url || `/lp/${updated.slug}`}` : undefined,
        variant: 'success',
        durationMs: 3000,
      });
    } catch (err) {
      pushToast({ title: 'Thao tác thất bại', description: errorMessage(err), variant: 'error', durationMs: 3500 });
    } finally {
      setPublishBusy(false);
    }
  };

  if (loadStatus === 'loading') {
    return (
      <div className="mx-auto max-w-5xl p-6">
        <div className="h-8 w-1/3 animate-pulse rounded bg-gray-200" />
        <div className="mt-6 space-y-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-40 animate-pulse rounded-xl bg-gray-100" />
          ))}
        </div>
      </div>
    );
  }

  if (loadStatus === 'error' || !ladipage) {
    return (
      <div className="mx-auto max-w-5xl p-6">
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {loadError || 'Không tải được ladipage'}{' '}
          <button type="button" onClick={load} className="font-medium underline">
            Thử lại
          </button>
        </div>
      </div>
    );
  }

  const sortedSections = [...ladipage.sections].sort((a, b) => a.order_index - b.order_index);

  return (
    <div className="mx-auto max-w-5xl p-4 pb-24 md:p-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Link href="/admin/ladipage" className="text-sm text-gray-500 hover:text-gray-700">
          ← Danh sách Ladipage
        </Link>
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${
              ladipage.status === 'published' ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-100 text-gray-600'
            }`}
          >
            {ladipage.status === 'published' ? 'Đã đăng' : 'Nháp'}
          </span>
          {ladipage.status === 'published' && (
            <a
              href={ladipage.public_url || `/lp/${ladipage.slug}`}
              target="_blank"
              rel="noreferrer"
              className="rounded-md border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
            >
              Xem trang public
            </a>
          )}
          <Link
            href="/admin/ladipage/new"
            className="rounded-md border border-orange-600 px-3 py-1.5 text-xs font-semibold text-orange-600 hover:bg-orange-50"
          >
            + Tạo ladipage mới
          </Link>
          <button
            type="button"
            disabled={!!autogen?.running || publishBusy || deleteBusy}
            onClick={() => {
              setRegenerateConfirmText('');
              setRegenerateModalOpen(true);
            }}
            className="rounded-md border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-800 hover:bg-amber-100 disabled:opacity-50"
          >
            Tạo lại toàn bộ
          </button>
          <button
            type="button"
            disabled={!!autogen?.running || publishBusy || deleteBusy}
            onClick={() => {
              setDeleteConfirmText('');
              setDeleteModalOpen(true);
            }}
            className="rounded-md border border-red-200 px-3 py-1.5 text-xs font-semibold text-red-600 hover:bg-red-50 disabled:opacity-50"
          >
            Xóa ladipage
          </button>
          <button
            type="button"
            disabled={publishBusy || !!autogen?.running || deleteBusy}
            onClick={togglePublish}
            className="rounded-md bg-orange-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-orange-700 disabled:opacity-50"
          >
            {publishBusy ? 'Đang lưu…' : ladipage.status === 'published' ? 'Gỡ đăng' : 'Đăng trang'}
          </button>
        </div>
      </div>

      {autogen?.running && (
        <div className="mb-6 rounded-xl border border-orange-200 bg-orange-50 p-4">
          <div className="mb-2 flex items-center justify-between text-sm font-medium text-orange-800">
            <span>
              Đang tạo nội dung AI ({autogen.current}/{autogen.total}): {autogen.label}
            </span>
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-orange-600 border-t-transparent" />
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-orange-100">
            <div
              className="h-full rounded-full bg-orange-600 transition-all"
              style={{ width: `${(autogen.current / Math.max(1, autogen.total)) * 100}%` }}
            />
          </div>
        </div>
      )}

      <div className="mb-6 rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
        <label className="mb-1 block text-xs font-medium text-gray-500">Tiêu đề ladipage</label>
        <input
          value={titleDraft}
          onChange={(e) => setTitleDraft(e.target.value)}
          className="w-full rounded-md border border-gray-300 p-2 text-sm font-semibold outline-none focus:border-orange-400"
        />
        <label className="mb-1 mt-3 block text-xs font-medium text-gray-500">Ý tưởng / định hướng nội dung</label>
        <textarea
          value={briefDraft}
          onChange={(e) => setBriefDraft(e.target.value)}
          rows={2}
          className="w-full rounded-md border border-gray-300 p-2 text-sm outline-none focus:border-orange-400"
        />
        {ladipage.source_type === 'category' && (
          <div className="mt-3">
            <label className="mb-1 block text-xs font-medium text-gray-500">
              Lọc chất liệu trong danh mục
              {ladipage.include_material ? ' (bắt buộc)' : ' (tuỳ chọn)'}
              {ladipage.category_name ? ` — ${ladipage.category_name}` : ''}
            </label>
            {materialsLoading ? (
              <div className="h-10 animate-pulse rounded-md bg-gray-100" />
            ) : (
              <select
                value={materialFilterDraft}
                onChange={(e) => setMaterialFilterDraft(e.target.value)}
                className="w-full rounded-md border border-gray-300 p-2 text-sm outline-none focus:border-orange-400"
              >
                <option value="">
                  {materialOptions.length ? '— Không lọc / chọn chất liệu —' : '— Không có chất liệu —'}
                </option>
                {materialOptions.map((m) => (
                  <option key={m.material} value={m.material}>
                    {m.material}
                    {m.count > 0 ? ` (${m.count} SP)` : ''}
                  </option>
                ))}
              </select>
            )}
            <p className="mt-1 text-xs text-gray-500">
              Grid chỉ lấy SP cùng chất liệu. Đổi chất liệu xong hãy tạo lại section Chất liệu nếu cần.
            </p>
          </div>
        )}
        <div className="mt-2 flex justify-end">
          <button
            type="button"
            disabled={savingMeta}
            onClick={saveMeta}
            className="rounded-md bg-gray-900 px-4 py-1.5 text-xs font-medium text-white hover:bg-gray-700 disabled:opacity-50"
          >
            {savingMeta ? 'Đang lưu…' : 'Lưu thông tin'}
          </button>
        </div>
      </div>

      {ladipage.source_type === 'category' && ladipage.seo_collision_warning ? (
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          {ladipage.seo_collision_warning}. Hệ thống đã cố tách USP khỏi trang danh mục/cluster.
          {ladipage.category_seo_path ? (
            <>
              {' '}
              Trang SEO chính:{' '}
              <a href={ladipage.category_seo_path} className="font-medium underline" target="_blank" rel="noreferrer">
                {ladipage.category_seo_path}
              </a>
            </>
          ) : null}
        </div>
      ) : null}

      <div className="mb-6 rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-gray-900">SEO &amp; URL public</h2>
          <button
            type="button"
            onClick={fillSeoFromTitle}
            disabled={generatingSeo}
            className="text-xs font-medium text-orange-700 hover:underline disabled:opacity-50"
          >
            {generatingSeo ? 'AI đang tạo SEO…' : '✨ AI tạo lại SEO'}
          </button>
        </div>
        {generatingSeo && (
          <p className="mb-2 text-xs text-orange-700">DeepSeek đang viết meta title và meta description…</p>
        )}
        <p className="mb-3 text-xs text-gray-500">
          Trang public:{' '}
          <a
            href={ladipage.public_url || `/lp/${slugDraft || ladipage.slug}`}
            target="_blank"
            rel="noreferrer"
            className="text-orange-700 hover:underline"
          >
            {ladipage.public_url || `/lp/${slugDraft || ladipage.slug}`}
          </a>
        </p>
        <label className="mb-1 block text-xs font-medium text-gray-500">Slug URL</label>
        <input
          value={slugDraft}
          onChange={(e) => setSlugDraft(e.target.value.toLowerCase().replace(/\s+/g, '-'))}
          className="w-full rounded-md border border-gray-300 p-2 font-mono text-sm outline-none focus:border-orange-400"
          placeholder="ao-thun-nam-cong-nghe"
        />
        <label className="mb-1 mt-3 block text-xs font-medium text-gray-500">Meta title (tab trình duyệt / Google)</label>
        <input
          value={metaTitleDraft}
          onChange={(e) => setMetaTitleDraft(e.target.value.slice(0, 500))}
          disabled={generatingSeo}
          className="w-full rounded-md border border-gray-300 p-2 text-sm outline-none focus:border-orange-400 disabled:bg-gray-50"
          placeholder={titleDraft || 'Tiêu đề hiển thị trên Google'}
        />
        <label className="mb-1 mt-3 block text-xs font-medium text-gray-500">
          Meta description{' '}
          <span className={metaDescriptionDraft.length > 160 ? 'text-amber-600' : 'text-gray-400'}>
            ({metaDescriptionDraft.length}/160 khuyến nghị)
          </span>
        </label>
        <textarea
          value={metaDescriptionDraft}
          onChange={(e) => setMetaDescriptionDraft(e.target.value.slice(0, 1000))}
          disabled={generatingSeo}
          rows={3}
          className="w-full rounded-md border border-gray-300 p-2 text-sm outline-none focus:border-orange-400 disabled:bg-gray-50"
          placeholder="Mô tả ngắn hiển thị trên kết quả tìm kiếm"
        />
        <div className="mt-2 flex justify-end">
          <button
            type="button"
            disabled={savingMeta || generatingSeo}
            onClick={saveMeta}
            className="rounded-md bg-orange-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-orange-700 disabled:opacity-50"
          >
            {savingMeta ? 'Đang lưu…' : 'Lưu SEO'}
          </button>
        </div>
      </div>

      {ladipage.source_type === 'products' && (
        <div className="mb-6 rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold text-gray-900">Sản phẩm trên ladipage</h2>
            <span className="text-xs text-gray-500">
              {selectedProducts.length === 1 ? 'Chế độ 1 sản phẩm' : `${selectedProducts.length} sản phẩm đã chọn`}
            </span>
          </div>
          {productsLoadStatus === 'loading' ? (
            <div className="h-24 animate-pulse rounded-md bg-gray-100" />
          ) : (
            <LadipageProductPicker
              mode={selectedProducts.length <= 1 ? 'single' : 'multi'}
              selectedProducts={selectedProducts}
              onChange={setSelectedProducts}
            />
          )}
          <div className="mt-3 flex justify-end">
            <button
              type="button"
              disabled={savingProducts || productsLoadStatus === 'loading' || selectedProducts.length === 0}
              onClick={() => void saveProducts()}
              className="rounded-md bg-gray-900 px-4 py-1.5 text-xs font-medium text-white hover:bg-gray-700 disabled:opacity-50"
            >
              {savingProducts ? 'Đang lưu…' : 'Lưu danh sách sản phẩm'}
            </button>
          </div>
        </div>
      )}

      <div className="space-y-4">
        {sortedSections.map((section) => (
          <div key={section.id} className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm md:p-6">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wide text-gray-400">
                {SECTION_LABELS[section.section_type] || section.section_type}
              </span>
              <div className="flex items-center gap-2">
                {section.section_type === 'material' && section.status === 'ready' && isSingleProductLadipage && (
                  <button
                    type="button"
                    disabled={sectionBusy[section.id]}
                    onClick={() => regenerateSection(section.id, { target: 'image' })}
                    className="rounded-full border border-gray-200 px-3 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50"
                  >
                    {sectionBusy[section.id]
                      ? 'Đang cập nhật…'
                      : (section.data as MaterialSectionData)?.image_source === 'product'
                        ? 'Cập nhật ảnh SP'
                        : 'Tạo lại ảnh AI'}
                  </button>
                )}
                {section.section_type === 'hero' && section.status === 'ready' && (
                  <button
                    type="button"
                    disabled={sectionBusy[section.id]}
                    onClick={() => regenerateSection(section.id, { target: 'image' })}
                    className="rounded-full border border-gray-200 px-3 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50"
                  >
                    {sectionBusy[section.id] ? 'Đang cập nhật…' : 'Cập nhật ảnh SP'}
                  </button>
                )}
                {section.status === 'pending' && section.section_type !== 'products_grid' && (
                  <button
                    type="button"
                    disabled={sectionBusy[section.id]}
                    onClick={() => generateSection(section.id)}
                    className="rounded-full bg-orange-600 px-3 py-1 text-xs font-medium text-white hover:bg-orange-700 disabled:opacity-50"
                  >
                    {sectionBusy[section.id] ? 'Đang tạo…' : '✨ Tạo nội dung AI'}
                  </button>
                )}
              </div>
            </div>

            {section.status === 'error' && (
              <div className="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
                {section.error_message || 'AI tạo nội dung thất bại.'}{' '}
                <button
                  type="button"
                  onClick={() => generateSection(section.id)}
                  className="font-medium underline"
                >
                  Thử lại
                </button>
              </div>
            )}

            {renderSectionBody(section, {
              busy: !!sectionBusy[section.id],
              onSaveField: (field, value) => saveSectionField(section, field, value),
              onSaveArrayItem: (arrayKey, idx, itemField, value) =>
                saveArrayItemField(section, arrayKey, idx, itemField, value),
              onRegenerateText: (instruction) =>
                regenerateSection(section.id, { target: 'text', custom_prompt: instruction || undefined }),
              onRegenerateAll: (instruction) =>
                regenerateSection(section.id, { target: 'all', custom_prompt: instruction || undefined }),
              onRegenerateImage: (prompt) =>
                regenerateSection(section.id, { target: 'image', custom_prompt: prompt || undefined }),
              resolvedProductIds: ladipage.resolved_product_ids,
              slug: ladipage.slug,
              heroImageOptions,
              heroProductsLoading: heroProductsStatus === 'loading',
              isSingleProductLadipage,
            })}
          </div>
        ))}
      </div>

      {regenerateModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true">
          <div className="w-full max-w-md rounded-xl bg-white p-5 shadow-xl">
            <h2 className="text-base font-semibold text-gray-900">Tạo lại toàn bộ ladipage?</h2>
            <p className="mt-2 text-sm text-gray-600">
              DeepSeek sẽ viết lại <strong>100% nội dung AI</strong> (hero, điểm mạnh, chất liệu, CTA, FAQ) và SEO meta.
              Ảnh chất liệu tuân theo chế độ hiện tại (ảnh SP hoặc AI). Tiêu đề/brief admin giữ nguyên.
            </p>
            <label className="mt-4 block text-xs font-medium text-gray-700">
              Gõ <code className="rounded bg-gray-100 px-1 py-0.5">{REGENERATE_ALL_CONFIRM_PHRASE}</code> để xác nhận
            </label>
            <input
              type="text"
              value={regenerateConfirmText}
              onChange={(e) => setRegenerateConfirmText(e.target.value)}
              placeholder={`Ví dụ: ${REGENERATE_ALL_CONFIRM_PHRASE}`}
              className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm outline-none focus:border-orange-400"
              autoComplete="off"
            />
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setRegenerateModalOpen(false);
                  setRegenerateConfirmText('');
                }}
                className="rounded-md px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100"
              >
                Hủy
              </button>
              <button
                type="button"
                disabled={!confirmPhraseMatches(regenerateConfirmText, REGENERATE_ALL_CONFIRM_PHRASE)}
                onClick={() => void regenerateAllLadipage()}
                className="rounded-md bg-amber-600 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-700 disabled:opacity-50"
              >
                Tạo lại toàn bộ
              </button>
            </div>
          </div>
        </div>
      )}

      {deleteModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true">
          <div className="w-full max-w-md rounded-xl bg-white p-5 shadow-xl">
            <h2 className="text-base font-semibold text-gray-900">Xóa ladipage này?</h2>
            <p className="mt-2 text-sm text-gray-600">
              Trang public và toàn bộ nội dung/ảnh đã tạo sẽ bị xóa vĩnh viễn. Dữ liệu sản phẩm không bị ảnh hưởng.
            </p>
            <label className="mt-4 block text-xs font-medium text-gray-700">
              Gõ <code className="rounded bg-gray-100 px-1 py-0.5">{DELETE_LADIPAGE_CONFIRM_PHRASE}</code> để xác nhận
            </label>
            <input
              type="text"
              value={deleteConfirmText}
              onChange={(e) => setDeleteConfirmText(e.target.value)}
              placeholder={`Ví dụ: ${DELETE_LADIPAGE_CONFIRM_PHRASE}`}
              className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm outline-none focus:border-red-400"
              autoComplete="off"
            />
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setDeleteModalOpen(false);
                  setDeleteConfirmText('');
                }}
                className="rounded-md px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100"
              >
                Hủy
              </button>
              <button
                type="button"
                disabled={
                  deleteBusy || !confirmPhraseMatches(deleteConfirmText, DELETE_LADIPAGE_CONFIRM_PHRASE)
                }
                onClick={() => void deleteCurrentLadipage()}
                className="rounded-md bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
              >
                {deleteBusy ? 'Đang xóa…' : 'Xóa vĩnh viễn'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

interface SectionBodyHandlers {
  busy: boolean;
  onSaveField: (field: string, value: unknown) => void | Promise<void>;
  onSaveArrayItem: (arrayKey: string, index: number, itemField: string, value: string) => void | Promise<void>;
  onRegenerateText: (instruction: string) => void | Promise<void>;
  onRegenerateAll: (instruction: string) => void | Promise<void>;
  onRegenerateImage: (prompt: string) => void | Promise<void>;
  resolvedProductIds: number[];
  slug: string;
  heroImageOptions: HeroImageOption[];
  heroProductsLoading: boolean;
  isSingleProductLadipage: boolean;
}

function renderSectionBody(section: LadipageSection, h: SectionBodyHandlers) {
  if (section.status === 'pending') {
    return <p className="italic text-gray-400">Chưa tạo nội dung — bấm &quot;Tạo nội dung AI&quot; ở trên.</p>;
  }

  switch (section.section_type) {
    case 'hero': {
      const data = section.data as HeroSectionData;
      return (
        <HeroSection
          data={data}
          editable
          isBusy={h.busy || h.heroProductsLoading}
          productImageOptions={h.heroImageOptions}
          onSaveField={(field, value) => h.onSaveField(field, value)}
          onRegenerateText={h.onRegenerateText}
        />
      );
    }
    case 'highlights': {
      const data = section.data as HighlightsSectionData;
      return (
        <HighlightsSection
          data={data}
          editable
          isBusy={h.busy}
          onSaveItem={(idx, field, value) => h.onSaveArrayItem('items', idx, field, value)}
          onRegenerate={h.onRegenerateAll}
        />
      );
    }
    case 'material': {
      const data = section.data as MaterialSectionData;
      return (
        <MaterialSection
          data={data}
          editable
          isBusy={h.busy || h.heroProductsLoading}
          singleProductMode={h.isSingleProductLadipage}
          productImageOptions={h.heroImageOptions}
          onSaveField={(field, value) => h.onSaveField(field, value)}
          onRegenerateText={h.onRegenerateText}
          onRegenerateImage={h.onRegenerateImage}
        />
      );
    }
    case 'trust_cta': {
      const data = section.data as TrustCtaSectionData;
      return (
        <TrustCtaSection
          data={data}
          editable
          isBusy={h.busy}
          onSaveField={(field, value) => h.onSaveField(field, value)}
          onRegenerate={h.onRegenerateAll}
        />
      );
    }
    case 'faq': {
      const data = section.data as FaqSectionData;
      return (
        <FaqSection
          data={data}
          editable
          isBusy={h.busy}
          onSaveItem={(idx, field, value) => h.onSaveArrayItem('items', idx, field, value)}
          onRegenerate={h.onRegenerateAll}
        />
      );
    }
    case 'products_grid':
      return <ProductsGridSection productIds={h.resolvedProductIds} source={`ladipage-editor:${h.slug}`} />;
    default:
      return null;
  }
}
