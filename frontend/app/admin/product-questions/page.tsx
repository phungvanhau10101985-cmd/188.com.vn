'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import {
  adminProductQuestionsAPI,
  type ProductQuestionAdmin,
  type ProductQuestionsListResponse,
} from '@/lib/admin-api';

const PAGE_SIZE = 10;
const COL_WIDTHS_STORAGE_KEY = 'admin_product_questions_column_widths';

const COLUMN_KEYS = [
  'stt', 'user_name', 'content', 'created_at', 'group', 'product_id', 'updated_at', 'is_active',
  'useful',
  'reply_admin_name', 'reply_admin_content', 'reply_admin_at', 'reply_user_one_id', 'reply_user_one_name',
  'reply_user_one_content', 'reply_user_one_at', 'reply_user_two_id', 'reply_user_two_name',
  'reply_user_two_content', 'reply_user_two_at', 'reply_count', 'actions',
] as const;

const DEFAULT_COLUMN_WIDTHS: Record<string, number> = {
  stt: 44, user_name: 110, content: 140, created_at: 115, group: 52, product_id: 56, updated_at: 115,
  is_active: 88, useful: 88, reply_admin_name: 120, reply_admin_content: 150, reply_admin_at: 115,
  reply_user_one_id: 72, reply_user_one_name: 90, reply_user_one_content: 110, reply_user_one_at: 115,
  reply_user_two_id: 72, reply_user_two_name: 90, reply_user_two_content: 110, reply_user_two_at: 115,
  reply_count: 78, actions: 100,
};

function loadColumnWidths(): Record<string, number> {
  if (typeof window === 'undefined') return { ...DEFAULT_COLUMN_WIDTHS };
  try {
    const s = localStorage.getItem(COL_WIDTHS_STORAGE_KEY);
    if (!s) return { ...DEFAULT_COLUMN_WIDTHS };
    const parsed = JSON.parse(s) as Record<string, number>;
    return { ...DEFAULT_COLUMN_WIDTHS, ...parsed };
  } catch {
    return { ...DEFAULT_COLUMN_WIDTHS };
  }
}

function saveColumnWidths(widths: Record<string, number>) {
  try {
    localStorage.setItem(COL_WIDTHS_STORAGE_KEY, JSON.stringify(widths));
  } catch {
    // ignore
  }
}

function formatDate(s: string | null | undefined) {
  if (!s) return '—';
  try {
    const d = new Date(s);
    return d.toLocaleString('vi-VN');
  } catch {
    return s;
  }
}

type RowEdit = Partial<Pick<ProductQuestionAdmin,
  'group' | 'reply_admin_name' | 'reply_admin_content' | 'is_active' | 'useful' |
  'reply_user_one_name' | 'reply_user_one_content' | 'reply_user_two_name' | 'reply_user_two_content'
>>;

