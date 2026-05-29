'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  adminEmailManagementAPI,
  adminNewsletterAPI,
  type AdminEmailSendManagement,
  type AdminNewsletterImportResponse,
  type AdminNewsletterListResponse,
  type AdminNewsletterSubscriber,
} from '@/lib/admin-api';

const PAGE_SIZE = 50;
type AdminTab = 'manage' | 'list';

function formatDate(value?: string | null) {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString('vi-VN');
}

function formatImportResult(r: {
  created: number;
  reactivated: number;
  skipped_active: number;
  updated_profile?: number;
  invalid: number;
  corrected?: number;
  duplicate_in_file?: number;
  parsed: number;
  corrections?: Array<{ row: number; original: string; fixed: string; fixes: string[] }>;
  invalid_rows?: Array<{ row: number; email: string; reason: string }>;
}) {
  const parts = [
    `Hợp lệ ${r.parsed}: thêm mới ${r.created}, kích hoạt lại ${r.reactivated}, đã có ${r.skipped_active}`,
  ];
  if (r.updated_profile) parts.push(`cập nhật hồ sơ ${r.updated_profile}`);
  if (r.corrected) parts.push(`sửa email gõ nhầm ${r.corrected}`);
  if (r.invalid) parts.push(`không hợp lệ ${r.invalid}`);
  if (r.duplicate_in_file) parts.push(`trùng trong file ${r.duplicate_in_file}`);
  return parts.join(' · ') + '.';
}

