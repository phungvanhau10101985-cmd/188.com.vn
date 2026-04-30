'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import AdminLayout from '@/components/admin/AdminLayout';
import { apiClient } from '@/lib/api-client';
import { getApiBaseUrl, ngrokFetchHeaders } from '@/lib/api-base';
import {
  buildCategorySeoSitemapXml,
  CATEGORY_SEO_SITEMAP_PATH,
  flattenCategoryTreeForSitemap,
  triggerDownloadXml,
} from '@/lib/category-sitemap';
import { generateSlug } from '@/lib/utils';
import type { CategoryLevel1, CategoryLevel3 } from '@/types/api';

/** Phân tách cặp l2/l3 trong key multi-select */
const FROM_L2_L3_SEP = '\x1f';

/** Mọi từ (cách bằng khoảng trắng) đều phải có trong nhãn — thứ tự không quan trọng */
function labelMatchesTokenSearch(label: string, searchRaw: string): boolean {
  const tokens = searchRaw
    .trim()
    .toLowerCase()
    .split(/\s+/)
    .filter((t) => t.length > 0);
  if (tokens.length === 0) return true;
  const haystack = label.toLowerCase();
  return tokens.every((t) => haystack.includes(t));
}

type TabType = 'list' | 'rules';
type MappingItem = {
  id: number;
  from_category?: string | null;
  from_subcategory?: string | null;
  from_sub_subcategory?: string | null;
  to_category?: string | null;
  to_subcategory?: string | null;
  to_sub_subcategory?: string | null;
  created_at?: string | null;
};

interface FlatCategory {
  level: 1 | 2 | 3;
  name: string;
  slug: string;
  path: string;
  url: string;
  fullName: string;
}

type RedirectItem = {
  from: string;
  to: string;
  source_name: string;
  canonical_name: string;
};

type GeminiCatalogRow = {
  path: string;
  breadcrumb_label: string;
  level: number;
  product_count: number;
  has_seo_description: boolean;
  has_seo_body: boolean;
  gemini_enabled: boolean;
};

type CategorySeoAppSettingsSnap = {
  gemini_auto_enabled_admin: boolean;
  env_allows_gemini_auto: boolean;
  gemini_auto_effective: boolean;
  gemini_whitelist_only_env: boolean;
};

function slugOf(node: { name: string; slug?: string }): string {
  return (node.slug || node.name).toString().trim().toLowerCase().replace(/\s+/g, '-');
}

/** Giống slug URL backend / Navigation — không dùng slug chỉ lowercase có dấu. */
function slugFromPlainName(name: string): string {
  return generateSlug(name).replace(/^-+|-+$/g, '') || slugOf({ name });
}

/**
 * Ba tên danh mục đích (giống chuỗi hiển thị cột «Đến»): cấp 2 có thể lấy từ from_subcategory khi chỉ đích là cấp 3.
 */
function mappingDestinationSegmentNames(r: MappingItem): string[] {
  const t1 = r.to_category?.trim();
  if (!t1) return [];
  const hasT3 = !!(r.to_sub_subcategory && String(r.to_sub_subcategory).trim());
  const t2Raw = r.to_subcategory && String(r.to_subcategory).trim();
  const t2 = t2Raw
    ? String(r.to_subcategory).trim()
    : hasT3 && r.from_subcategory
      ? String(r.from_subcategory).trim()
      : '';
  const t3 = r.to_sub_subcategory?.trim();
  const parts = [t1];
  if (t2) parts.push(t2);
  if (t3) parts.push(t3);
  return parts;
}

/** URL `/danh-muc/slug1/...` tới danh mục đích đã map (ưu tiên slug trên cây đã tải). */
function mappingDestinationDanhMucPath(tree: CategoryLevel1[], r: MappingItem): string | null {
  const names = mappingDestinationSegmentNames(r);
  if (names.length === 0) return null;

  const slugs: string[] = [];
  const c1 = tree.find((c) => c.name === names[0]);
  slugs.push(c1 ? slugOf(c1) : slugFromPlainName(names[0]));

  if (names.length >= 2) {
    const c2 = c1?.children?.find((c) => c.name === names[1]);
    slugs.push(c2 ? slugOf(c2) : slugFromPlainName(names[1]));
  }
  if (names.length >= 3) {
    const l2 = c1?.children?.find((c) => c.name === names[1]);
    const l3list = l2?.children || [];
    const want = names[2];
    let foundObj: CategoryLevel3 | undefined;
    for (const c3 of l3list) {
      const nm =
        typeof c3 === 'object' && c3 !== null && 'name' in c3 ? (c3 as CategoryLevel3).name : String(c3);
      if (nm === want && typeof c3 === 'object' && c3 !== null) {
        foundObj = c3 as CategoryLevel3;
        break;
      }
    }
    slugs.push(foundObj ? slugOf(foundObj) : slugFromPlainName(names[2]));
  }

  return `/danh-muc/${slugs.map((s) => encodeURIComponent(s)).join('/')}`;
}

function flattenTree(tree: CategoryLevel1[]): FlatCategory[] {
  const out: FlatCategory[] = [];
  for (const c1 of tree) {
    const s1 = slugOf(c1);
    out.push({
      level: 1,
      name: c1.name,
      slug: s1,
      path: s1,
      url: `/danh-muc/${s1}`,
      fullName: c1.name,
    });
    for (const c2 of c1.children || []) {
      const s2 = slugOf(c2);
      const path2 = `${s1}/${s2}`;
      out.push({
        level: 2,
        name: c2.name,
        slug: s2,
        path: path2,
        url: `/danh-muc/${path2}`,
        fullName: `${c1.name} › ${c2.name}`,
      });
      const children3 = c2.children || [];
      for (const c3 of children3) {
        const name3 = typeof c3 === 'object' && c3 !== null && 'name' in c3 ? (c3 as CategoryLevel3).name : String(c3);
        const s3 = typeof c3 === 'object' && c3 !== null && 'slug' in c3 ? ((c3 as CategoryLevel3).slug || name3) : name3;
        const s3Norm = String(s3).trim().toLowerCase().replace(/\s+/g, '-');
        const path3 = `${path2}/${s3Norm}`;
        out.push({
          level: 3,
          name: name3,
          slug: s3Norm,
          path: path3,
          url: `/danh-muc/${path3}`,
          fullName: `${c1.name} › ${c2.name} › ${name3}`,
        });
      }
    }
  }
  return out;
}