export default function AdminProductQuestionsPage() {
  const [data, setData] = useState<ProductQuestionsListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchGroup, setSearchGroup] = useState('');
  const [page, setPage] = useState(1);
  const [toast, setToast] = useState<{ type: 'ok' | 'err'; msg: string } | null>(null);
  const [importing, setImporting] = useState(false);
  const [rowEdit, setRowEdit] = useState<Record<number, RowEdit>>({});
  const [savingId, setSavingId] = useState<number | null>(null);
  const [columnWidths, setColumnWidths] = useState<Record<string, number>>(loadColumnWidths);
  const resizeRef = useRef<{ key: string; startX: number; startW: number } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const startResize = useCallback((key: string) => (e: React.MouseEvent) => {
    e.preventDefault();
    const startW = columnWidths[key] ?? DEFAULT_COLUMN_WIDTHS[key] ?? 100;
    resizeRef.current = { key, startX: e.clientX, startW };
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    const onMove = (ev: MouseEvent) => {
      if (!resizeRef.current) return;
      const delta = ev.clientX - resizeRef.current.startX;
      const newW = Math.max(40, resizeRef.current.startW + delta);
      setColumnWidths((prev) => {
        const next = { ...prev, [resizeRef.current!.key]: newW };
        saveColumnWidths(next);
        return next;
      });
    };
    const onUp = () => {
      resizeRef.current = null;
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }, [columnWidths]);

  const getColWidth = useCallback((key: string) => columnWidths[key] ?? DEFAULT_COLUMN_WIDTHS[key] ?? 100, [columnWidths]);

  const resetColumnWidths = useCallback(() => {
    setColumnWidths({ ...DEFAULT_COLUMN_WIDTHS });
    saveColumnWidths(DEFAULT_COLUMN_WIDTHS);
    showToast('ok', 'Đã đặt lại độ rộng cột');
  }, []);

  const showToast = (type: 'ok' | 'err', msg: string) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 3000);
  };

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const res = await adminProductQuestionsAPI.getList({
        skip: (page - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
        search_group: searchGroup.trim() || undefined,
        sort_by: 'id',
        sort_desc: true,
      });
      setData(res);
    } catch {
      showToast('err', 'Lỗi tải danh sách');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [page, searchGroup]);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    fetchList();
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    try {
      const result = await adminProductQuestionsAPI.importExcel(file);
      const created = (result as { created?: number })?.created ?? 0;
      showToast('ok', `Import xong: ${created} câu hỏi`);
      fetchList();
    } catch (err: unknown) {
      showToast('err', (err as Error)?.message || 'Import thất bại');
    } finally {
      setImporting(false);
      e.target.value = '';
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Bạn có chắc muốn xóa câu hỏi này?')) return;
    try {
      await adminProductQuestionsAPI.delete(id);
      showToast('ok', 'Đã xóa');
      fetchList();
    } catch {
      showToast('err', 'Xóa thất bại');
    }
  };

  const getRowVal = useCallback((q: ProductQuestionAdmin, key: keyof RowEdit) => {
    if (rowEdit[q.id] && key in rowEdit[q.id]) return (rowEdit[q.id] as Record<string, unknown>)[key];
    return (q as unknown as Record<string, unknown>)[key];
  }, [rowEdit]);

  const setRowVal = useCallback((id: number, key: keyof RowEdit, value: string | boolean | number) => {
    setRowEdit((prev) => ({ ...prev, [id]: { ...prev[id], [key]: value } }));
  }, []);

  const handleSaveRow = async (q: ProductQuestionAdmin) => {
    const e = rowEdit[q.id];
    const reply_admin_name = (e?.reply_admin_name !== undefined ? e.reply_admin_name : q.reply_admin_name) ?? '';
    const reply_admin_content = (e?.reply_admin_content !== undefined ? e.reply_admin_content : q.reply_admin_content) ?? '';
    const is_active = e?.is_active !== undefined ? e.is_active! : q.is_active;
    const groupRaw = e?.group !== undefined ? e.group : q.group;
    const group = Math.max(0, typeof groupRaw === 'number' ? groupRaw : (parseInt(String(groupRaw), 10) || 0));
    const usefulRaw = e?.useful !== undefined ? e.useful : q.useful;
    const useful = Math.max(0, typeof usefulRaw === 'number' ? usefulRaw : (parseInt(String(usefulRaw), 10) || 0));
    const reply_user_one_name = (e?.reply_user_one_name !== undefined ? e.reply_user_one_name : q.reply_user_one_name) ?? '';
    const reply_user_one_content = (e?.reply_user_one_content !== undefined ? e.reply_user_one_content : q.reply_user_one_content) ?? '';
    const reply_user_two_name = (e?.reply_user_two_name !== undefined ? e.reply_user_two_name : q.reply_user_two_name) ?? '';
    const reply_user_two_content = (e?.reply_user_two_content !== undefined ? e.reply_user_two_content : q.reply_user_two_content) ?? '';
    setSavingId(q.id);
    try {
      await adminProductQuestionsAPI.update(q.id, {
        group, reply_admin_name, reply_admin_content, is_active, useful,
        reply_user_one_name, reply_user_one_content, reply_user_two_name, reply_user_two_content,
      });
      setRowEdit((prev) => {
        const next = { ...prev };
        delete next[q.id];
        return next;
      });
      showToast('ok', 'Đã lưu');
      fetchList();
    } catch {
      showToast('err', 'Lưu thất bại');
    } finally {
      setSavingId(null);
    }
  };

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
      <div className="p-6">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">
          Tất cả Câu hỏi Câu trả lời sản phẩm
        </h1>

        {toast && (
          <div
            className={`fixed top-4 right-4 z-50 px-4 py-2 rounded-lg ${
              toast.type === 'ok' ? 'bg-green-600 text-white' : 'bg-red-600 text-white'
            }`}
          >
            {toast.msg}
          </div>
        )}

        <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
          <a href="/" className="text-blue-600 hover:underline">Trang chủ</a>
          <span className="text-gray-400">|</span>
          <a href="/" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">
            Xem website
          </a>
          <span className="text-gray-400">|</span>
          <span className="text-gray-600">Thêm mới (form tạo trong bảng)</span>
          <span className="text-gray-400">|</span>
          <button
            type="button"
            onClick={() => adminProductQuestionsAPI.downloadSampleExcel().catch((e) => showToast('err', (e as Error)?.message || 'Lỗi tải file'))}
            className="text-blue-600 hover:underline"
          >
            Tải file Excel mẫu
          </button>
          <span className="text-gray-400">|</span>
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={importing}
            className="text-blue-600 hover:underline disabled:opacity-70"
          >
            {importing ? 'Đang import...' : 'Import'}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,.xls"
            className="hidden"
            onChange={handleImport}
          />
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-4 mb-6">
          <form onSubmit={handleSearch} className="flex flex-wrap items-end gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Tìm kiếm theo Nhóm câu hỏi
              </label>
              <input
                type="text"
                value={searchGroup}
                onChange={(e) => setSearchGroup(e.target.value)}
                placeholder="Nhập số nhóm..."
                className="w-48 rounded-lg border border-gray-300 px-3 py-2 text-sm"
              />
            </div>
            <button
              type="submit"
              className="px-4 py-2 bg-slate-700 text-white rounded-lg hover:bg-slate-800 text-sm font-medium"
            >
              Tìm kiếm
            </button>
          </form>
        </div>

        <div className="mb-2 flex items-center justify-between flex-wrap gap-2">
          <span className="text-sm text-gray-600">
            Tổng số bản ghi: {data?.total ?? 0}
          </span>
          <div className="flex items-center gap-2 text-sm">
            <button
              type="button"
              onClick={resetColumnWidths}
              className="px-2 py-1 rounded border border-gray-300 hover:bg-gray-100 text-gray-700"
              title="Đặt lại độ rộng tất cả cột về mặc định"
            >
              Đặt lại độ rộng cột
            </button>
            <span className="text-gray-600">Hiển thị</span>
            <select
              value={PAGE_SIZE}
              className="rounded border border-gray-300 px-2 py-1"
              disabled
            >
              <option value={10}>10</option>
            </select>
          </div>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          {loading ? (
            <div className="p-12 text-center text-gray-500">Đang tải...</div>
          ) : !data?.items?.length ? (
            <div className="p-12 text-center text-gray-500">
              Chưa có câu hỏi nào. Dùng Import để tải file Excel.
            </div>
          ) : (
            <div className="overflow-x-auto -mx-2">
              <table className="w-full text-sm table-fixed" style={{ tableLayout: 'fixed' }}>
                <colgroup>
                  {COLUMN_KEYS.map((key) => (
                    <col key={key} style={{ width: getColWidth(key), minWidth: getColWidth(key) }} />
                  ))}
                </colgroup>
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200">
                    {[
                      ['stt', 'STT'],
                      ['user_name', 'Tên người hỏi'],
                      ['content', 'Nội dung hỏi'],
                      ['created_at', 'Thời gian hỏi'],
                      ['group', 'Nhóm'],
                      ['product_id', 'ID SP'],
                      ['updated_at', 'Thời gian\nupdate'],
                      ['is_active', 'Kích hoạt'],
                      ['useful', 'Lượt thấy\nhữu ích'],
                      ['reply_admin_name', 'Tên Admin\ntrả lời'],
                      ['reply_admin_content', 'Nội dung admin\ntrả lời'],
                      ['reply_admin_at', 'Thời gian\nadmin TL'],
                      ['reply_user_one_id', 'ID user 1'],
                      ['reply_user_one_name', 'Tên user 1'],
                      ['reply_user_one_content', 'Nội dung\nuser 1'],
                      ['reply_user_one_at', 'Thời gian\nuser 1'],
                      ['reply_user_two_id', 'ID user 2'],
                      ['reply_user_two_name', 'Tên user 2'],
                      ['reply_user_two_content', 'Nội dung\nuser 2'],
                      ['reply_user_two_at', 'Thời gian\nuser 2'],
                      ['reply_count', 'Số TL'],
                      ['actions', 'Chức năng'],
                    ].map(([key, label]) => (
                      <th
                        key={key}
                        className="text-left py-2 px-2 font-semibold text-gray-700 relative group align-bottom"
                        style={{ width: getColWidth(key), minWidth: getColWidth(key), maxWidth: getColWidth(key) }}
                      >
                        <span className="block break-words leading-tight" style={{ lineHeight: 1.25 }}>
                          {String(label).split('\n').map((line, i) => (
                            <span key={i} className="block">{line}</span>
                          ))}
                        </span>
                        <span
                          role="separator"
                          aria-label={`Kéo để đổi độ rộng cột ${String(label).replace(/\n/g, ' ')}`}
                          onMouseDown={startResize(key)}
                          className="absolute top-0 right-0 w-1.5 h-full cursor-col-resize hover:bg-blue-400 active:bg-blue-500 bg-transparent group-hover:bg-gray-300 transition-colors"
                          title="Kéo để thay đổi độ rộng cột"
                        />
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((q, idx) => (
                    <tr key={q.id} className="border-b border-gray-100 hover:bg-gray-50/50 align-top">
                      <td className="py-2 px-2 overflow-hidden">{ (page - 1) * PAGE_SIZE + idx + 1 }</td>
                      <td className="py-2 px-2 overflow-hidden">{ q.user_name || '—' }</td>
                      <td className="py-2 px-2 break-words overflow-hidden">{ q.content || '—' }</td>
                      <td className="py-2 px-2 text-gray-600 whitespace-nowrap overflow-hidden">{ formatDate(q.created_at) }</td>
                      <td className="py-2 px-2 overflow-hidden">
                        <input
                          type="number"
                          min={0}
                          value={Math.max(0, Number(getRowVal(q, 'group') ?? q.group ?? 0) || 0)}
                          onChange={(e) => setRowVal(q.id, 'group', Math.max(0, parseInt(e.target.value, 10) || 0))}
                          onBlur={() => handleSaveRow(q)}
                          className="rounded border border-gray-300 px-1 py-0.5 text-xs w-full max-w-[48px]"
                        />
                      </td>
                      <td className="py-2 px-2 overflow-hidden">{ q.product_id ?? '—' }</td>
                      <td className="py-2 px-2 text-gray-600 whitespace-nowrap overflow-hidden">{ formatDate(q.updated_at) }</td>
                      <td className="py-2 px-2 overflow-hidden">
                        <select
                          value={getRowVal(q, 'is_active') ? '1' : '0'}
                          onChange={(e) => setRowVal(q.id, 'is_active', e.target.value === '1')}
                          onBlur={() => handleSaveRow(q)}
                          className="rounded border border-gray-300 px-1 py-0.5 text-xs w-full max-w-[90px]"
                        >
                          <option value="1">Hiển thị</option>
                          <option value="0">Ẩn</option>
                        </select>
                      </td>
                      <td className="py-2 px-2 overflow-hidden">
                        <input
                          type="number"
                          min={0}
                          value={Math.max(0, Number(getRowVal(q, 'useful') ?? q.useful ?? 0) || 0)}
                          onChange={(e) => setRowVal(q.id, 'useful', Math.max(0, parseInt(e.target.value, 10) || 0))}
                          onBlur={() => handleSaveRow(q)}
                          className="rounded border border-gray-300 px-1 py-0.5 text-xs w-full max-w-[72px]"
                          title="Số hiển thị bên cửa hàng (không khớp tự động với số tài khoản đã bấm hữu ích)"
                          aria-label="Lượt thấy hữu ích"
                        />
                      </td>
                      <td className="py-2 px-2 overflow-hidden">
                        <input
                          type="text"
                          value={String(getRowVal(q, 'reply_admin_name') ?? '')}
                          onChange={(e) => setRowVal(q.id, 'reply_admin_name', e.target.value)}
                          onBlur={() => handleSaveRow(q)}
                          className="rounded border border-gray-300 px-2 py-1 text-xs w-full min-w-0 max-w-full"
                          placeholder="Tên admin"
                        />
                      </td>
                      <td className="py-2 px-2 overflow-hidden">
                        <input
                          type="text"
                          value={String(getRowVal(q, 'reply_admin_content') ?? '')}
                          onChange={(e) => setRowVal(q.id, 'reply_admin_content', e.target.value)}
                          onBlur={() => handleSaveRow(q)}
                          className="rounded border border-gray-300 px-2 py-1 text-xs w-full min-w-0"
                          placeholder="Nội dung trả lời"
                        />
                      </td>
                      <td className="py-2 px-2 text-gray-600 whitespace-nowrap overflow-hidden">{ formatDate(q.reply_admin_at) }</td>
                      <td className="py-2 px-2 overflow-hidden">{ q.reply_user_one_id ?? '—' }</td>
                      <td className="py-2 px-2 overflow-hidden">
                        <input
                          type="text"
                          value={String(getRowVal(q, 'reply_user_one_name') ?? '')}
                          onChange={(e) => setRowVal(q.id, 'reply_user_one_name', e.target.value)}
                          onBlur={() => handleSaveRow(q)}
                          className="rounded border border-gray-300 px-2 py-1 text-xs w-full min-w-0"
                          placeholder="Tên user 1"
                        />
                      </td>
                      <td className="py-2 px-2 overflow-hidden">
                        <input
                          type="text"
                          value={String(getRowVal(q, 'reply_user_one_content') ?? '')}
                          onChange={(e) => setRowVal(q.id, 'reply_user_one_content', e.target.value)}
                          onBlur={() => handleSaveRow(q)}
                          className="rounded border border-gray-300 px-2 py-1 text-xs w-full min-w-0"
                          placeholder="Nội dung user 1"
                        />
                      </td>
                      <td className="py-2 px-2 text-gray-600 whitespace-nowrap overflow-hidden">{ formatDate(q.reply_user_one_at) }</td>
                      <td className="py-2 px-2 overflow-hidden">{ q.reply_user_two_id ?? '—' }</td>
                      <td className="py-2 px-2 overflow-hidden">
                        <input
                          type="text"
                          value={String(getRowVal(q, 'reply_user_two_name') ?? '')}
                          onChange={(e) => setRowVal(q.id, 'reply_user_two_name', e.target.value)}
                          onBlur={() => handleSaveRow(q)}
                          className="rounded border border-gray-300 px-2 py-1 text-xs w-full min-w-0"
                          placeholder="Tên user 2"
                        />
                      </td>
                      <td className="py-2 px-2 overflow-hidden">
                        <input
                          type="text"
                          value={String(getRowVal(q, 'reply_user_two_content') ?? '')}
                          onChange={(e) => setRowVal(q.id, 'reply_user_two_content', e.target.value)}
                          onBlur={() => handleSaveRow(q)}
                          className="rounded border border-gray-300 px-2 py-1 text-xs w-full min-w-0"
                          placeholder="Nội dung user 2"
                        />
                      </td>
                      <td className="py-2 px-2 text-gray-600 whitespace-nowrap overflow-hidden">{ formatDate(q.reply_user_two_at) }</td>
                      <td className="py-2 px-2 overflow-hidden">{ q.reply_count } (2=khóa)</td>
                      <td className="py-2 px-2 whitespace-nowrap overflow-hidden">
                        {!q.is_imported && (q.product_slug || q.product_id) && (
                          <a
                            href={q.product_slug ? `/products/${q.product_slug}#question-${q.id}` : `/products?product_id=${q.product_id}#question-${q.id}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-600 hover:underline text-xs mr-1"
                          >
                            Xem câu hỏi
                          </a>
                        )}
                        <button
                          type="button"
                          onClick={() => handleSaveRow(q)}
                          disabled={savingId === q.id}
                          className="text-blue-600 hover:underline text-xs mr-1 disabled:opacity-50"
                        >
                          { savingId === q.id ? 'Đang lưu...' : 'Lưu' }
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDelete(q.id)}
                          className="text-red-600 hover:underline text-xs"
                        >
                          Xóa
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {data && data.total > PAGE_SIZE && (
            <div className="p-3 border-t border-gray-100 flex items-center justify-between">
              <span className="text-sm text-gray-600">Tổng số bản ghi: {data.total}</span>
              <div className="flex gap-1">
                <button
                  type="button"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="px-3 py-1 rounded border border-gray-300 text-sm disabled:opacity-50"
                >
                  «
                </button>
                <span className="px-3 py-1 text-sm">
                  {page} / {totalPages}
                </span>
                <button
                  type="button"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  className="px-3 py-1 rounded border border-gray-300 text-sm disabled:opacity-50"
                >
                  »
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
  );
}