export default function AdminNewsletterPage() {
  const [tab, setTab] = useState<AdminTab>('manage');
  const [data, setData] = useState<AdminNewsletterListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [q, setQ] = useState('');
  const [activeFilter, setActiveFilter] = useState<'all' | 'active' | 'inactive'>('all');
  const [page, setPage] = useState(1);
  const [banner, setBanner] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);
  const [campaignStatus, setCampaignStatus] = useState<string | null>(null);

  const [emailMgmt, setEmailMgmt] = useState<AdminEmailSendManagement | null>(null);
  const [emailMgmtLoading, setEmailMgmtLoading] = useState(true);
  const [savingWarmup, setSavingWarmup] = useState(false);
  const [runningBirthday, setRunningBirthday] = useState(false);
  const [warmupEnabled, setWarmupEnabled] = useState(true);
  const [startLimit, setStartLimit] = useState(5);
  const [dailyIncrement, setDailyIncrement] = useState(5);
  const [maxLimit, setMaxLimit] = useState('');
  const [birthdayCronEnabled, setBirthdayCronEnabled] = useState(true);

  const [importText, setImportText] = useState('');
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);

  const [campaignSubject, setCampaignSubject] = useState('');
  const [campaignMessage, setCampaignMessage] = useState('');
  const [testEmail, setTestEmail] = useState('');
  const [sendingTest, setSendingTest] = useState(false);
  const [sendingBroadcast, setSendingBroadcast] = useState(false);
  const [confirmBroadcast, setConfirmBroadcast] = useState(false);
  const [importDetails, setImportDetails] = useState<{
    corrections?: AdminNewsletterImportResponse['corrections'];
    invalid_rows?: AdminNewsletterImportResponse['invalid_rows'];
  } | null>(null);

  const activeOnlyParam =
    activeFilter === 'active' ? true : activeFilter === 'inactive' ? false : null;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await adminNewsletterAPI.list({
        skip: (page - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
        q: q.trim() || undefined,
        active_only: activeOnlyParam,
      });
      setData(res);
    } catch (err) {
      setData(null);
      setBanner({
        type: 'err',
        text: err instanceof Error ? err.message : 'Không tải được danh sách.',
      });
    } finally {
      setLoading(false);
    }
  }, [page, q, activeOnlyParam]);

  useEffect(() => {
    void load();
  }, [load]);

  const loadEmailMgmt = useCallback(async () => {
    setEmailMgmtLoading(true);
    try {
      const res = await adminEmailManagementAPI.getOverview();
      setEmailMgmt(res);
      setWarmupEnabled(res.warmup_enabled);
      setStartLimit(res.start_limit);
      setDailyIncrement(res.daily_increment);
      setMaxLimit(res.max_limit != null ? String(res.max_limit) : '');
      setBirthdayCronEnabled(res.birthday_cron_enabled);
    } catch (err) {
      setEmailMgmt(null);
      setBanner({
        type: 'err',
        text: err instanceof Error ? err.message : 'Không tải được thống kê gửi mail.',
      });
    } finally {
      setEmailMgmtLoading(false);
    }
  }, []);

  useEffect(() => {
    if (tab !== 'manage') return;
    void loadEmailMgmt();
    const id = window.setInterval(() => void loadEmailMgmt(), 30000);
    return () => window.clearInterval(id);
  }, [tab, loadEmailMgmt]);

  const handleSaveWarmup = async () => {
    setSavingWarmup(true);
    setBanner(null);
    try {
      const parsedMax = maxLimit.trim() ? Number(maxLimit.trim()) : null;
      if (parsedMax != null && (!Number.isFinite(parsedMax) || parsedMax < 1)) {
        setBanner({ type: 'err', text: 'Giới hạn tối đa phải là số ≥ 1 hoặc để trống.' });
        return;
      }
      const res = await adminEmailManagementAPI.updateWarmupSettings({
        warmup_enabled: warmupEnabled,
        start_limit: startLimit,
        daily_increment: dailyIncrement,
        max_limit: parsedMax,
        birthday_cron_enabled: birthdayCronEnabled,
      });
      setEmailMgmt(res);
      setBanner({ type: 'ok', text: 'Đã lưu cài đặt warm-up.' });
    } catch (err) {
      setBanner({
        type: 'err',
        text: err instanceof Error ? err.message : 'Lưu cài đặt thất bại.',
      });
    } finally {
      setSavingWarmup(false);
    }
  };

  const handleRunBirthdayBatch = async () => {
    setRunningBirthday(true);
    setBanner(null);
    try {
      const res = await adminEmailManagementAPI.runBirthdayBatch();
      setBanner({ type: 'ok', text: res.message || 'Đã chạy batch CMSN.' });
      await loadEmailMgmt();
    } catch (err) {
      setBanner({
        type: 'err',
        text: err instanceof Error ? err.message : 'Chạy batch CMSN thất bại.',
      });
    } finally {
      setRunningBirthday(false);
    }
  };

  useEffect(() => {
    let active = true;
    const poll = async () => {
      try {
        const st = await adminNewsletterAPI.getCampaignStatus();
        if (!active) return;
        if (st.status === 'running') {
          setCampaignStatus('Đang gửi email marketing…');
        } else if (st.status === 'done') {
          setCampaignStatus(
            `Hoàn tất: gửi OK ${st.sent ?? 0}, lỗi ${st.failed ?? 0}${
              st.deferred_quota ? `, chờ quota ${st.deferred_quota}` : ''
            }${st.subject ? ` — «${st.subject}»` : ''}`,
          );
        } else {
          setCampaignStatus(null);
        }
      } catch {
        if (active) setCampaignStatus(null);
      }
    };
    void poll();
    const id = window.setInterval(() => void poll(), 8000);
    return () => {
      active = false;
      window.clearInterval(id);
    };
  }, []);

  const items = useMemo(() => data?.items ?? [], [data?.items]);
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const activeTotal = data?.active_total ?? 0;

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    void load();
  };

  const handleExport = async () => {
    setExporting(true);
    setBanner(null);
    try {
      await adminNewsletterAPI.exportCsv({
        q: q.trim() || undefined,
        active_only: activeOnlyParam,
      });
      setBanner({ type: 'ok', text: 'Đã tải file CSV.' });
    } catch (err) {
      setBanner({
        type: 'err',
        text: err instanceof Error ? err.message : 'Xuất CSV thất bại.',
      });
    } finally {
      setExporting(false);
    }
  };

  const handleImport = async () => {
    setImporting(true);
    setBanner(null);
    setImportDetails(null);
    try {
      let result;
      if (importFile) {
        result = await adminNewsletterAPI.importFile(importFile, 'import');
      } else if (importText.trim()) {
        result = await adminNewsletterAPI.importText(importText, 'import');
      } else {
        setBanner({ type: 'err', text: 'Chọn file hoặc dán danh sách email.' });
        return;
      }
      setBanner({ type: 'ok', text: formatImportResult(result) });
      setImportDetails({
        corrections: result.corrections,
        invalid_rows: result.invalid_rows,
      });
      setImportText('');
      setImportFile(null);
      setPage(1);
      await load();
    } catch (err) {
      setBanner({
        type: 'err',
        text: err instanceof Error ? err.message : 'Import thất bại.',
      });
    } finally {
      setImporting(false);
    }
  };

  const handleSendTest = async () => {
    if (!campaignSubject.trim() || !campaignMessage.trim()) {
      setBanner({ type: 'err', text: 'Nhập tiêu đề và nội dung email.' });
      return;
    }
    if (!testEmail.trim()) {
      setBanner({ type: 'err', text: 'Nhập email để gửi thử.' });
      return;
    }
    setSendingTest(true);
    setBanner(null);
    try {
      const res = await adminNewsletterAPI.sendCampaign({
        subject: campaignSubject.trim(),
        message: campaignMessage.trim(),
        test_email: testEmail.trim(),
      });
      setBanner({ type: 'ok', text: res.message });
    } catch (err) {
      setBanner({
        type: 'err',
        text: err instanceof Error ? err.message : 'Gửi thử thất bại.',
      });
    } finally {
      setSendingTest(false);
    }
  };

  const handleSendBroadcast = async () => {
    if (!campaignSubject.trim() || !campaignMessage.trim()) {
      setBanner({ type: 'err', text: 'Nhập tiêu đề và nội dung email.' });
      return;
    }
    setSendingBroadcast(true);
    setBanner(null);
    try {
      const res = await adminNewsletterAPI.sendCampaign({
        subject: campaignSubject.trim(),
        message: campaignMessage.trim(),
      });
      setBanner({ type: 'ok', text: res.message });
      setConfirmBroadcast(false);
      setCampaignStatus(`Đang gửi tới ${res.recipient_count} email…`);
    } catch (err) {
      setBanner({
        type: 'err',
        text: err instanceof Error ? err.message : 'Gửi marketing thất bại.',
      });
    } finally {
      setSendingBroadcast(false);
    }
  };

  return (
    <div className="p-6 max-w-6xl space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Quản lý gửi email</h1>
          <p className="text-sm text-gray-600 mt-1">
            CMSN sinh nhật, warm-up SMTP và email marketing. Đang active:{' '}
            <strong>{activeTotal || '…'}</strong>
            {data != null && tab === 'list' ? ` · Hiển thị ${total} theo bộ lọc` : null}
          </p>
        </div>
        {tab === 'list' ? (
          <button
            type="button"
            onClick={() => void handleExport()}
            disabled={exporting || loading}
            className="px-4 py-2 rounded-lg bg-[#ea580c] text-white text-sm font-semibold hover:bg-orange-600 disabled:opacity-60"
          >
            {exporting ? 'Đang xuất…' : 'Tải CSV'}
          </button>
        ) : (
          <button
            type="button"
            onClick={() => void loadEmailMgmt()}
            disabled={emailMgmtLoading}
            className="px-4 py-2 rounded-lg border border-gray-300 bg-white text-sm font-medium hover:bg-gray-50 disabled:opacity-60"
          >
            {emailMgmtLoading ? 'Đang tải…' : 'Làm mới'}
          </button>
        )}
      </div>

      <div className="flex gap-2 border-b border-gray-200">
        <button
          type="button"
          onClick={() => setTab('manage')}
          className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
            tab === 'manage'
              ? 'border-[#ea580c] text-[#ea580c]'
              : 'border-transparent text-gray-600 hover:text-gray-900'
          }`}
        >
          Gửi mail & thống kê
        </button>
        <button
          type="button"
          onClick={() => setTab('list')}
          className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
            tab === 'list'
              ? 'border-[#ea580c] text-[#ea580c]'
              : 'border-transparent text-gray-600 hover:text-gray-900'
          }`}
        >
          Danh sách & marketing
        </button>
      </div>

      {banner && (
        <div
          className={`rounded-lg border px-4 py-3 text-sm ${
            banner.type === 'ok'
              ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
              : 'border-red-200 bg-red-50 text-red-700'
          }`}
        >
          {banner.text}
        </div>
      )}

      {importDetails && tab === 'list' && (importDetails.corrections?.length || importDetails.invalid_rows?.length) ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {importDetails.corrections?.length ? (
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm">
              <h3 className="font-semibold text-amber-900 mb-2">
                Email đã tự sửa ({importDetails.corrections.length}
                {importDetails.corrections.length >= 100 ? '+' : ''})
              </h3>
              <ul className="space-y-1 max-h-48 overflow-y-auto text-amber-950">
                {importDetails.corrections.map((c) => (
                  <li key={`${c.row}-${c.original}`}>
                    Dòng {c.row}: <span className="line-through opacity-70">{c.original}</span> →{' '}
                    <strong>{c.fixed}</strong>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {importDetails.invalid_rows?.length ? (
            <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm">
              <h3 className="font-semibold text-red-900 mb-2">
                Email không import được ({importDetails.invalid_rows.length}
                {importDetails.invalid_rows.length >= 100 ? '+' : ''})
              </h3>
              <ul className="space-y-1 max-h-48 overflow-y-auto text-red-900">
                {importDetails.invalid_rows.map((r) => (
                  <li key={`${r.row}-${r.email}`}>
                    Dòng {r.row}: {r.email || '(trống)'} — {r.reason}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}

      {tab === 'manage' ? (
        <>
          {emailMgmtLoading && !emailMgmt ? (
            <div className="rounded-xl border border-gray-200 bg-white p-12 text-center text-sm text-gray-500">
              Đang tải thống kê…
            </div>
          ) : !emailMgmt ? (
            <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-sm text-red-800">
              Không tải được dữ liệu gửi mail. Backend có thể chưa restart sau cập nhật — hãy chạy lại{' '}
              <code className="bg-red-100 px-1 rounded">uvicorn main:app --port 8001 --reload</code> trong thư mục{' '}
              <code className="bg-red-100 px-1 rounded">backend</code>, rồi{' '}
              <button type="button" onClick={() => void loadEmailMgmt()} className="underline font-medium">
                thử lại
              </button>
              .
            </div>
          ) : (
            <>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <div className="rounded-xl border border-gray-200 bg-white p-4">
                  <p className="text-xs text-gray-500 uppercase tracking-wide">Hôm nay — giới hạn</p>
                  <p className="text-2xl font-bold text-gray-900 mt-1">
                    {emailMgmt.warmup_enabled
                      ? `${emailMgmt.daily_sent_total} / ${emailMgmt.daily_limit ?? '—'}`
                      : 'Không giới hạn'}
                  </p>
                  {emailMgmt.warmup_enabled ? (
                    <p className="text-xs text-gray-500 mt-1">
                      Còn lại {emailMgmt.remaining_today ?? 0} · Ngày warm-up #{emailMgmt.warmup_day}
                    </p>
                  ) : null}
                </div>
                <div className="rounded-xl border border-gray-200 bg-white p-4">
                  <p className="text-xs text-gray-500 uppercase tracking-wide">CMSN hôm nay</p>
                  <p className="text-2xl font-bold text-gray-900 mt-1">{emailMgmt.daily_birthday_sent}</p>
                  <p className="text-xs text-gray-500 mt-1">
                    Chờ gửi {emailMgmt.birthday_pending_today} · Tổng đã gửi {emailMgmt.birthday_sent_all_time}
                  </p>
                </div>
                <div className="rounded-xl border border-gray-200 bg-white p-4">
                  <p className="text-xs text-gray-500 uppercase tracking-wide">Marketing hôm nay</p>
                  <p className="text-2xl font-bold text-gray-900 mt-1">{emailMgmt.daily_marketing_sent}</p>
                  <p className="text-xs text-gray-500 mt-1">Dùng phần quota còn lại sau CMSN</p>
                </div>
                <div className="rounded-xl border border-gray-200 bg-white p-4">
                  <p className="text-xs text-gray-500 uppercase tracking-wide">CMSN tự động</p>
                  <p className="text-2xl font-bold text-gray-900 mt-1">
                    {emailMgmt.birthday_cron_enabled ? 'Bật' : 'Tắt'}
                  </p>
                  <p className="text-xs text-gray-500 mt-1">
                    Gửi {emailMgmt.birthday_send_days_before} ngày trước sinh nhật
                  </p>
                </div>
              </div>

              <div className="grid gap-6 lg:grid-cols-2">
                <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-4">
                  <div>
                    <h2 className="text-lg font-semibold text-gray-900">Cài đặt warm-up</h2>
                    <p className="text-xs text-gray-500 mt-1">
                      Bắt đầu {startLimit} email/ngày, mỗi ngày tăng thêm {dailyIncrement}. CMSN được ưu tiên
                      trước marketing.
                    </p>
                  </div>
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={warmupEnabled}
                      onChange={(e) => setWarmupEnabled(e.target.checked)}
                      className="rounded border-gray-300"
                    />
                    Bật giới hạn warm-up hàng ngày
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={birthdayCronEnabled}
                      onChange={(e) => setBirthdayCronEnabled(e.target.checked)}
                      className="rounded border-gray-300"
                    />
                    Tự động gửi CMSN (cron hàng ngày)
                  </label>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Email/ngày ban đầu</label>
                      <input
                        type="number"
                        min={1}
                        value={startLimit}
                        onChange={(e) => setStartLimit(Number(e.target.value) || 5)}
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Tăng mỗi ngày</label>
                      <input
                        type="number"
                        min={1}
                        value={dailyIncrement}
                        onChange={(e) => setDailyIncrement(Number(e.target.value) || 5)}
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Giới hạn tối đa/ngày (tùy chọn)
                    </label>
                    <input
                      type="number"
                      min={1}
                      value={maxLimit}
                      onChange={(e) => setMaxLimit(e.target.value)}
                      placeholder="Không giới hạn trần"
                      className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                    />
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={savingWarmup}
                      onClick={() => void handleSaveWarmup()}
                      className="px-4 py-2 rounded-lg bg-[#ea580c] text-white text-sm font-semibold hover:bg-orange-600 disabled:opacity-60"
                    >
                      {savingWarmup ? 'Đang lưu…' : 'Lưu cài đặt'}
                    </button>
                    <button
                      type="button"
                      disabled={runningBirthday}
                      onClick={() => void handleRunBirthdayBatch()}
                      className="px-4 py-2 rounded-lg border border-gray-300 bg-white text-sm font-medium hover:bg-gray-50 disabled:opacity-60"
                    >
                      {runningBirthday ? 'Đang gửi CMSN…' : 'Chạy batch CMSN ngay'}
                    </button>
                  </div>
                </div>

                <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
                  <h2 className="text-lg font-semibold text-gray-900">Lịch sử gửi CMSN (14 ngày)</h2>
                  {!emailMgmt.recent_days.length ? (
                    <p className="text-sm text-gray-500">Chưa có email CMSN nào được ghi nhận.</p>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="min-w-full text-sm">
                        <thead className="bg-gray-50 text-left text-gray-600">
                          <tr>
                            <th className="px-3 py-2 font-semibold">Ngày</th>
                            <th className="px-3 py-2 font-semibold">Đã gửi</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100">
                          {emailMgmt.recent_days.map((row) => (
                            <tr key={row.date}>
                              <td className="px-3 py-2 text-gray-900">{row.date}</td>
                              <td className="px-3 py-2 font-medium">{row.birthday_sent}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </>
      ) : (
        <>
      {campaignStatus && (
        <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">
          {campaignStatus}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
          <h2 className="text-lg font-semibold text-gray-900">Import email marketing</h2>
          <p className="text-xs text-gray-500">
            Chỉ danh sách email nhận tin quảng cáo (CSV/TXT cột <code className="bg-gray-100 px-1 rounded">email</code>).
            Khách hàng cũ đầy đủ hồ sơ → import tại{' '}
            <a href="/admin/members" className="text-orange-700 underline font-medium">
              Quản lý thành viên
            </a>
            .
          </p>
          <input
            type="file"
            accept=".csv,.xlsx,.xls,.txt"
            onChange={(e) => {
              setImportFile(e.target.files?.[0] ?? null);
            }}
            className="block w-full text-sm text-gray-600 file:mr-3 file:py-2 file:px-3 file:rounded-lg file:border-0 file:bg-orange-50 file:text-orange-800"
          />
          <textarea
            value={importText}
            onChange={(e) => setImportText(e.target.value)}
            rows={5}
            placeholder={'Hoặc dán email:\nkhach1@gmail.com\nkhach2@yahoo.com'}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono"
          />
          <button
            type="button"
            disabled={importing}
            onClick={() => void handleImport()}
            className="px-4 py-2 rounded-lg bg-gray-900 text-white text-sm font-medium hover:bg-gray-800 disabled:opacity-60"
          >
            {importing ? 'Đang import…' : 'Import vào danh sách'}
          </button>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
          <h2 className="text-lg font-semibold text-gray-900">Gửi email marketing</h2>
          <p className="text-xs text-gray-500">
            Gửi thử trước, rồi gửi tới <strong>{activeTotal || 0}</strong> email đang nhận tin. Cần SMTP trong
            backend.
          </p>
          <input
            type="text"
            value={campaignSubject}
            onChange={(e) => setCampaignSubject(e.target.value)}
            placeholder="Tiêu đề email"
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
          />
          <textarea
            value={campaignMessage}
            onChange={(e) => setCampaignMessage(e.target.value)}
            rows={6}
            placeholder="Nội dung (plain text). Email có nút vào 188.com.vn."
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
          />
          <div className="flex flex-wrap gap-2 items-end">
            <div className="flex-1 min-w-[180px]">
              <label className="block text-xs text-gray-600 mb-1">Gửi thử tới</label>
              <input
                type="email"
                value={testEmail}
                onChange={(e) => setTestEmail(e.target.value)}
                placeholder="email@…"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
              />
            </div>
            <button
              type="button"
              disabled={sendingTest || sendingBroadcast}
              onClick={() => void handleSendTest()}
              className="px-4 py-2 rounded-lg border border-gray-300 bg-white text-sm font-medium hover:bg-gray-50 disabled:opacity-60"
            >
              {sendingTest ? 'Đang gửi…' : 'Gửi thử'}
            </button>
          </div>
          {!confirmBroadcast ? (
            <button
              type="button"
              disabled={sendingBroadcast || activeTotal <= 0}
              onClick={() => setConfirmBroadcast(true)}
              className="w-full px-4 py-2 rounded-lg bg-[#ea580c] text-white text-sm font-semibold hover:bg-orange-600 disabled:opacity-60"
            >
              Gửi tới toàn bộ danh sách active
            </button>
          ) : (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 space-y-2">
              <p className="text-sm text-amber-900">
                Xác nhận gửi email tới <strong>{activeTotal}</strong> địa chỉ đang nhận tin?
              </p>
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={sendingBroadcast}
                  onClick={() => void handleSendBroadcast()}
                  className="px-4 py-2 rounded-lg bg-[#ea580c] text-white text-sm font-semibold disabled:opacity-60"
                >
                  {sendingBroadcast ? 'Đang khởi chạy…' : 'Xác nhận gửi'}
                </button>
                <button
                  type="button"
                  disabled={sendingBroadcast}
                  onClick={() => setConfirmBroadcast(false)}
                  className="px-4 py-2 rounded-lg border border-gray-300 text-sm"
                >
                  Hủy
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <form onSubmit={handleSearch} className="flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-[200px]">
            <label className="block text-sm font-medium text-gray-700 mb-1">Tìm email / nguồn</label>
            <input
              type="search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="email@… hoặc import"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Trạng thái</label>
            <select
              value={activeFilter}
              onChange={(e) => {
                setActiveFilter(e.target.value as 'all' | 'active' | 'inactive');
                setPage(1);
              }}
              className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
            >
              <option value="all">Tất cả</option>
              <option value="active">Đang nhận tin</option>
              <option value="inactive">Đã hủy / tắt</option>
            </select>
          </div>
          <button
            type="submit"
            disabled={loading}
            className="px-4 py-2 rounded-lg border border-gray-300 bg-white text-sm font-medium hover:bg-gray-50 disabled:opacity-60"
          >
            Lọc
          </button>
        </form>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="p-12 text-center text-gray-500 text-sm">Đang tải…</div>
        ) : items.length === 0 ? (
          <div className="p-12 text-center text-gray-500 text-sm">
            Chưa có email — import danh sách hoặc chờ khách đăng ký footer.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 text-left text-gray-600">
                <tr>
                  <th className="px-4 py-3 font-semibold">Email</th>
                  <th className="px-4 py-3 font-semibold">Thành viên</th>
                  <th className="px-4 py-3 font-semibold">Nguồn</th>
                  <th className="px-4 py-3 font-semibold">Trạng thái</th>
                  <th className="px-4 py-3 font-semibold">Đăng ký lúc</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {items.map((row: AdminNewsletterSubscriber) => (
                  <tr key={row.id} className="hover:bg-gray-50/80">
                    <td className="px-4 py-3 font-medium text-gray-900">{row.email}</td>
                    <td className="px-4 py-3 text-gray-700">
                      {row.user_id ? (
                        <span>
                          #{row.user_id}
                          {row.user_full_name ? ` · ${row.user_full_name}` : ''}
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-600">{row.source}</td>
                    <td className="px-4 py-3">
                      {row.is_active ? (
                        <span className="inline-flex rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">
                          Đang nhận
                        </span>
                      ) : (
                        <span className="inline-flex rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">
                          Tắt
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-600 whitespace-nowrap">
                      {formatDate(row.subscribed_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {totalPages > 1 && (
          <div className="flex items-center justify-between gap-3 px-4 py-3 border-t border-gray-100">
            <span className="text-xs text-gray-500">
              Trang {page}/{totalPages}
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={page <= 1 || loading}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="px-3 py-1.5 text-sm rounded-lg border border-gray-300 disabled:opacity-50"
              >
                Trước
              </button>
              <button
                type="button"
                disabled={page >= totalPages || loading}
                onClick={() => setPage((p) => p + 1)}
                className="px-3 py-1.5 text-sm rounded-lg border border-gray-300 disabled:opacity-50"
              >
                Sau
              </button>
            </div>
          </div>
        )}
      </div>
        </>
      )}
    </div>
  );
}
