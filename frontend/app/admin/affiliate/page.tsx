'use client';

import { useCallback, useEffect, useState, type ChangeEvent, type FormEvent } from 'react';
import {
  adminAffiliateAPI,
  type AdminAffiliateApplication,
  type AdminAffiliateCommission,
  type AdminAffiliateSettings,
  type AdminWalletWithdrawal,
} from '@/lib/admin-api';

function fmt(amount: number) {
  return new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(amount || 0);
}

function fmtDate(value?: string | null) {
  if (!value) return '—';
  return new Date(value).toLocaleString('vi-VN');
}

const STATUS_LABEL: Record<string, string> = {
  pending: 'Chờ duyệt',
  approved: 'Đã chuyển',
  rejected: 'Từ chối',
  confirmed: 'Đã xác nhận',
  cancelled: 'Đã hủy',
};

type TabKey = 'settings' | 'applications' | 'commissions' | 'withdrawals';

export default function AdminAffiliatePage() {
  const [activeTab, setActiveTab] = useState<TabKey>('settings');
  const [settings, setSettings] = useState<AdminAffiliateSettings | null>(null);
  const [applications, setApplications] = useState<AdminAffiliateApplication[]>([]);
  const [commissions, setCommissions] = useState<AdminAffiliateCommission[]>([]);
  const [withdrawals, setWithdrawals] = useState<AdminWalletWithdrawal[]>([]);
  const [settingsLoading, setSettingsLoading] = useState(true);
  const [applicationsLoading, setApplicationsLoading] = useState(true);
  const [commissionsLoading, setCommissionsLoading] = useState(true);
  const [withdrawalsLoading, setWithdrawalsLoading] = useState(true);
  const [savingSettings, setSavingSettings] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ type: 'ok' | 'err'; msg: string } | null>(null);
  const [applicationFilter, setApplicationFilter] = useState<'pending' | 'all' | 'approved' | 'rejected'>('pending');
  const [withdrawalFilter, setWithdrawalFilter] = useState<'pending' | 'all'>('pending');
  const [commissionFilter, setCommissionFilter] = useState<'all' | 'confirmed' | 'pending' | 'cancelled'>('all');
  const [busyId, setBusyId] = useState<number | null>(null);
  const [rejectTarget, setRejectTarget] = useState<AdminWalletWithdrawal | null>(null);
  const [rejectNote, setRejectNote] = useState('');
  const [appRejectTarget, setAppRejectTarget] = useState<AdminAffiliateApplication | null>(null);
  const [appRejectNote, setAppRejectNote] = useState('');

  const showToast = (type: 'ok' | 'err', msg: string) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 4000);
  };

  const loadSettings = useCallback(async () => {
    setSettingsLoading(true);
    setError(null);
    try {
      setSettings(await adminAffiliateAPI.getSettings());
    } catch (err: any) {
      setError(err?.message || 'Không tải được cài đặt affiliate');
    } finally {
      setSettingsLoading(false);
    }
  }, []);

  const loadApplications = useCallback(async () => {
    setApplicationsLoading(true);
    setError(null);
    try {
      const status = applicationFilter === 'all' ? undefined : applicationFilter;
      setApplications(await adminAffiliateAPI.listApplications(status));
    } catch (err: any) {
      setError(err?.message || 'Không tải được danh sách đăng ký affiliate');
    } finally {
      setApplicationsLoading(false);
    }
  }, [applicationFilter]);

  const loadCommissions = useCallback(async () => {
    setCommissionsLoading(true);
    setError(null);
    try {
      const status = commissionFilter === 'all' ? undefined : commissionFilter;
      setCommissions(await adminAffiliateAPI.listCommissions(status));
    } catch (err: any) {
      setError(err?.message || 'Không tải được danh sách hoa hồng');
    } finally {
      setCommissionsLoading(false);
    }
  }, [commissionFilter]);

  const loadWithdrawals = useCallback(async () => {
    setWithdrawalsLoading(true);
    setError(null);
    try {
      const status = withdrawalFilter === 'pending' ? 'pending' : undefined;
      setWithdrawals(await adminAffiliateAPI.listWithdrawals(status));
    } catch (err: any) {
      setError(err?.message || 'Không tải được danh sách rút tiền');
    } finally {
      setWithdrawalsLoading(false);
    }
  }, [withdrawalFilter]);

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

  useEffect(() => {
    void loadApplications();
  }, [loadApplications]);

  useEffect(() => {
    void loadCommissions();
  }, [loadCommissions]);

  useEffect(() => {
    void loadWithdrawals();
  }, [loadWithdrawals]);

  const setSettingNumber =
    (key: 'commission_percent' | 'min_withdrawal' | 'ref_cookie_days') =>
    (event: ChangeEvent<HTMLInputElement>) => {
      const value = event.target.value === '' ? 0 : Number(event.target.value);
      setSettings((prev) => (prev ? { ...prev, [key]: Number.isFinite(value) ? value : 0 } : prev));
    };

  const saveSettings = async (event: FormEvent) => {
    event.preventDefault();
    if (!settings) return;
    if (settings.commission_percent < 0 || settings.commission_percent > 100) {
      showToast('err', 'Hoa hồng phải nằm trong khoảng 0-100%.');
      return;
    }
    if (settings.ref_cookie_days < 1 || settings.ref_cookie_days > 365) {
      showToast('err', 'Thời hạn cookie phải từ 1 đến 365 ngày.');
      return;
    }
    setSavingSettings(true);
    try {
      const saved = await adminAffiliateAPI.updateSettings({
        enabled: settings.enabled,
        commission_percent: settings.commission_percent,
        min_withdrawal: settings.min_withdrawal,
        ref_cookie_days: settings.ref_cookie_days,
        commission_policy: settings.commission_policy || null,
      });
      setSettings(saved);
      showToast('ok', 'Đã lưu cài đặt affiliate.');
    } catch (err: any) {
      showToast('err', err?.message || 'Không lưu được cài đặt');
    } finally {
      setSavingSettings(false);
    }
  };

  const approve = async (id: number) => {
    setBusyId(id);
    try {
      await adminAffiliateAPI.approveWithdrawal(id);
      showToast('ok', 'Đã duyệt yêu cầu rút tiền.');
      await loadWithdrawals();
    } catch (err: any) {
      setError(err?.message || 'Không duyệt được');
    } finally {
      setBusyId(null);
    }
  };

  const approveApplication = async (id: number) => {
    setBusyId(id);
    try {
      await adminAffiliateAPI.approveApplication(id);
      showToast('ok', 'Đã phê duyệt người dùng làm affiliate.');
      await loadApplications();
    } catch (err: any) {
      setError(err?.message || 'Không phê duyệt được hồ sơ');
    } finally {
      setBusyId(null);
    }
  };

  const rejectApplication = async () => {
    if (!appRejectTarget) return;
    setBusyId(appRejectTarget.id);
    try {
      await adminAffiliateAPI.rejectApplication(appRejectTarget.id, appRejectNote || undefined);
      showToast('ok', 'Đã từ chối hồ sơ affiliate.');
      setAppRejectTarget(null);
      setAppRejectNote('');
      await loadApplications();
    } catch (err: any) {
      setError(err?.message || 'Không từ chối được hồ sơ');
    } finally {
      setBusyId(null);
    }
  };

  const reject = async () => {
    if (!rejectTarget) return;
    setBusyId(rejectTarget.id);
    try {
      await adminAffiliateAPI.rejectWithdrawal(rejectTarget.id, rejectNote || undefined);
      showToast('ok', 'Đã từ chối và hoàn tiền vào ví.');
      setRejectTarget(null);
      setRejectNote('');
      await loadWithdrawals();
    } catch (err: any) {
      setError(err?.message || 'Không từ chối được');
    } finally {
      setBusyId(null);
    }
  };

  const tabClass = (key: TabKey) =>
    `px-3 py-2 rounded-lg text-sm font-semibold ${
      activeTab === key ? 'bg-orange-100 text-orange-800' : 'text-gray-600 hover:bg-gray-100'
    }`;

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Affiliate & ví</h1>
          <p className="text-sm text-gray-600">Cài đặt hoa hồng, theo dõi đơn giới thiệu và duyệt rút tiền</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setActiveTab('settings')}
            className={tabClass('settings')}
          >
            Cài đặt
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('applications')}
            className={tabClass('applications')}
          >
            Người đăng ký
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('commissions')}
            className={tabClass('commissions')}
          >
            Hoa hồng
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('withdrawals')}
            className={tabClass('withdrawals')}
          >
            Rút tiền
          </button>
        </div>
      </div>

      {error ? (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
          {error}{' '}
          <button
            type="button"
            onClick={() => {
              void loadSettings();
              void loadApplications();
              void loadCommissions();
              void loadWithdrawals();
            }}
            className="underline font-medium"
          >
            Thử lại
          </button>
        </div>
      ) : null}

      {activeTab === 'settings' ? (
        <div className="bg-white rounded-xl border border-gray-100 p-5">
          {settingsLoading || !settings ? (
            <div className="p-8 text-center text-sm text-gray-500">Đang tải cài đặt…</div>
          ) : (
            <form onSubmit={saveSettings} className="space-y-5">
              <div className="flex items-center justify-between gap-4 rounded-lg border border-orange-100 bg-orange-50 px-4 py-3">
                <div>
                  <p className="font-semibold text-gray-900">Bật chương trình affiliate</p>
                  <p className="text-sm text-gray-600">Khi tắt, hệ thống không nhận mã giới thiệu mới và không phát sinh hoa hồng mới.</p>
                </div>
                <label className="inline-flex items-center gap-2 text-sm font-medium text-gray-800">
                  <input
                    type="checkbox"
                    checked={settings.enabled}
                    onChange={(event) => setSettings((prev) => (prev ? { ...prev, enabled: event.target.checked } : prev))}
                    className="h-4 w-4 rounded border-gray-300 text-orange-600 focus:ring-orange-500"
                  />
                  Đang bật
                </label>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <label className="block">
                  <span className="text-sm font-medium text-gray-700">Hoa hồng (%)</span>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    step={0.01}
                    value={settings.commission_percent}
                    onChange={setSettingNumber('commission_percent')}
                    className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  />
                </label>
                <label className="block">
                  <span className="text-sm font-medium text-gray-700">Rút tối thiểu (VND)</span>
                  <input
                    type="number"
                    min={0}
                    step={1000}
                    value={settings.min_withdrawal}
                    onChange={setSettingNumber('min_withdrawal')}
                    className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  />
                </label>
                <label className="block">
                  <span className="text-sm font-medium text-gray-700">Cookie giới thiệu (ngày)</span>
                  <input
                    type="number"
                    min={1}
                    max={365}
                    value={settings.ref_cookie_days}
                    onChange={setSettingNumber('ref_cookie_days')}
                    className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  />
                </label>
              </div>

              <label className="block">
                <span className="text-sm font-medium text-gray-700">Ghi chú chính sách hoa hồng</span>
                <textarea
                  value={settings.commission_policy || ''}
                  onChange={(event) => setSettings((prev) => (prev ? { ...prev, commission_policy: event.target.value } : prev))}
                  rows={4}
                  placeholder="Ví dụ: Hoa hồng tính trên giá sản phẩm sau giảm giá, không gồm phí ship."
                  className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                />
              </label>

              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <p className="text-xs text-gray-500">
                  Cập nhật cuối: {fmtDate(settings.updated_at)}
                  {settings.updated_by ? ` bởi admin #${settings.updated_by}` : ''}
                </p>
                <button
                  type="submit"
                  disabled={savingSettings}
                  className="rounded-lg bg-[#ea580c] px-4 py-2 text-sm font-semibold text-white hover:bg-orange-700 disabled:opacity-50"
                >
                  {savingSettings ? 'Đang lưu…' : 'Lưu cài đặt'}
                </button>
              </div>
            </form>
          )}
        </div>
      ) : null}

      {activeTab === 'applications' ? (
        <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
          <div className="flex items-center justify-between gap-3 border-b border-gray-100 px-4 py-3">
            <h2 className="font-semibold text-gray-900">Người đăng ký làm affiliate</h2>
            <select
              value={applicationFilter}
              onChange={(event) => setApplicationFilter(event.target.value as typeof applicationFilter)}
              className="rounded-lg border border-gray-200 px-3 py-2 text-sm"
            >
              <option value="pending">Chờ duyệt</option>
              <option value="all">Tất cả</option>
              <option value="approved">Đã duyệt</option>
              <option value="rejected">Từ chối</option>
            </select>
          </div>
          {applicationsLoading ? (
            <div className="p-8 text-center text-sm text-gray-500">Đang tải hồ sơ đăng ký…</div>
          ) : applications.length === 0 ? (
            <div className="p-8 text-center text-sm text-gray-500">Không có hồ sơ đăng ký phù hợp.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-gray-50 text-left text-gray-600">
                  <tr>
                    <th className="px-4 py-3">ID</th>
                    <th className="px-4 py-3">User</th>
                    <th className="px-4 py-3">Email</th>
                    <th className="px-4 py-3">Link MXH</th>
                    <th className="px-4 py-3">Ghi chú</th>
                    <th className="px-4 py-3">Trạng thái</th>
                    <th className="px-4 py-3">Ngày gửi</th>
                    <th className="px-4 py-3">Thao tác</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {applications.map((row) => (
                    <tr key={row.id}>
                      <td className="px-4 py-3">#{row.id}</td>
                      <td className="px-4 py-3">#{row.user_id}</td>
                      <td className="px-4 py-3">
                        {row.user_email ? (
                          <a href={`mailto:${row.user_email}`} className="text-orange-700 hover:underline">
                            {row.user_email}
                          </a>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <div className="space-y-1">
                          {row.social_links.map((link) => (
                            <a
                              key={link}
                              href={link}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="block max-w-xs truncate text-orange-700 underline"
                            >
                              {link}
                            </a>
                          ))}
                        </div>
                      </td>
                      <td className="px-4 py-3 max-w-xs">
                        <p className="text-gray-700">{row.note || '—'}</p>
                        {row.admin_note ? <p className="mt-1 text-xs text-red-600">Admin: {row.admin_note}</p> : null}
                      </td>
                      <td className="px-4 py-3">
                        {row.status === 'approved' ? 'Đã duyệt' : row.status === 'rejected' ? 'Từ chối' : 'Chờ duyệt'}
                      </td>
                      <td className="px-4 py-3 text-xs text-gray-500">{fmtDate(row.submitted_at)}</td>
                      <td className="px-4 py-3">
                        {row.status === 'pending' ? (
                          <div className="flex gap-2">
                            <button
                              type="button"
                              disabled={busyId === row.id}
                              onClick={() => void approveApplication(row.id)}
                              className="text-green-700 font-medium hover:underline disabled:opacity-50"
                            >
                              Duyệt
                            </button>
                            <button
                              type="button"
                              disabled={busyId === row.id}
                              onClick={() => {
                                setAppRejectTarget(row);
                                setAppRejectNote('');
                              }}
                              className="text-red-600 font-medium hover:underline disabled:opacity-50"
                            >
                              Từ chối
                            </button>
                          </div>
                        ) : (
                          <span className="text-xs text-gray-500">{row.reviewed_at ? fmtDate(row.reviewed_at) : '—'}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : null}

      {activeTab === 'commissions' ? (
        <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
          <div className="flex items-center justify-between gap-3 border-b border-gray-100 px-4 py-3">
            <h2 className="font-semibold text-gray-900">Danh sách hoa hồng</h2>
            <select
              value={commissionFilter}
              onChange={(event) => setCommissionFilter(event.target.value as typeof commissionFilter)}
              className="rounded-lg border border-gray-200 px-3 py-2 text-sm"
            >
              <option value="all">Tất cả</option>
              <option value="confirmed">Đã xác nhận</option>
              <option value="pending">Chờ duyệt</option>
              <option value="cancelled">Đã hủy</option>
            </select>
          </div>
          {commissionsLoading ? (
            <div className="p-8 text-center text-sm text-gray-500">Đang tải hoa hồng…</div>
          ) : commissions.length === 0 ? (
            <div className="p-8 text-center text-sm text-gray-500">Chưa có hoa hồng phù hợp.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-gray-50 text-left text-gray-600">
                  <tr>
                    <th className="px-4 py-3">ID</th>
                    <th className="px-4 py-3">Người giới thiệu</th>
                    <th className="px-4 py-3">Người mua</th>
                    <th className="px-4 py-3">Đơn hàng</th>
                    <th className="px-4 py-3">Giá trị tính</th>
                    <th className="px-4 py-3">Hoa hồng</th>
                    <th className="px-4 py-3">Trạng thái</th>
                    <th className="px-4 py-3">Ngày tạo</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {commissions.map((row) => (
                    <tr key={row.id}>
                      <td className="px-4 py-3">#{row.id}</td>
                      <td className="px-4 py-3">#{row.referrer_user_id}</td>
                      <td className="px-4 py-3">{row.buyer_user_id ? `#${row.buyer_user_id}` : '—'}</td>
                      <td className="px-4 py-3">#{row.order_id}</td>
                      <td className="px-4 py-3">{fmt(Number(row.order_base_amount))}</td>
                      <td className="px-4 py-3 font-semibold">
                        {fmt(Number(row.commission_amount))}
                        <span className="ml-1 text-xs text-gray-500">({Number(row.commission_percent)}%)</span>
                      </td>
                      <td className="px-4 py-3">{STATUS_LABEL[row.status] || row.status}</td>
                      <td className="px-4 py-3 text-xs text-gray-500">{fmtDate(row.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : null}

      {activeTab === 'withdrawals' ? (
        <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
          <div className="flex items-center justify-between gap-3 border-b border-gray-100 px-4 py-3">
            <h2 className="font-semibold text-gray-900">Yêu cầu rút tiền</h2>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setWithdrawalFilter('pending')}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium ${withdrawalFilter === 'pending' ? 'bg-orange-100 text-orange-800' : 'bg-gray-100'}`}
              >
                Chờ duyệt
              </button>
              <button
                type="button"
                onClick={() => setWithdrawalFilter('all')}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium ${withdrawalFilter === 'all' ? 'bg-orange-100 text-orange-800' : 'bg-gray-100'}`}
              >
                Tất cả
              </button>
            </div>
          </div>

          {withdrawalsLoading ? (
            <div className="p-8 text-center text-sm text-gray-500">Đang tải yêu cầu rút tiền…</div>
          ) : withdrawals.length === 0 ? (
            <div className="p-8 text-center text-sm text-gray-500">Không có yêu cầu rút tiền.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-gray-50 text-left text-gray-600">
                  <tr>
                    <th className="px-4 py-3">ID</th>
                    <th className="px-4 py-3">User</th>
                    <th className="px-4 py-3">Số tiền</th>
                    <th className="px-4 py-3">Ngân hàng</th>
                    <th className="px-4 py-3">Trạng thái</th>
                    <th className="px-4 py-3">Thao tác</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {withdrawals.map((row) => (
                    <tr key={row.id}>
                      <td className="px-4 py-3">#{row.id}</td>
                      <td className="px-4 py-3">#{row.user_id}</td>
                      <td className="px-4 py-3 font-semibold">{fmt(Number(row.amount))}</td>
                      <td className="px-4 py-3">
                        <div>{row.bank_name}</div>
                        <div className="text-xs text-gray-500">
                          {row.bank_account} · {row.account_holder}
                        </div>
                      </td>
                      <td className="px-4 py-3">{STATUS_LABEL[row.status] || row.status}</td>
                      <td className="px-4 py-3">
                        {row.status === 'pending' ? (
                          <div className="flex gap-2">
                            <button
                              type="button"
                              disabled={busyId === row.id}
                              onClick={() => void approve(row.id)}
                              className="text-green-700 font-medium hover:underline disabled:opacity-50"
                            >
                              Duyệt
                            </button>
                            <button
                              type="button"
                              disabled={busyId === row.id}
                              onClick={() => {
                                setRejectTarget(row);
                                setRejectNote('');
                              }}
                              className="text-red-600 font-medium hover:underline disabled:opacity-50"
                            >
                              Từ chối
                            </button>
                          </div>
                        ) : (
                          <span className="text-xs text-gray-500">{row.admin_note || '—'}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : null}

      {rejectTarget ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <div className="w-full max-w-md rounded-xl bg-white p-5 shadow-xl">
            <h3 className="text-lg font-semibold text-gray-900">Từ chối yêu cầu rút tiền</h3>
            <p className="mt-1 text-sm text-gray-600">
              Yêu cầu #{rejectTarget.id} của user #{rejectTarget.user_id}, số tiền {fmt(Number(rejectTarget.amount))}.
            </p>
            <label className="mt-4 block">
              <span className="text-sm font-medium text-gray-700">Lý do từ chối (tuỳ chọn)</span>
              <textarea
                value={rejectNote}
                onChange={(event) => setRejectNote(event.target.value)}
                rows={3}
                className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                placeholder="Ví dụ: Thông tin tài khoản ngân hàng chưa chính xác."
              />
            </label>
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setRejectTarget(null)}
                className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium hover:bg-gray-50"
              >
                Hủy
              </button>
              <button
                type="button"
                disabled={busyId === rejectTarget.id}
                onClick={() => void reject()}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
              >
                {busyId === rejectTarget.id ? 'Đang xử lý…' : 'Từ chối'}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {appRejectTarget ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <div className="w-full max-w-md rounded-xl bg-white p-5 shadow-xl">
            <h3 className="text-lg font-semibold text-gray-900">Từ chối hồ sơ affiliate</h3>
            <p className="mt-1 text-sm text-gray-600">
              Hồ sơ #{appRejectTarget.id} của user #{appRejectTarget.user_id}.
            </p>
            <label className="mt-4 block">
              <span className="text-sm font-medium text-gray-700">Lý do từ chối (tuỳ chọn)</span>
              <textarea
                value={appRejectNote}
                onChange={(event) => setAppRejectNote(event.target.value)}
                rows={3}
                className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                placeholder="Ví dụ: Kênh mạng xã hội chưa phù hợp hoặc thiếu thông tin."
              />
            </label>
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setAppRejectTarget(null)}
                className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium hover:bg-gray-50"
              >
                Hủy
              </button>
              <button
                type="button"
                disabled={busyId === appRejectTarget.id}
                onClick={() => void rejectApplication()}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
              >
                {busyId === appRejectTarget.id ? 'Đang xử lý…' : 'Từ chối'}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {toast ? (
        <div
          className={`fixed bottom-6 right-6 z-[100] rounded-lg px-4 py-2 text-sm text-white shadow ${
            toast.type === 'ok' ? 'bg-green-700' : 'bg-red-600'
          }`}
        >
          {toast.msg}
        </div>
      ) : null}
    </div>
  );
}