export default function AdminDanhMucSeoPage() {
  const [tree, setTree] = useState<CategoryLevel1[]>([]);
  const [redirects, setRedirects] = useState<RedirectItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [activeTab, setActiveTab] = useState<TabType>('list');

  const [processing, setProcessing] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [geminiRows, setGeminiRows] = useState<GeminiCatalogRow[]>([]);
  const [geminiSummary, setGeminiSummary] = useState<Record<string, number> | null>(null);
  const [geminiLoading, setGeminiLoading] = useState(false);
  const [geminiBanner, setGeminiBanner] = useState<{ text: string; tone: 'success' | 'error' } | null>(null);
  const [geminiFilter, setGeminiFilter] = useState<'all' | 'targets' | 'missing_desc' | 'missing_body'>('all');
  const [geminiSearch, setGeminiSearch] = useState('');
  const [geminiRunPicked, setGeminiRunPicked] = useState<string[]>([]);
  const [geminiRunForceMeta, setGeminiRunForceMeta] = useState(false);
  const [geminiRunForceBody, setGeminiRunForceBody] = useState(false);
  const [geminiDelayInput, setGeminiDelayInput] = useState('1.2');
  const [geminiJobStatus, setGeminiJobStatus] = useState<any | null>(null);
  const geminiPollRef = useRef<number | null>(null);

  const [geminiAppSettings, setGeminiAppSettings] = useState<CategorySeoAppSettingsSnap | null>(null);
  const [geminiSettingsSaving, setGeminiSettingsSaving] = useState(false);
  const [sitemapDownloading, setSitemapDownloading] = useState(false);
  const [publicSitemapBase, setPublicSitemapBase] = useState('');

  const [mappings, setMappings] = useState<MappingItem[]>([]);
  const [mappingsLoading, setMappingsLoading] = useState(false);
  const [mappingForm, setMappingForm] = useState({
    from_category: '',
    from_subcategory: '',
    from_sub_subcategory: '',
    to_category: '',
    to_subcategory: '',
    to_sub_subcategory: '',
  });
  const [mappingEditId, setMappingEditId] = useState<number | null>(null);
  const [mappingJson, setMappingJson] = useState('');
  const [mappingReplace, setMappingReplace] = useState(false);
  /** Nguồn: chọn nhiều cấp 2 / nhiều cặp cấp 3 (chỉ khi tạo mới, không dùng khi sửa một dòng) */
  const [mappingSourceL2Multi, setMappingSourceL2Multi] = useState<string[]>([]);
  const [mappingSourceL3Multi, setMappingSourceL3Multi] = useState<string[]>([]);
  const [mappingSourceL2Search, setMappingSourceL2Search] = useState('');
  const [mappingSourceL3Search, setMappingSourceL3Search] = useState('');

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [treeData, redirectData] = await Promise.all([
        apiClient.getCategoryTreeFromProducts(),
        apiClient.getCategorySeoRedirects(),
      ]);
      setTree(Array.isArray(treeData) ? treeData : []);
      setRedirects(redirectData.redirects || []);
    } catch {
      setError('Không tải được danh mục');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    setPublicSitemapBase(window.location.origin);
  }, []);

  const level1Categories = useMemo(() => tree.map((c) => c.name), [tree]);
  const level2ByLevel1 = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const c1 of tree) {
      const list = (c1.children || []).map((c2) => c2.name).filter(Boolean);
      map.set(c1.name, Array.from(new Set(list)).sort());
    }
    return map;
  }, [tree]);

  const level3ByLevel1 = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const c1 of tree) {
      const set = new Set<string>();
      for (const c2 of c1.children || []) {
        for (const c3 of c2.children || []) {
          const name =
            typeof c3 === 'object' && c3 !== null && 'name' in c3 ? c3.name : String(c3);
          if (name) set.add(name);
        }
      }
      map.set(c1.name, Array.from(set).sort());
    }
    return map;
  }, [tree]);

  const combinedLevel23ByLevel1 = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const c1 of tree) {
      const set = new Set<string>();
      for (const c2 of c1.children || []) {
        if (c2?.name) set.add(c2.name);
        for (const c3 of c2.children || []) {
          const name =
            typeof c3 === 'object' && c3 !== null && 'name' in c3 ? c3.name : String(c3);
          if (name) set.add(name);
        }
      }
      map.set(c1.name, Array.from(set).sort());
    }
    return map;
  }, [tree]);

  function getLevel2Categories(categoryName: string) {
    const cat = tree.find((c) => c.name === categoryName);
    return cat?.children?.map((c) => c.name) || [];
  }

  function getLevel3Categories(categoryName: string, subcategoryName: string) {
    const cat = tree.find((c) => c.name === categoryName);
    const subcat = cat?.children?.find((c) => c.name === subcategoryName);
    return (subcat?.children || []).map((c) =>
      typeof c === 'object' && c !== null && 'name' in c ? c.name : String(c)
    );
  }

  function getLevel2Options(categoryName: string) {
    return getLevel2Categories(categoryName);
  }

  function getLevel3Options(categoryName: string, subcategoryName: string) {
    return getLevel3Categories(categoryName, subcategoryName);
  }

  /** Danh sách cấp 2 nguồn sau khi lọc từ khóa (giống logic cấp 3) */
  const level2OptionsFilteredForDisplay = useMemo(() => {
    if (!mappingForm.from_category) return [] as string[];
    const opts = getLevel2Options(mappingForm.from_category);
    if (!mappingSourceL2Search.trim()) return opts;
    return opts.filter((sub) => labelMatchesTokenSearch(sub, mappingSourceL2Search));
  }, [tree, mappingForm.from_category, mappingSourceL2Search]);

  /** Cặp (cấp 2 › cấp 3): chỉ các nhánh thuộc các cấp 2 nguồn đã chọn */
  const level3PairsUnderFromCategory = useMemo(() => {
    const catName = mappingForm.from_category;
    if (!catName) return [] as { key: string; label: string }[];
    const c1 = tree.find((c) => c.name === catName);
    if (!c1?.children?.length) return [];
    if (mappingSourceL2Multi.length === 0) return [];
    const allowed = new Set(mappingSourceL2Multi);
    const out: { key: string; label: string }[] = [];
    for (const c2 of c1.children || []) {
      const l2 = c2.name;
      if (!l2?.trim() || !allowed.has(l2)) continue;
      for (const c3 of c2.children || []) {
        const n3 =
          typeof c3 === 'object' && c3 !== null && 'name' in c3 ? (c3 as CategoryLevel3).name : String(c3);
        if (!String(n3).trim()) continue;
        const key = `${l2}${FROM_L2_L3_SEP}${n3}`;
        out.push({ key, label: `${l2} › ${n3}` });
      }
    }
    return out.sort((a, b) => a.label.localeCompare(b.label, 'vi'));
  }, [tree, mappingForm.from_category, mappingSourceL2Multi]);

  /** Danh sách cấp 3 hiển thị sau khi lọc từ khóa */
  const level3PairsFilteredForDisplay = useMemo(() => {
    if (!mappingSourceL3Search.trim()) return level3PairsUnderFromCategory;
    return level3PairsUnderFromCategory.filter(({ label }) =>
      labelMatchesTokenSearch(label, mappingSourceL3Search)
    );
  }, [level3PairsUnderFromCategory, mappingSourceL3Search]);

  /** Bỏ tick cấp 3 nếu không còn thuộc cấp 2 đang chọn */
  useEffect(() => {
    if (mappingEditId) return;
    const allowed = new Set(mappingSourceL2Multi);
    setMappingSourceL3Multi((prev) =>
      prev.filter((key) => {
        const i = key.indexOf(FROM_L2_L3_SEP);
        if (i <= 0) return false;
        const l2 = key.slice(0, i);
        return allowed.has(l2);
      })
    );
  }, [mappingSourceL2Multi, mappingEditId]);

  function toggleMappingSourceL2(name: string) {
    setMappingSourceL2Multi((prev) =>
      prev.includes(name) ? prev.filter((x) => x !== name) : [...prev, name]
    );
  }

  function toggleMappingSourceL3(key: string) {
    setMappingSourceL3Multi((prev) =>
      prev.includes(key) ? prev.filter((x) => x !== key) : [...prev, key]
    );
  }


  const loadMappings = async () => {
    setMappingsLoading(true);
    setError(null);
    try {
      const result = await apiClient.getFinalMappings();
      setMappings(result.mappings || []);
    } catch (err: any) {
      setError(err.message || 'Không tải được mapping');
    } finally {
      setMappingsLoading(false);
    }
  };

  async function loadGeminiCatalog() {
    setGeminiLoading(true);
    try {
      const [data, app] = await Promise.all([
        apiClient.getGeminiTargetsCatalog(),
        apiClient.getCategorySeoAppSettings(),
      ]);
      setGeminiRows(Array.isArray(data?.rows) ? data.rows : []);
      setGeminiSummary((data?.summary as Record<string, number>) ?? null);
      setGeminiAppSettings(app);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : typeof err === 'string' ? err : 'Không tải được catalog Gemini SEO';
      setGeminiBanner({ text: msg, tone: 'error' });
    } finally {
      setGeminiLoading(false);
    }
  }

  async function handlePersistGeminiAuto(enabled: boolean) {
    setGeminiSettingsSaving(true);
    setGeminiBanner(null);
    try {
      await apiClient.putCategorySeoAppSettings({ gemini_auto_enabled: enabled });
      await loadGeminiCatalog();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : typeof err === 'string' ? err : 'Không lưu được cài đặt';
      setGeminiBanner({ text: msg, tone: 'error' });
    } finally {
      setGeminiSettingsSaving(false);
    }
  }

  const loadGeminiJobStatus = async () => {
    try {
      const s = await apiClient.getGeminiTargetsJobStatus();
      setGeminiJobStatus(s);
      if (!s?.running && geminiPollRef.current) {
        window.clearInterval(geminiPollRef.current);
        geminiPollRef.current = null;
        await loadGeminiCatalog();
      }
    } catch {
      // ignore
    }
  };

  const startGeminiPolling = () => {
    if (geminiPollRef.current) {
      window.clearInterval(geminiPollRef.current);
    }
    geminiPollRef.current = window.setInterval(() => void loadGeminiJobStatus(), 2000);
    void loadGeminiJobStatus();
  };

  useEffect(() => {
    if (activeTab === 'list' && !loading) {
      void loadGeminiCatalog();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- chỉ khi mở tab / cây danh mục tải xong
  }, [activeTab, loading]);

  async function toggleGeminiTarget(path: string, enabled: boolean) {
    try {
      await apiClient.setGeminiTargets({ paths: [path], enabled });
      setGeminiRows((prev) => prev.map((r) => (r.path === path ? { ...r, gemini_enabled: enabled } : r)));
      await loadGeminiCatalog();
      setGeminiBanner(null);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : typeof err === 'string' ? err : 'Không cập nhật được Gemini đích';
      setGeminiBanner({ text: msg, tone: 'error' });
    }
  }

  const toggleGeminiRunPicked = (path: string) => {
    setGeminiRunPicked((prev) => (prev.includes(path) ? prev.filter((p) => p !== path) : [...prev, path]));
  };

  const handleGeminiRun = async (mode: 'whitelist' | 'picked') => {
    const whitelistTargets = geminiRows.filter((r) => r.gemini_enabled);
    if (mode === 'whitelist' && whitelistTargets.length === 0) {
      setGeminiBanner({
        text: 'Không có danh mục nào đánh dấu «Đích». Tick cột Đích ít nhất một dòng, hoặc dùng nút «Lần này».',
        tone: 'error',
      });
      return;
    }
    if (mode === 'picked' && geminiRunPicked.length === 0) {
      setGeminiBanner({
        text: 'Chưa chọn dòng nào trong cột «Lần này». Tick ít nhất một dòng rồi ấn lại.',
        tone: 'error',
      });
      return;
    }
    if (
      !confirm(
        'Gemini sẽ tạo/cập nhật meta và đoạn SEO cuối trang cho danh mục đã chọn. Việc này có thể vài phút và tốn quota API. Tiếp tục?'
      )
    )
      return;
    let paths: string[] | undefined;
    if (mode === 'picked') {
      paths = [...geminiRunPicked];
    }
    let delay = Number.parseFloat(geminiDelayInput.replace(',', '.'));
    if (!Number.isFinite(delay) || delay < 0) delay = 1.2;
    setProcessing(true);
    setGeminiBanner(null);
    try {
      await apiClient.runGeminiTargets({
        ...(paths !== undefined ? { paths } : {}),
        force_description: geminiRunForceMeta,
        force_body: geminiRunForceBody,
        delay,
      });
      setGeminiBanner({ text: 'Đã bắt đầu Gemini (meta + body). Xem tiến độ bên dưới.', tone: 'success' });
      startGeminiPolling();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : typeof err === 'string' ? err : 'Không khởi chạy được job';
      setGeminiBanner({ text: msg, tone: 'error' });
    } finally {
      setProcessing(false);
    }
  };

  const handleCreateOrUpdateMapping = async () => {
    if (!mappingForm.from_category || !mappingForm.to_category) {
      alert('Vui lòng nhập đủ thông tin');
      return;
    }
    setProcessing(true);
    setError(null);
    setSuccessMessage(null);
    try {
      const normalizedDestSubcategory = (fromSubForInfer: string) =>
        !mappingForm.to_subcategory.trim() && mappingForm.to_sub_subcategory.trim()
          ? fromSubForInfer
          : mappingForm.to_subcategory;

      const buildPayload = (from_subcategory: string, from_sub_subcategory: string) => ({
        from_category: mappingForm.from_category,
        from_subcategory: from_subcategory || '',
        from_sub_subcategory: from_sub_subcategory || '',
        to_category: mappingForm.to_category || mappingForm.from_category,
        to_subcategory: normalizedDestSubcategory(from_subcategory) || '',
        to_sub_subcategory: mappingForm.to_sub_subcategory || '',
      });

      if (mappingEditId) {
        const payload = buildPayload(mappingForm.from_subcategory, mappingForm.from_sub_subcategory);
        const res = await apiClient.updateFinalMapping(mappingEditId, payload);
        const n = res.products_updated ?? 0;
        setSuccessMessage(`✅ Đã cập nhật mapping. ${n} sản phẩm khớp nguồn đã chuyển sang đích.`);
      } else {
        const l2HasSelectedL3 = new Set<string>();
        for (const key of mappingSourceL3Multi) {
          const i = key.indexOf(FROM_L2_L3_SEP);
          if (i <= 0) continue;
          l2HasSelectedL3.add(key.slice(0, i));
        }
        const expanded: { fs: string; fss: string }[] = [];
        for (const key of mappingSourceL3Multi) {
          const i = key.indexOf(FROM_L2_L3_SEP);
          if (i === -1) continue;
          const l2 = key.slice(0, i);
          const l3 = key.slice(i + FROM_L2_L3_SEP.length);
          expanded.push({ fs: l2, fss: l3 });
        }
        for (const l2 of mappingSourceL2Multi) {
          if (l2HasSelectedL3.has(l2)) {
            continue;
          }
          expanded.push({ fs: l2, fss: '' });
        }
        const seen = new Set<string>();
        const uniq = expanded.filter((r) => {
          const k = `${r.fs}\u0000${r.fss}`;
          if (seen.has(k)) return false;
          seen.add(k);
          return true;
        });
        if (uniq.length === 0) {
          alert('Vui lòng chọn ít nhất một danh mục nguồn cấp 2 hoặc một nhánh cấp 3');
          return;
        }
        let created = 0;
        let productsUpdated = 0;
        for (const row of uniq) {
          const res = await apiClient.createFinalMapping(buildPayload(row.fs, row.fss));
          created += 1;
          productsUpdated += res.products_updated ?? 0;
        }
        setSuccessMessage(
          `✅ Đã tạo ${created} mapping. ${productsUpdated} sản phẩm khớp nguồn (cấp 3 đã chọn) đã chuyển sang đích — cấp 3 khác không đổi.`
        );
      }
      setMappingForm({
        from_category: '',
        from_subcategory: '',
        from_sub_subcategory: '',
        to_category: '',
        to_subcategory: '',
        to_sub_subcategory: '',
      });
      setMappingSourceL2Multi([]);
      setMappingSourceL3Multi([]);
      setMappingSourceL2Search('');
      setMappingSourceL3Search('');
      setMappingEditId(null);
      await loadMappings();
      await loadData();
    } catch (err: any) {
      setError(err.message || 'Có lỗi xảy ra');
    } finally {
      setProcessing(false);
    }
  };

  const handleEditMapping = (mapping: MappingItem) => {
    setMappingEditId(mapping.id);
    setMappingSourceL2Multi([]);
    setMappingSourceL3Multi([]);
    setMappingSourceL2Search('');
    setMappingSourceL3Search('');
    setMappingForm({
      from_category: mapping.from_category || '',
      from_subcategory: mapping.from_subcategory || '',
      from_sub_subcategory: mapping.from_sub_subcategory || '',
      to_category: mapping.to_category || '',
      to_subcategory: mapping.to_subcategory || '',
      to_sub_subcategory: mapping.to_sub_subcategory || '',
    });
  };

  const handleDeleteMapping = async (id: number) => {
    if (!confirm('Xóa mapping này?')) return;
    setProcessing(true);
    try {
      await apiClient.deleteFinalMapping(id);
      await loadMappings();
    } finally {
      setProcessing(false);
    }
  };

  const handleApplyMappings = async () => {
    if (!confirm('Áp dụng mapping cho sản phẩm cũ?')) return;
    setProcessing(true);
    try {
      const result = await apiClient.applyFinalMappings();
      setSuccessMessage(`✅ Đã cập nhật ${result.updated} sản phẩm`);
    } finally {
      setProcessing(false);
    }
  };

  const handleExportMappings = async () => {
    const result = await apiClient.exportFinalMappings();
    setMappingJson(JSON.stringify(result, null, 2));
  };

  const handleImportMappings = async () => {
    let parsed: any;
    try {
      parsed = JSON.parse(mappingJson || '{}');
    } catch {
      alert('JSON không hợp lệ');
      return;
    }
    setProcessing(true);
    try {
      const res = await apiClient.importFinalMappings({ mappings: parsed.mappings || [], replace: mappingReplace });
      const pu = res.products_updated ?? 0;
      setSuccessMessage(
        `✅ Import xong (${res.created} mapping${pu ? `; ${pu} sản phẩm khớp nguồn cấp 3 đã cập nhật` : ''}).`
      );
      await loadMappings();
    } finally {
      setProcessing(false);
    }
  };

  const filteredGeminiRows = useMemo(() => {
    let r = geminiRows;
    if (geminiFilter === 'targets') r = r.filter((x) => x.gemini_enabled);
    if (geminiFilter === 'missing_desc') r = r.filter((x) => x.gemini_enabled && !x.has_seo_description);
    if (geminiFilter === 'missing_body') r = r.filter((x) => x.gemini_enabled && !x.has_seo_body);
    if (geminiSearch.trim()) {
      const q = geminiSearch.trim().toLowerCase();
      r = r.filter((x) => x.path.includes(q) || x.breadcrumb_label.toLowerCase().includes(q));
    }
    return r;
  }, [geminiRows, geminiFilter, geminiSearch]);


  const redirectMap = useMemo(() => {
    const m = new Map<string, string>();
    redirects.forEach((r) => m.set(r.from, r.to));
    return m;
  }, [redirects]);

  const flat = useMemo(() => flattenTree(tree), [tree]);
  const filtered = useMemo(() => {
    if (!search.trim()) return flat;
    const q = search.trim().toLowerCase();
    return flat.filter(
      (row) => row.name.toLowerCase().includes(q) || row.fullName.toLowerCase().includes(q) || row.path.toLowerCase().includes(q)
    );
  }, [flat, search]);

  const handleDownloadCategorySitemap = async () => {
    const siteBase =
      (process.env.NEXT_PUBLIC_SITE_URL ||
        process.env.NEXT_PUBLIC_DOMAIN ||
        (typeof window !== 'undefined' ? window.location.origin : '')
      ).replace(/\/$/, '') || '';
    if (!siteBase) return;
    setSitemapDownloading(true);
    try {
      const indexedClusterUrls: string[] = [];
      try {
        const res = await fetch(`${getApiBaseUrl()}/seo-clusters/`, {
          headers: { 'Content-Type': 'application/json', ...ngrokFetchHeaders() },
        });
        if (res.ok) {
          const data = (await res.json()) as Array<{ slug?: string; index_policy?: string }>;
          if (Array.isArray(data)) {
            for (const c of data) {
              if (!c.slug || c.index_policy !== 'index') continue;
              indexedClusterUrls.push(
                `${siteBase}/c/${encodeURIComponent(String(c.slug).replace(/^\/+|\/+$/g, ''))}`
              );
            }
          }
        }
      } catch {
        /* bỏ qua cluster — vẫn tải sitemap chỉ danh mục */
      }
      const xml = buildCategorySeoSitemapXml({
        siteBase,
        categories: flattenCategoryTreeForSitemap(tree),
        indexedClusterAbsoluteUrls: indexedClusterUrls,
      });
      const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
      triggerDownloadXml(`sitemap-danh-muc-seo-${stamp}.xml`, xml);
    } finally {
      setSitemapDownloading(false);
    }
  };

  return (
    <AdminLayout>
      <div className="p-6 max-w-7xl">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Quản lý danh mục SEO</h1>
        <p className="text-gray-600 text-sm mb-4">Sitemap · sinh SEO danh mục (Gemini) · mapping nguồn → đích.</p>

        <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-gray-200 bg-gray-50/90 px-4 py-3">
          <div className="max-w-xl text-sm text-gray-700">
            <span className="font-semibold text-gray-900">Sitemap XML danh mục</span>
            <p className="mt-1 text-xs text-gray-600">Dùng Search Console hoặc tải file .xml.</p>
            <details className="mt-2 text-xs text-gray-600">
              <summary className="cursor-pointer select-none text-gray-700 hover:underline">Chi tiết URL &amp; phạm vi</summary>
              <p className="mt-2 leading-snug">
                Gồm <code className="text-[11px]">/danh-muc</code>, các nhánh từ API, và <code className="text-[11px]">/c/&lt;slug&gt;</code> được
                index — cùng nội dung với file tải xuống.
              </p>
              <p className="mt-2 text-[11px]">
                URL:{` `}
                <code className="break-all rounded bg-white/80 px-1 py-0.5 text-[11px] text-[#c2410c]">
                  {publicSitemapBase}
                  {CATEGORY_SEO_SITEMAP_PATH}
                </code>
              </p>
            </details>
          </div>
          <div className="flex shrink-0 flex-col gap-2 sm:flex-row sm:items-center">
            <Link
              href={CATEGORY_SEO_SITEMAP_PATH}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center rounded-lg bg-[#ea580c] px-4 py-2 text-center text-sm font-medium text-white hover:bg-[#c2410c]"
            >
              Mở sitemap (tab mới)
            </Link>
            <button
              type="button"
              onClick={() => void handleDownloadCategorySitemap()}
              disabled={loading || sitemapDownloading}
              className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-800 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {sitemapDownloading ? 'Đang tạo file…' : 'Tải file .xml'}
            </button>
          </div>
        </div>

        <div className="mb-6 border-b border-gray-200">
          <nav className="-mb-px flex space-x-8">
            <button
              onClick={() => setActiveTab('list')}
              className={`py-4 px-1 border-b-2 font-medium text-sm ${
                activeTab === 'list'
                  ? 'border-[#ea580c] text-[#ea580c]'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              Danh mục &amp; Gemini
            </button>
            <button
              onClick={async () => {
                setActiveTab('rules');
                if (mappings.length === 0) await loadMappings();
              }}
              className={`py-4 px-1 border-b-2 font-medium text-sm ${
                activeTab === 'rules'
                  ? 'border-[#ea580c] text-[#ea580c]'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              Xem mapping
            </button>
          </nav>
        </div>

        {successMessage && (
          <div className="mb-4 p-4 bg-green-50 border border-green-200 rounded-lg text-green-800">{successMessage}</div>
        )}
        {error && activeTab !== 'list' && (
          <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-800">{error}</div>
        )}

        {loading ? (
          <p className="text-gray-500">Đang tải...</p>
        ) : (
          <>
            {activeTab === 'list' && (
              <div>
                <div className="mb-6 rounded-xl border border-orange-100 bg-gradient-to-b from-orange-50/50 to-orange-50/20 p-4 space-y-4">
                  <div>
                    <h2 className="text-lg font-semibold text-gray-900">Sinh nội dung SEO bằng Gemini</h2>
                    <p className="mt-0.5 text-xs text-gray-500">Meta mô tả + đoạn văn cuối trang danh mục (slug giống URL /danh-muc/...).</p>

                    <div className="mt-3 rounded-lg border border-orange-200/80 bg-white p-3 text-xs text-gray-700 shadow-sm">
                      <p className="font-semibold text-gray-900">Cách làm (chọn một)</p>
                      <ul className="mt-2 list-none space-y-2 pl-0">
                        <li className="flex gap-2">
                          <span
                            className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#ea580c] text-[11px] font-bold text-white"
                            aria-hidden
                          >
                            A
                          </span>
                          <span>
                            <strong className="text-gray-900">Chạy theo nhóm cố định:</strong> tick cột <strong>Đích</strong> (lưu server) → bấm{' '}
                            <strong className="text-[#c2410c]">nút cam</strong>.
                          </span>
                        </li>
                        <li className="flex gap-2">
                          <span
                            className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gray-600 text-[11px] font-bold text-white"
                            aria-hidden
                          >
                            B
                          </span>
                          <span>
                            <strong className="text-gray-900">Chạy vài dòng trong lần này:</strong> tick cột <strong>Lần này</strong> (không lưu) →
                            bấm <strong>nút xám</strong>.
                          </span>
                        </li>
                      </ul>
                      <p className="mt-2 border-t border-gray-100 pt-2 text-[11px] text-gray-500">
                        Lọc «Đích thiếu meta/body»: chỉ dùng khi đã có ít nhất một dòng tick <strong>Đích</strong>. Xem SEO trên web: dùng «Xóa sạch
                        cache» (menu admin).
                      </p>
                    </div>

                    {geminiAppSettings && (
                      <details className="mt-3 rounded-lg border border-orange-200/70 bg-white/90 px-3 py-2 text-xs text-gray-700">
                        <summary className="cursor-pointer select-none font-medium text-gray-900 hover:text-[#c2410c]">
                          Tự động sau khi import / lưu sản phẩm (tuỳ cấu hình server)
                        </summary>
                        <div className="mt-3 space-y-2 border-t border-gray-100 pt-3">
                          <div className="flex flex-wrap items-center gap-2">
                            <button
                              type="button"
                              onClick={() => void handlePersistGeminiAuto(false)}
                              disabled={geminiSettingsSaving}
                              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                                !geminiAppSettings.gemini_auto_enabled_admin
                                  ? 'border-2 border-[#ea580c] bg-orange-50 text-[#c2410c]'
                                  : 'border border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
                              } disabled:opacity-50`}
                            >
                              Không auto — chỉ bấm nút tay
                            </button>
                            <button
                              type="button"
                              onClick={() => void handlePersistGeminiAuto(true)}
                              disabled={geminiSettingsSaving || !geminiAppSettings.env_allows_gemini_auto}
                              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                                geminiAppSettings.gemini_auto_enabled_admin
                                  ? 'border-2 border-[#ea580c] bg-orange-50 text-[#c2410c]'
                                  : 'border border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
                              } disabled:opacity-50`}
                            >
                              Bật auto
                            </button>
                            {geminiSettingsSaving && <span className="text-gray-500">Đang lưu…</span>}
                          </div>
                          <p className="text-gray-700">
                            Trạng thái thực tế:{` `}
                            <strong>{geminiAppSettings.gemini_auto_effective ? 'Đang bật auto' : 'Đang tắt auto'}</strong>
                            {!geminiAppSettings.gemini_auto_effective && ' — chỉ chạy bằng nút Sinh SEO bên dưới.'}
                          </p>
                          {!geminiAppSettings.env_allows_gemini_auto && (
                            <p className="rounded bg-amber-50 px-2 py-1 text-amber-900">
                              Môi trường này chưa cho auto (thiếu <span className="font-mono">CATEGORY_GEMINI_SEO_AUTO_ENABLED</span> + production/staging nếu
                              có quy định).
                            </p>
                          )}
                          {geminiAppSettings.env_allows_gemini_auto && geminiAppSettings.gemini_whitelist_only_env && (
                            <p className="text-gray-600">Auto chỉ áp dụng cho path đã tick <strong>Đích</strong> (whitelist trong .env).</p>
                          )}
                        </div>
                      </details>
                    )}

                    <details className="mt-2 text-[11px] text-gray-500">
                      <summary className="cursor-pointer select-none hover:text-gray-700">API (cho dev)</summary>
                      <p className="mt-2 font-mono leading-relaxed text-gray-700">
                        GET/PUT /category-seo/app-settings · PUT /category-seo/gemini-targets · POST /category-seo/gemini-targets/run
                      </p>
                      <p className="mt-2 text-gray-600">
                        Body-only riêng (ít dùng): POST /category-seo/seo-bodies/generate
                      </p>
                    </details>
                  </div>

                  {geminiSummary && (
                    <div>
                      <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-gray-500">Thống kê catalog</p>
                      <div className="flex flex-wrap gap-x-3 gap-y-1 rounded-md bg-white px-2 py-1.5 text-[11px] text-gray-700 ring-1 ring-orange-100/80">
                      <span>
                        Tổng <strong>{geminiSummary.paths_total ?? 0}</strong>
                      </span>
                      <span className="text-gray-300">|</span>
                      <span>
                        Có SP <strong>{geminiSummary.with_products ?? 0}</strong>
                      </span>
                      <span className="text-gray-300">|</span>
                      <span>
                        Đích <strong>{geminiSummary.gemini_target_count ?? 0}</strong>
                      </span>
                      <span className="text-gray-300">|</span>
                      <span>
                        Đích thiếu meta <strong>{geminiSummary.gemini_missing_description ?? 0}</strong>
                      </span>
                      <span className="text-gray-300">|</span>
                      <span>
                        Đích thiếu body <strong>{geminiSummary.gemini_missing_body ?? 0}</strong>
                      </span>
                      <span className="text-gray-300">|</span>
                      <span>
                        Chưa đích <strong>{geminiSummary.not_marked_for_gemini ?? 0}</strong>
                      </span>
                    </div>
                    </div>
                  )}
                  <div className="space-y-4">
                    <div>
                      <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-500">Tìm và lọc</p>
                      <div className="mt-1 flex flex-wrap items-center gap-2">
                        <input
                          type="text"
                          value={geminiSearch}
                          onChange={(e) => setGeminiSearch(e.target.value)}
                          placeholder="Tìm breadcrumb hoặc slug path…"
                          className="rounded-lg border border-gray-300 px-3 py-2 text-sm w-56 max-w-full"
                        />
                        <select
                          value={geminiFilter}
                          onChange={(e) => setGeminiFilter(e.target.value as typeof geminiFilter)}
                          className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
                        >
                          <option value="all">Tất cả danh mục</option>
                          <option value="targets">Chỉ các dòng là Đích</option>
                          <option value="missing_desc">Trong các Đích: còn thiếu meta</option>
                          <option value="missing_body">Trong các Đích: còn thiếu body</option>
                        </select>
                        <button
                          type="button"
                          onClick={() => void loadGeminiCatalog()}
                          disabled={geminiLoading}
                          className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                        >
                          {geminiLoading ? 'Đang tải...' : 'Làm mới'}
                        </button>
                      </div>
                    </div>

                    <div>
                      <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-500">Chạy Gemini</p>
                      <div className="mt-1 flex flex-wrap items-center gap-2">
                        <button
                          type="button"
                          onClick={() => void handleGeminiRun('whitelist')}
                          disabled={processing}
                          className="rounded-lg border border-[#ea580c] bg-[#ea580c] px-3 py-2 text-sm font-medium text-white hover:bg-[#c2410c] disabled:opacity-50"
                        >
                          Sinh SEO — mọi dòng là Đích
                        </button>
                        <button
                          type="button"
                          onClick={() => void handleGeminiRun('picked')}
                          disabled={processing}
                          className="rounded-lg border border-gray-400 bg-white px-3 py-2 text-sm font-medium text-gray-800 hover:bg-gray-50 disabled:opacity-50"
                        >
                          Sinh SEO — các dòng tick «Lần này»
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            const pathsShown = filteredGeminiRows.map((r) => r.path);
                            const allMarked = pathsShown.length > 0 && pathsShown.every((p) => geminiRunPicked.includes(p));
                            if (allMarked) {
                              setGeminiRunPicked((prev) => prev.filter((p) => !pathsShown.includes(p)));
                            } else {
                              setGeminiRunPicked((prev) => Array.from(new Set([...prev, ...pathsShown])));
                            }
                          }}
                          className="rounded-lg border border-gray-300 bg-white px-2 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
                        >
                          {filteredGeminiRows.every((r) => geminiRunPicked.includes(r.path)) && filteredGeminiRows.length > 0
                            ? 'Bỏ «Lần này» trên các dòng đang xem'
                            : 'Tick hết «Lần này» các dòng đang xem'}
                        </button>
                      </div>
                      <p className="mt-1.5 text-[11px] text-gray-500">Nút cam dùng cột Đích. Nút viền xám dùng cột «Lần này».</p>
                    </div>

                    <div>
                      <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-500">Tuỳ chọn sinh</p>
                      <div className="mt-1 flex flex-wrap items-center gap-4 text-xs text-gray-600">
                        <label className="flex cursor-pointer items-center gap-2">
                          <input
                            type="checkbox"
                            checked={geminiRunForceMeta}
                            onChange={(e) => setGeminiRunForceMeta(e.target.checked)}
                          />
                          Luôn ghi đè meta cũ
                        </label>
                        <label className="flex cursor-pointer items-center gap-2">
                          <input
                            type="checkbox"
                            checked={geminiRunForceBody}
                            onChange={(e) => setGeminiRunForceBody(e.target.checked)}
                          />
                          Luôn ghi đè đoạn body cũ
                        </label>
                        <label className="flex items-center gap-2">
                          Nghỉ giữa mỗi lần (giây)
                          <input
                            type="text"
                            value={geminiDelayInput}
                            onChange={(e) => setGeminiDelayInput(e.target.value)}
                            className="w-12 rounded border border-gray-300 px-1.5 py-0.5 font-mono text-xs"
                          />
                        </label>
                      </div>
                    </div>
                  </div>
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-500">Danh mục trong catalog (slug = /danh-muc/…)</p>
                  {geminiBanner && (
                    <p
                      className={
                        geminiBanner.tone === 'error'
                          ? 'mt-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900'
                          : 'mt-2 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900'
                      }
                      role={geminiBanner.tone === 'error' ? 'alert' : 'status'}
                    >
                      {geminiBanner.text}
                    </p>
                  )}
                  <div className="mt-1 max-h-72 overflow-auto rounded-lg border border-gray-200 bg-white">
                    <table className="w-full text-left text-xs">
                      <thead className="sticky top-0 bg-gray-100 text-[11px] uppercase tracking-wide text-gray-600">
                        <tr>
                          <th className="px-2 py-2">Breadcrumb</th>
                          <th className="px-2 py-2 font-mono">Path</th>
                          <th className="px-2 py-2 text-center">SP</th>
                          <th className="px-2 py-2 text-center" title="Đã có meta (Gemini/thủ công)?">
                            Meta
                          </th>
                          <th className="px-2 py-2 text-center" title="Đã có đoạn cuối trang (Gemini/thủ công)?">
                            Body
                          </th>
                          <th className="px-2 py-2 text-center" title="Whitelist lưu DB">
                            Đích
                          </th>
                          <th className="px-2 py-2 text-center" title="Chỉ phiên hiện tại">
                            Lần này
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredGeminiRows.length === 0 ? (
                          <tr>
                            <td colSpan={7} className="px-3 py-8 text-center text-gray-500">
                              {geminiLoading
                                ? 'Đang tải...'
                                : 'Không có dòng nào khớp lọc — thử «Tất cả danh mục» hoặc tick vài ô Đích rồi Làm mới.'}
                            </td>
                          </tr>
                        ) : (
                          filteredGeminiRows.map((row) => (
                            <tr key={row.path} className="border-t border-gray-100 hover:bg-gray-50/80">
                              <td className="max-w-[200px] px-2 py-1.5 text-gray-800">{row.breadcrumb_label}</td>
                              <td className="px-2 py-1.5 font-mono text-[11px] text-gray-700">{row.path}</td>
                              <td className="px-2 py-1.5 text-center tabular-nums">{row.product_count}</td>
                              <td className="px-2 py-1.5 text-center">{row.has_seo_description ? '✓' : '—'}</td>
                              <td className="px-2 py-1.5 text-center">{row.has_seo_body ? '✓' : '—'}</td>
                              <td className="px-2 py-1.5 text-center">
                                <input
                                  type="checkbox"
                                  checked={row.gemini_enabled}
                                  onChange={(e) => void toggleGeminiTarget(row.path, e.target.checked)}
                                  aria-label="Đích — lưu trên server"
                                />
                              </td>
                              <td className="px-2 py-1.5 text-center">
                                <input
                                  type="checkbox"
                                  checked={geminiRunPicked.includes(row.path)}
                                  onChange={() => toggleGeminiRunPicked(row.path)}
                                  aria-label="Chạy trong lần mở trang này"
                                />
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                  {geminiJobStatus && geminiJobStatus.total > 0 && (
                    <div className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-[11px] text-gray-700">
                      <span className="font-medium">{geminiJobStatus.running ? 'Đang chạy' : 'Hoàn tất'}</span>
                      <span className="mx-1.5 text-gray-300">·</span>
                      <span>
                        {geminiJobStatus.processed ?? 0}/{geminiJobStatus.total ?? 0}
                      </span>
                      <span className="mx-1.5 text-gray-300">·</span>
                      <span>meta +{geminiJobStatus.meta_generated ?? 0}</span>
                      <span className="text-gray-400"> ~{geminiJobStatus.meta_skipped ?? 0}</span>
                      <span className="mx-1.5 text-gray-300">·</span>
                      <span>body +{geminiJobStatus.body_generated ?? 0}</span>
                      <span className="text-gray-400"> ~{geminiJobStatus.body_skipped ?? 0}</span>
                      <span className="mx-1.5 text-gray-300">·</span>
                      <span className={geminiJobStatus.failed ? 'text-red-700' : ''}>lỗi {geminiJobStatus.failed ?? 0}</span>
                      {geminiJobStatus.current_path && geminiJobStatus.running ? (
                        <div className="mt-1 truncate font-mono text-[10px] text-gray-500">
                          → {geminiJobStatus.current_path}
                        </div>
                      ) : null}
                    </div>
                  )}
                </div>

                <div className="mb-2">
                  <h2 className="text-base font-semibold text-gray-900">Cây danh mục hiển thị trên web</h2>
                  <p className="text-xs text-gray-500">
                    URL và redirect (nếu có). Tìm trong bảng Gemini phía trên nếu chỉ cần sinh SEO cho path.
                  </p>
                </div>

                <div className="mb-4 flex flex-wrap items-center gap-3">
                  <input
                    type="text"
                    placeholder="Tìm theo tên hoặc slug..."
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="border border-gray-300 rounded-lg px-3 py-2 text-sm w-64"
                  />
                  <span className="text-sm text-gray-500">
                    {filtered.length} / {flat.length} danh mục
                  </span>
                  <button
                    type="button"
                    onClick={async () => {
                      await loadData();
                      if (activeTab === 'list') {
                        await loadGeminiCatalog();
                      }
                    }}
                    disabled={loading}
                    className="px-3 py-2 text-sm font-medium rounded-lg border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                  >
                    {loading ? 'Đang tải...' : 'Làm mới'}
                  </button>
                </div>

                <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-gray-50 border-b border-gray-200">
                        <th className="text-left py-3 px-4 font-semibold text-gray-700 w-20">Cấp</th>
                        <th className="text-left py-3 px-4 font-semibold text-gray-700">Tên</th>
                        <th className="text-left py-3 px-4 font-semibold text-gray-700">Path (slug)</th>
                        <th className="text-left py-3 px-4 font-semibold text-gray-700">URL</th>
                        <th className="text-left py-3 px-4 font-semibold text-gray-700 min-w-[140px]">Trạng thái SEO</th>
                        <th className="text-left py-3 px-4 font-semibold text-gray-700 w-28">Thao tác</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filtered.map((row, i) => (
                        <tr key={`${row.path}-${i}`} className="border-b border-gray-100 hover:bg-gray-50/50">
                          <td className="py-2 px-4">
                            <span
                              className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${
                                row.level === 1
                                  ? 'bg-orange-100 text-orange-800'
                                  : row.level === 2
                                    ? 'bg-amber-100 text-amber-800'
                                    : 'bg-gray-100 text-gray-700'
                              }`}
                            >
                              Cấp {row.level}
                            </span>
                          </td>
                          <td className="py-2 px-4 font-medium text-gray-900">{row.fullName}</td>
                          <td className="py-2 px-4 text-gray-600 font-mono text-xs">{row.path}</td>
                          <td className="py-2 px-4 text-gray-600 truncate max-w-xs">{row.url}</td>
                          <td className="py-2 px-4 text-sm">
                            {redirectMap.get(row.url) ? (
                              <span className="text-amber-700" title="Trang này 301 về URL canonical">
                                → 301 → <span className="font-mono text-xs">{redirectMap.get(row.url)}</span>
                              </span>
                            ) : (
                              <span className="text-green-700">Canonical</span>
                            )}
                          </td>
                          <td className="py-2 px-4">
                            <a
                              href={row.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-[#ea580c] hover:underline font-medium"
                            >
                              Mở trang
                            </a>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}


            {activeTab === 'rules' && (
              <div className="space-y-6">
                <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
                  <div className="flex flex-wrap items-center gap-3 mb-4">
                    <button
                      type="button"
                      onClick={loadMappings}
                      disabled={mappingsLoading}
                      className="px-3 py-2 text-sm font-medium rounded-lg border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                    >
                      {mappingsLoading ? 'Đang tải...' : 'Tải mapping'}
                    </button>
                    <button
                      type="button"
                      onClick={handleApplyMappings}
                      disabled={processing}
                      className="px-3 py-2 text-sm font-medium rounded-lg border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                    >
                      Đồng bộ mapping cho sản phẩm cũ (chỉ nhánh có cấp 3 nguồn trong mapping; không reset toàn bộ SP)
                    </button>
                  </div>

                  <div className="overflow-x-auto border border-gray-200 rounded-lg">
                    <table className="min-w-full text-sm">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="text-left px-3 py-2">ID</th>
                          <th className="text-left px-3 py-2">Từ</th>
                          <th className="text-left px-3 py-2">Đến</th>
                          <th className="text-left px-3 py-2">Thao tác</th>
                        </tr>
                      </thead>
                      <tbody>
                        {mappings.map((r) => {
                          const destUrl = mappingDestinationDanhMucPath(tree, r);
                          return (
                          <tr key={r.id} className="border-t">
                            <td className="px-3 py-2">{r.id}</td>
                            <td className="px-3 py-2">
                              {[r.from_category, r.from_subcategory, r.from_sub_subcategory].filter(Boolean).join(' > ')}
                            </td>
                            <td className="px-3 py-2">
                              <div className="flex flex-col gap-1.5 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
                                <span className="break-words text-gray-900 flex-1 min-w-0">
                                  {[
                                    r.to_category,
                                    r.to_subcategory || (r.to_sub_subcategory ? r.from_subcategory : ''),
                                    r.to_sub_subcategory,
                                  ]
                                    .filter(Boolean)
                                    .join(' > ')}
                                </span>
                                {destUrl && (
                                  <a
                                    href={destUrl}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="shrink-0 inline-flex items-center gap-1 text-[#ea580c] hover:underline font-medium whitespace-nowrap text-xs sm:text-sm"
                                    title="Mở trang danh mục đích trên site"
                                  >
                                    Mở danh mục
                                    <span aria-hidden className="opacity-70">
                                      ↗
                                    </span>
                                  </a>
                                )}
                              </div>
                            </td>
                            <td className="px-3 py-2 space-x-2">
                              <button
                                type="button"
                                onClick={() => handleEditMapping(r)}
                                className="text-blue-600 hover:underline"
                              >
                                Sửa
                              </button>
                              <button
                                type="button"
                                onClick={() => handleDeleteMapping(r.id)}
                                className="text-red-600 hover:underline"
                              >
                                Xóa
                              </button>
                            </td>
                          </tr>
                          );
                        })}
                        {mappings.length === 0 && !mappingsLoading && (
                          <tr>
                            <td className="px-3 py-3 text-gray-500" colSpan={4}>
                              Chưa có mapping
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
                  <h3 className={`text-lg font-semibold ${mappingEditId ? 'mb-4' : 'mb-1'}`}>
                    {mappingEditId ? 'Sửa mapping' : 'Tạo mapping'}
                  </h3>
                  {!mappingEditId && (
                    <p className="text-xs text-gray-500 mb-4">
                      Nguồn: chọn cấp 2 + chỉ tick những **cấp 3** muốn map; sản phẩm thuộc cùng cấp 2 nhưng **không** tick vẫn giữ danh mục cũ. Mỗi nhánh đã tick tạo một mapping; backend cập nhật **đúng** SP khớp 3 cột nguồn sang đích. Không dùng “đồng bộ” kiểu gộp cả cấp 2.
                    </p>
                  )}
                  <div className="border border-gray-200 rounded-lg overflow-hidden">
                    <div className="grid grid-cols-2 bg-gray-50 text-sm font-medium text-gray-700">
                      <div className="px-3 py-2 border-r border-gray-200">Nguồn</div>
                      <div className="px-3 py-2">Đích</div>
                    </div>
                    <div className="grid grid-cols-2 items-start">
                      <div className="px-3 py-2 border-r border-gray-200">
                        <div className="text-xs text-gray-500 mb-1">Cấp 1</div>
                        <select
                          value={mappingForm.from_category}
                          onChange={(e) => {
                            const v = e.target.value;
                            setMappingForm({
                              ...mappingForm,
                              from_category: v,
                              from_subcategory: '',
                              from_sub_subcategory: '',
                              to_category: v,
                            });
                            setMappingSourceL2Multi([]);
                            setMappingSourceL3Multi([]);
                            setMappingSourceL2Search('');
                            setMappingSourceL3Search('');
                          }}
                          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                        >
                          <option value="">-- Chọn cấp 1 --</option>
                          {level1Categories.map((cat) => (
                            <option key={cat} value={cat}>
                              {cat}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="px-3 py-2">
                        <div className="text-xs text-gray-500 mb-1">Cấp 1</div>
                        <select
                          value={mappingForm.to_category}
                          onChange={(e) =>
                            setMappingForm({
                              ...mappingForm,
                              to_category: e.target.value,
                              to_subcategory: '',
                              to_sub_subcategory: '',
                            })
                          }
                        disabled
                          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                        >
                        <option value="">{mappingForm.to_category || '-- Chọn cấp 1 --'}</option>
                        </select>
                      </div>
                      <div className="px-3 py-2 border-r border-gray-200 border-t border-gray-200">
                        {mappingEditId ? (
                          <>
                            <div className="text-xs text-gray-500 mb-1">Cấp 2</div>
                          <select
                            value={mappingForm.from_subcategory}
                            onChange={(e) =>
                              setMappingForm({
                                ...mappingForm,
                                from_subcategory: e.target.value,
                                from_sub_subcategory: '',
                              })
                            }
                            disabled={!mappingForm.from_category}
                            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                          >
                            <option value="">-- Chọn cấp 2 --</option>
                            {getLevel2Options(mappingForm.from_category).map((sub) => (
                              <option key={sub} value={sub}>
                                {sub}
                              </option>
                            ))}
                          </select>
                          </>
                        ) : (
                          <>
                            <div className="flex flex-wrap items-center gap-2 mb-1.5">
                              <span className="text-xs text-gray-500 shrink-0">Cấp 2 (chọn nhiều)</span>
                              <input
                                type="search"
                                value={mappingSourceL2Search}
                                onChange={(e) => setMappingSourceL2Search(e.target.value)}
                                placeholder="Tìm (nhiều từ, thứ tự tuỳ ý)…"
                                disabled={!mappingForm.from_category}
                                className="flex-1 min-w-[7rem] border border-gray-200 rounded-md px-2 py-1 text-xs text-gray-800 placeholder:text-gray-400 disabled:bg-gray-50 disabled:text-gray-400"
                                aria-label="Lọc danh mục cấp 2 nguồn"
                              />
                            </div>
                            <div className="max-h-52 overflow-y-auto border border-gray-200 rounded-lg p-2 space-y-1.5 bg-white">
                              {!mappingForm.from_category ? (
                                <p className="text-xs text-gray-400">Chọn cấp 1 trước</p>
                              ) : getLevel2Options(mappingForm.from_category).length === 0 ? (
                                <p className="text-xs text-gray-400">Không có cấp 2</p>
                              ) : level2OptionsFilteredForDisplay.length === 0 ? (
                                <p className="text-xs text-gray-400">Không có danh mục khớp từ khóa</p>
                              ) : (
                                level2OptionsFilteredForDisplay.map((sub) => (
                                  <label key={sub} className="flex items-start gap-2 text-sm cursor-pointer">
                                    <input
                                      type="checkbox"
                                      className="mt-0.5 shrink-0"
                                      checked={mappingSourceL2Multi.includes(sub)}
                                      onChange={() => toggleMappingSourceL2(sub)}
                                    />
                                    <span>{sub}</span>
                                  </label>
                                ))
                              )}
                            </div>
                          </>
                        )}
                      </div>
                      <div className="px-3 py-2 border-t border-gray-200">
                        <div className="text-xs text-gray-500 mb-1">Cấp 2</div>
                        <input
                          type="text"
                          list="mapping-to-subcategory-list"
                          value={mappingForm.to_subcategory}
                          onChange={(e) =>
                            setMappingForm({
                              ...mappingForm,
                              to_subcategory: e.target.value,
                              to_sub_subcategory: '',
                            })
                          }
                          placeholder="Gõ hoặc chọn cấp 2"
                          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                        />
                        <datalist id="mapping-to-subcategory-list">
                          {(combinedLevel23ByLevel1.get(mappingForm.to_category) || []).map((sub) => (
                            <option key={sub} value={sub} />
                          ))}
                        </datalist>
                      </div>
                      <div className="px-3 py-2 border-r border-gray-200 border-t border-gray-200">
                        {mappingEditId ? (
                          <>
                            <div className="text-xs text-gray-500 mb-1">Cấp 3</div>
                            <select
                              value={mappingForm.from_sub_subcategory}
                              onChange={(e) => setMappingForm({ ...mappingForm, from_sub_subcategory: e.target.value })}
                              disabled={!mappingForm.from_category || !mappingForm.from_subcategory}
                              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                            >
                              <option value="">-- Chọn cấp 3 --</option>
                              {getLevel3Options(mappingForm.from_category, mappingForm.from_subcategory).map((sub) => (
                                <option key={sub} value={sub}>
                                  {sub}
                                </option>
                              ))}
                            </select>
                          </>
                        ) : (
                          <>
                            <div className="flex flex-wrap items-center gap-2 mb-1.5">
                              <span className="text-xs text-gray-500 shrink-0">Cấp 3 (chọn nhiều)</span>
                              <input
                                type="search"
                                value={mappingSourceL3Search}
                                onChange={(e) => setMappingSourceL3Search(e.target.value)}
                                placeholder="Tìm (nhiều từ, thứ tự tuỳ ý)…"
                                disabled={!mappingForm.from_category || mappingSourceL2Multi.length === 0}
                                className="flex-1 min-w-[7rem] border border-gray-200 rounded-md px-2 py-1 text-xs text-gray-800 placeholder:text-gray-400 disabled:bg-gray-50 disabled:text-gray-400"
                                aria-label="Lọc danh mục cấp 3 nguồn"
                              />
                            </div>
                            <div className="max-h-52 overflow-y-auto border border-gray-200 rounded-lg p-2 space-y-1.5 bg-white">
                              {!mappingForm.from_category ? (
                                <p className="text-xs text-gray-400">Chọn cấp 1 trước</p>
                              ) : mappingSourceL2Multi.length === 0 ? (
                                <p className="text-xs text-gray-400">
                                  Chọn ít nhất một danh mục cấp 2 — chỉ hiển thị cấp 3 thuộc các cấp 2 đã chọn
                                </p>
                              ) : level3PairsUnderFromCategory.length === 0 ? (
                                <p className="text-xs text-gray-400">Không có cấp 3 trong các cấp 2 đã chọn</p>
                              ) : level3PairsFilteredForDisplay.length === 0 ? (
                                <p className="text-xs text-gray-400">Không có danh mục khớp từ khóa</p>
                              ) : (
                                level3PairsFilteredForDisplay.map(({ key, label }) => (
                                  <label key={key} className="flex items-start gap-2 text-sm cursor-pointer">
                                    <input
                                      type="checkbox"
                                      className="mt-0.5 shrink-0"
                                      checked={mappingSourceL3Multi.includes(key)}
                                      onChange={() => toggleMappingSourceL3(key)}
                                    />
                                    <span className="leading-snug">{label}</span>
                                  </label>
                                ))
                              )}
                            </div>
                          </>
                        )}
                      </div>
                      <div className="px-3 py-2 border-t border-gray-200">
                        <div className="text-xs text-gray-500 mb-1">Cấp 3</div>
                        <input
                          type="text"
                          list="mapping-to-subsubcategory-list"
                          value={mappingForm.to_sub_subcategory}
                          onChange={(e) => setMappingForm({ ...mappingForm, to_sub_subcategory: e.target.value })}
                          placeholder="Gõ hoặc chọn cấp 3"
                          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                        />
                        <datalist id="mapping-to-subsubcategory-list">
                          {(combinedLevel23ByLevel1.get(mappingForm.to_category) || []).map((sub) => (
                            <option key={sub} value={sub} />
                          ))}
                        </datalist>
                      </div>
                    </div>
                  </div>
                  <div className="mt-4 flex gap-2">
                    <button
                      type="button"
                      onClick={handleCreateOrUpdateMapping}
                      disabled={processing}
                      className="px-4 py-2 rounded-lg bg-[#ea580c] text-white font-medium disabled:opacity-50"
                    >
                      {processing ? 'Đang xử lý...' : mappingEditId ? 'Cập nhật mapping' : 'Tạo mapping'}
                    </button>
                    {mappingEditId && (
                      <button
                        type="button"
                        onClick={() => {
                          setMappingEditId(null);
                          setMappingSourceL2Multi([]);
                          setMappingSourceL3Multi([]);
                          setMappingSourceL2Search('');
                          setMappingSourceL3Search('');
                          setMappingForm({
                            from_category: '',
                            from_subcategory: '',
                            from_sub_subcategory: '',
                            to_category: '',
                            to_subcategory: '',
                            to_sub_subcategory: '',
                          });
                        }}
                        className="px-4 py-2 rounded-lg border border-gray-300"
                      >
                        Hủy sửa
                      </button>
                    )}
                  </div>
                </div>

                <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
                  <h3 className="text-lg font-semibold mb-4">Export/Import mapping</h3>
                  <div className="flex flex-wrap items-center gap-3 mb-3">
                    <button
                      type="button"
                      onClick={handleExportMappings}
                      className="px-3 py-2 text-sm font-medium rounded-lg border border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
                    >
                      Export
                    </button>
                    <label className="flex items-center gap-2 text-sm text-gray-600">
                      <input
                        type="checkbox"
                        checked={mappingReplace}
                        onChange={(e) => setMappingReplace(e.target.checked)}
                      />
                      Replace
                    </label>
                    <button
                      type="button"
                      onClick={handleImportMappings}
                      className="px-3 py-2 text-sm font-medium rounded-lg border border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
                    >
                      Import
                    </button>
                  </div>
                  <textarea
                    value={mappingJson}
                    onChange={(e) => setMappingJson(e.target.value)}
                    rows={8}
                    className="w-full border border-gray-300 rounded-lg p-3 text-xs font-mono"
                    placeholder='{"mappings":[...]}'
                  />
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </AdminLayout>
  );
}
