'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import AdminLayout from '@/components/admin/AdminLayout';
import { apiClient } from '@/lib/api-client';
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
  const [seoBodyForce, setSeoBodyForce] = useState(false);
  const [seoBodyMessage, setSeoBodyMessage] = useState<string | null>(null);
  const [seoBodyMode, setSeoBodyMode] = useState<'all' | 'selected'>('all');
  const [seoBodyPaths, setSeoBodyPaths] = useState<string[]>([]);
  const [seoBodySelected, setSeoBodySelected] = useState<string[]>([]);
  const [seoBodyLoading, setSeoBodyLoading] = useState(false);
  const [seoBodySearch, setSeoBodySearch] = useState('');
  const [seoBodyLevelFilter, setSeoBodyLevelFilter] = useState<'all' | '1' | '2' | '3'>('all');
  const [seoBodyStatus, setSeoBodyStatus] = useState<any | null>(null);
  const seoBodyPollRef = useRef<number | null>(null);

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
    if (seoBodyMode === 'selected' && seoBodyPaths.length === 0 && !seoBodyLoading) {
      loadSeoBodyPaths();
    }
  }, [seoBodyMode, seoBodyPaths.length, seoBodyLoading]);

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


  const loadSeoBodyPaths = async () => {
    setSeoBodyLoading(true);
    setSeoBodyMessage(null);
    try {
      const result = await apiClient.generateSeoBodies({ dry_run: true });
      setSeoBodyPaths(Array.isArray(result?.paths) ? result.paths : []);
    } catch (err: any) {
      setSeoBodyMessage(err.message || 'Không tải được danh sách danh mục');
    } finally {
      setSeoBodyLoading(false);
    }
  };

  const loadSeoBodyStatus = async () => {
    try {
      const status = await apiClient.getSeoBodiesStatus();
      setSeoBodyStatus(status);
      if (!status?.running && seoBodyPollRef.current) {
        window.clearInterval(seoBodyPollRef.current);
        seoBodyPollRef.current = null;
        setSeoBodyMessage('Đã hoàn tất. Xem kết quả bên dưới.');
      }
    } catch {
      // ignore
    }
  };

  const startSeoBodyPolling = () => {
    if (seoBodyPollRef.current) {
      window.clearInterval(seoBodyPollRef.current);
    }
    seoBodyPollRef.current = window.setInterval(loadSeoBodyStatus, 2000);
    loadSeoBodyStatus();
  };

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

  const handleGenerateSeoBodies = async () => {
    if (seoBodyMode === 'selected' && seoBodySelected.length === 0) {
      alert('Vui lòng chọn ít nhất 1 danh mục');
      return;
    }
    if (!confirm('Tạo lại SEO body? Thao tác này có thể mất thời gian.')) return;
    setProcessing(true);
    setSeoBodyMessage(null);
    try {
      if (seoBodyMode === 'all') {
        const result = await apiClient.generateSeoBodies({ force: seoBodyForce });
        setSeoBodyMessage(result?.message || 'Đã bắt đầu tạo lại SEO body');
        startSeoBodyPolling();
      } else {
        let done = 0;
        for (const path of seoBodySelected) {
          await apiClient.generateSeoBodies({ force: seoBodyForce, path });
          done += 1;
        }
        setSeoBodyMessage(`Đã bắt đầu tạo lại ${done} danh mục đã chọn`);
        startSeoBodyPolling();
      }
    } catch (err: any) {
      setSeoBodyMessage(err.message || 'Có lỗi xảy ra');
    } finally {
      setProcessing(false);
    }
  };

  const toggleSeoBodySelected = (path: string) => {
    setSeoBodySelected((prev) => (prev.includes(path) ? prev.filter((p) => p !== path) : [...prev, path]));
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

  const filteredSeoBodyPaths = useMemo(() => {
    if (!seoBodySearch.trim()) return seoBodyPaths;
    const q = seoBodySearch.trim().toLowerCase();
    return seoBodyPaths.filter((p) => p.toLowerCase().includes(q));
  }, [seoBodyPaths, seoBodySearch]);

  const levelFilteredSeoBodyPaths = useMemo(() => {
    if (seoBodyLevelFilter === 'all') return filteredSeoBodyPaths;
    return filteredSeoBodyPaths.filter((p) => p.split('/').filter(Boolean).length === Number(seoBodyLevelFilter));
  }, [filteredSeoBodyPaths, seoBodyLevelFilter]);


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

  return (
    <AdminLayout>
      <div className="p-6 max-w-7xl">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Quản lý danh mục SEO</h1>
        <p className="text-gray-600 text-sm mb-4">
          Quản lý danh mục cấp 1, 2, 3 và mapping SEO.
        </p>

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
              Danh sách danh mục
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
                <div className="mb-4 space-y-3">
                  <p className="text-xs text-gray-500">
                    Nội dung SEO cuối trang (Gemini) <strong>chỉ</strong> chạy khi bạn bấm «Chạy tất cả» hoặc «Chạy danh mục đã chọn»
                    bên dưới — không tự động khi khách mở trang danh mục hay sau import Excel.
                  </p>
                  <div className="flex flex-wrap items-center gap-3">
                    <button
                      type="button"
                      onClick={() => setSeoBodyMode('all')}
                      className={`px-3 py-2 text-sm font-medium rounded-lg border ${
                        seoBodyMode === 'all'
                          ? 'border-[#ea580c] text-[#ea580c] bg-orange-50'
                          : 'border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
                      }`}
                    >
                      Chọn tất cả danh mục
                    </button>
                    <button
                      type="button"
                      onClick={async () => {
                        setSeoBodyMode('selected');
                      }}
                      className={`px-3 py-2 text-sm font-medium rounded-lg border ${
                        seoBodyMode === 'selected'
                          ? 'border-[#ea580c] text-[#ea580c] bg-orange-50'
                          : 'border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
                      }`}
                    >
                      Chọn từng danh mục
                    </button>
                    <button
                      type="button"
                      onClick={handleGenerateSeoBodies}
                      disabled={processing}
                      className="px-3 py-2 text-sm font-medium rounded-lg border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                    >
                      {processing ? 'Đang chạy...' : seoBodyMode === 'all' ? 'Chạy tất cả' : 'Chạy danh mục đã chọn'}
                    </button>
                    <label className="flex items-center gap-2 text-sm text-gray-600">
                      <input
                        type="checkbox"
                        checked={seoBodyForce}
                        onChange={(e) => setSeoBodyForce(e.target.checked)}
                      />
                      Ghi đè (force)
                    </label>
                    {seoBodyMessage && <span className="text-sm text-emerald-700">{seoBodyMessage}</span>}
                  </div>

                  {seoBodyMode === 'selected' && (
                    <div className="border border-gray-200 rounded-lg p-3 bg-white">
                      <div className="flex items-center gap-3 mb-2">
                        <input
                          type="text"
                          value={seoBodySearch}
                          onChange={(e) => setSeoBodySearch(e.target.value)}
                          placeholder="Tìm danh mục..."
                          className="border border-gray-300 rounded-lg px-3 py-2 text-sm w-64"
                        />
                        <select
                          value={seoBodyLevelFilter}
                          onChange={(e) => setSeoBodyLevelFilter(e.target.value as 'all' | '1' | '2' | '3')}
                          className="border border-gray-300 rounded-lg px-3 py-2 text-sm"
                        >
                          <option value="all">Tất cả cấp</option>
                          <option value="1">Cấp 1</option>
                          <option value="2">Cấp 2</option>
                          <option value="3">Cấp 3</option>
                        </select>
                        <button
                          type="button"
                          onClick={() => {
                            const all = levelFilteredSeoBodyPaths;
                            setSeoBodySelected((prev) =>
                              all.every((p) => prev.includes(p)) ? prev.filter((p) => !all.includes(p)) : Array.from(new Set([...prev, ...all]))
                            );
                          }}
                          className="px-2 py-1 text-xs font-medium rounded border border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
                        >
                          {levelFilteredSeoBodyPaths.every((p) => seoBodySelected.includes(p)) ? 'Bỏ chọn' : 'Chọn tất cả'}
                        </button>
                        {seoBodyLoading && <span className="text-xs text-gray-500">Đang tải...</span>}
                        <span className="text-xs text-gray-500">
                          Đã chọn: {seoBodySelected.length} / {seoBodyPaths.length}
                        </span>
                      </div>
                      {seoBodyPaths.length === 0 ? (
                        <p className="text-sm text-gray-500">Chưa có danh mục.</p>
                      ) : (
                        <div className="max-h-48 overflow-y-auto space-y-1 text-sm">
                          {levelFilteredSeoBodyPaths.map((path) => (
                            <label key={path} className="flex items-center gap-2 px-2 py-1 hover:bg-gray-50 rounded">
                              <input
                                type="checkbox"
                                checked={seoBodySelected.includes(path)}
                                onChange={() => toggleSeoBodySelected(path)}
                              />
                              <span className="font-mono text-xs">{path}</span>
                            </label>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {seoBodyStatus && (
                    <div className="border border-gray-200 rounded-lg p-3 bg-white text-sm">
                      <div className="flex flex-wrap items-center gap-3">
                        <span className="text-gray-700">
                          Trạng thái: {seoBodyStatus.running ? 'Đang chạy' : 'Đã hoàn tất'}
                        </span>
                        <span className="text-gray-600">
                          Tiến độ: {seoBodyStatus.done}/{seoBodyStatus.total || 0}
                        </span>
                        <span className="text-gray-600">Bỏ qua: {seoBodyStatus.skipped || 0}</span>
                        <span className="text-gray-600">Lỗi: {seoBodyStatus.failed || 0}</span>
                      </div>
                      {seoBodyStatus.current_path && (
                        <div className="mt-2 text-xs text-gray-500">
                          Đang chạy: <span className="font-mono">{seoBodyStatus.current_path}</span>
                        </div>
                      )}
                      {(seoBodyStatus.report || []).length > 0 && (
                        <div className="mt-3 max-h-40 overflow-y-auto text-xs">
                          {(seoBodyStatus.report || []).slice(-20).map((item: any, idx: number) => (
                            <div key={`${item.path}-${idx}`} className="flex flex-wrap items-center gap-2">
                              <span className="font-mono text-gray-700">{item.path}</span>
                              <span className="text-gray-500">({item.status})</span>
                              {item.message && <span className="text-gray-400">- {item.message}</span>}
                              {typeof item.seo_body_len === 'number' && (
                                <span className="text-gray-400">len={item.seo_body_len}</span>
                              )}
                              {typeof item.has_links !== 'undefined' && (
                                <span className="text-gray-400">has_links={String(item.has_links)}</span>
                              )}
                              {typeof item.sibling_count === 'number' && (
                                <span className="text-gray-400">siblings={item.sibling_count}</span>
                              )}
                              {typeof item.sibling_mentions === 'number' && (
                                <span className="text-gray-400">mentions={item.sibling_mentions}</span>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
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
                    onClick={() => loadData()}
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
