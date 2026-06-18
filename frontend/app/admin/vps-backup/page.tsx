'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  adminVpsBackupAPI,
  type VpsBackupArchiveItem,
  type VpsBackupRunItem,
  type VpsBackupSettings,
} from '@/lib/admin-api';

const WEEKDAYS: { value: number; label: string }[] = [
  { value: 0, label: 'T2' },
  { value: 1, label: 'T3' },
  { value: 2, label: 'T4' },
  { value: 3, label: 'T5' },
  { value: 4, label: 'T6' },
  { value: 5, label: 'T7' },
  { value: 6, label: 'CN' },
];

function formatDt(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString('vi-VN', { dateStyle: 'short', timeStyle: 'short' });
  } catch {
    return iso;
  }
}

function statusBadge(status: string): string {
  switch (status) {
    case 'success':
      return 'bg-green-100 text-green-800';
    case 'failed':
      return 'bg-red-100 text-red-800';
    case 'running':
      return 'bg-blue-100 text-blue-800';
    case 'queued':
      return 'bg-gray-100 text-gray-700';
    default:
      return 'bg-gray-100 text-gray-600';
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case 'success':
      return 'Thành công';
    case 'failed':
      return 'Lỗi';
    case 'running':
      return 'Đang chạy';
    case 'queued':
      return 'Chờ';
    default:
      return status;
  }
}

function driveStatusLabel(status: string | null | undefined): string {
  switch (status) {
    case 'success':
      return 'Đã lên Drive';
    case 'failed':
      return 'Drive lỗi';
    case 'skipped':
      return '—';
    default:
      return status || '—';
  }
}

export default function AdminVpsBackupPage() {
  const [settings, setSettings] = useState<VpsBackupSettings | null>(null);
  const [runs, setRuns] = useState<VpsBackupRunItem[]>([]);
  const [archives, setArchives] = useState<VpsBackupArchiveItem[]>([]);
  const [archiveTotalPretty, setArchiveTotalPretty] = useState('—');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [deletingFile, setDeletingFile] = useState<string | null>(null);
  const [downloadingFile, setDownloadingFile] = useState<string | null>(null);
  const [toast, setToast] = useState<{ type: 'ok' | 'err'; msg: string } | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [formEnabled, setFormEnabled] = useState(false);
  const [formHour, setFormHour] = useState(3);
  const [formMinute, setFormMinute] = useState(0);
  const [formDays, setFormDays] = useState<number[]>([0, 1, 2, 3, 4, 5, 6]);
  const [formIncludeCache, setFormIncludeCache] = useState(false);

  const showToast = (type: 'ok' | 'err', msg: string) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 5000);
  };

  const applySettingsToForm = (s: VpsBackupSettings) => {
    setFormEnabled(s.enabled);
    setFormHour(s.hour);
    setFormMinute(s.minute);
    setFormDays(s.days_of_week?.length ? [...s.days_of_week] : [0, 1, 2, 3, 4, 5, 6]);
    setFormIncludeCache(s.include_cache);
  };

  const loadAll = useCallback(async () => {
    setLoadError(null);
    try {
      const [s, r, a] = await Promise.all([
        adminVpsBackupAPI.getSettings(),
        adminVpsBackupAPI.listRuns({ limit: 30 }),
        adminVpsBackupAPI.listArchives(),
      ]);
      setSettings(s);
      applySettingsToForm(s);
      setRuns(r.items);
      setArchives(a.items);
      setArchiveTotalPretty(a.total_size_pretty);
    } catch (err: unknown) {
      const msg = (err as Error)?.message || 'Không tải được dữ liệu backup';
      setLoadError(msg);
      showToast('err', msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const hasActiveRun = useMemo(
    () => runs.some((r) => r.status === 'queued' || r.status === 'running'),
    [runs],
  );

  useEffect(() => {
    if (!hasActiveRun) return;
    const t = setInterval(() => {
      adminVpsBackupAPI
        .listRuns({ limit: 30 })
        .then((r) => setRuns(r.items))
        .catch(() => {});
      adminVpsBackupAPI
        .listArchives()
        .then((a) => {
          setArchives(a.items);
          setArchiveTotalPretty(a.total_size_pretty);
        })
        .catch(() => {});
    }, 5000);
    return () => clearInterval(t);
  }, [hasActiveRun]);

  const toggleDay = (day: number) => {
    setFormDays((prev) => {
      if (prev.includes(day)) {
        const next = prev.filter((d) => d !== day);
        return next.length ? next : prev;
      }
      return [...prev, day].sort((a, b) => a - b);
    });
  };

  const handleSaveSchedule = async () => {
    setSaving(true);
    try {
      const s = await adminVpsBackupAPI.updateSettings({
        enabled: formEnabled,
        hour: formHour,
        minute: formMinute,
        days_of_week: formDays,
        include_cache: formIncludeCache,
      });
      setSettings(s);
      applySettingsToForm(s);
      showToast('ok', 'Đã lưu lịch backup.');
    } catch (err: unknown) {
      showToast('err', (err as Error)?.message || 'Lưu lịch thất bại');
    } finally {
      setSaving(false);
    }
  };

  const handleTrigger = async () => {
    setTriggering(true);
    try {
      const r = await adminVpsBackupAPI.triggerRun();
      showToast('ok', r.message);
      await loadAll();
    } catch (err: unknown) {
      showToast('err', (err as Error)?.message || 'Không chạy được backup');
    } finally {
      setTriggering(false);
    }
  };

  const handleDownloadArchive = async (filename: string) => {
    setDownloadingFile(filename);
    try {
      await adminVpsBackupAPI.downloadArchive(filename);
      showToast('ok', `Đang tải ${filename}`);
    } catch (err: unknown) {
      showToast('err', (err as Error)?.message || 'Tải file thất bại');
    } finally {
      setDownloadingFile(null);
    }
  };

  const handleDeleteArchive = async (filename: string) => {
    if (!confirm(`Xóa file backup "${filename}"? Hành động không thể hoàn tác.`)) return;
    setDeletingFile(filename);
    try {
      await adminVpsBackupAPI.deleteArchive(filename);
      showToast('ok', `Đã xóa ${filename}`);
      const a = await adminVpsBackupAPI.listArchives();
      setArchives(a.items);
      setArchiveTotalPretty(a.total_size_pretty);
    } catch (err: unknown) {
      showToast('err', (err as Error)?.message || 'Xóa file thất bại');
    } finally {
      setDeletingFile(null);
    }
  };

  if (loading) {
    return (
      <div className="p-6">
        <p className="text-gray-600">Đang tải…</p>
      </div>
    );
  }

  const backupAvailable = settings?.backup_available ?? false;

  return (
    <div className="p-6 max-w-6xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Backup VPS</h1>
        <p className="text-sm text-gray-600 mt-1">
          Giữ <strong>2 bản backup mới nhất</strong> trên server. Có thể tự động đẩy lên{' '}
          <strong>Google Drive</strong> sau mỗi lần backup. Email gửi admin khi xong. Kết hợp Snapshot
          panel VPS để khôi phục cả máy ảo.
        </p>
      </div>

      {toast && (
        <div
          className={`mb-4 rounded-lg px-4 py-3 text-sm ${
            toast.type === 'ok'
              ? 'bg-green-50 border border-green-200 text-green-800'
              : 'bg-red-50 border border-red-200 text-red-700'
          }`}
        >
          {toast.msg}
        </div>
      )}

      {loadError && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          <p className="font-medium">Không kết nối được API Backup VPS</p>
          <p className="mt-1">{loadError}</p>
          <button
            type="button"
            onClick={() => {
              setLoading(true);
              void loadAll();
            }}
            className="mt-2 underline font-medium"
          >
            Thử lại
          </button>
        </div>
      )}

      {!loadError && !backupAvailable && (
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          Backup script chỉ chạy trên <strong>VPS Linux</strong> (có{' '}
          <code className="text-xs bg-amber-100 px-1 rounded">deploy/backup-vps.sh</code>). Trên máy dev
          bạn vẫn xem được lịch sử nhưng không chạy backup từ đây.
        </div>
      )}

      {settings && (
        <div
          className={`mb-4 rounded-lg border px-4 py-3 text-sm ${
            settings.drive_upload_configured
              ? 'border-green-200 bg-green-50 text-green-900'
              : settings.drive_upload_enabled
                ? 'border-amber-200 bg-amber-50 text-amber-900'
                : 'border-gray-200 bg-gray-50 text-gray-700'
          }`}
        >
          <p className="font-medium mb-1">Google Drive</p>
          {settings.drive_upload_configured ? (
            <p>
              Đã bật — sau mỗi backup thành công file tự upload lên Drive (giữ{' '}
              <strong>{settings.drive_keep_count ?? 5}</strong> bản mới nhất).
              {settings.drive_folder_id ? (
                <>
                  {' '}
                  Folder ID:{' '}
                  <code className="text-xs bg-green-100 px-1 rounded break-all">
                    {settings.drive_folder_id}
                  </code>{' '}
                  —{' '}
                  <a
                    href={`https://drive.google.com/drive/folders/${encodeURIComponent(settings.drive_folder_id)}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-green-800 underline"
                  >
                    mở trên Drive
                  </a>
                  . Nếu upload báo 404: Share folder Editor cho service account trong file JSON.
                </>
              ) : null}
            </p>
          ) : settings.drive_upload_enabled ? (
            <p>
              Đã bật trong <code className="text-xs bg-amber-100 px-1 rounded">.env</code> nhưng thiếu
              cấu hình: kiểm tra <strong>VPS_BACKUP_DRIVE_FOLDER_ID</strong> và file service account JSON,
              rồi restart PM2.
            </p>
          ) : (
            <p>
              Chưa bật. Thêm vào <code className="text-xs bg-gray-100 px-1 rounded">backend/.env</code>:{' '}
              <code className="text-xs">VPS_BACKUP_DRIVE_ENABLED=true</code> và{' '}
              <code className="text-xs">VPS_BACKUP_DRIVE_FOLDER_ID=...</code> (folder Drive share Editor cho
              service account).
            </p>
          )}
        </div>
      )}

      <section className="mb-8 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Lịch backup tự động</h2>

        <label className="flex items-center gap-2 mb-4 cursor-pointer">
          <input
            type="checkbox"
            checked={formEnabled}
            onChange={(e) => setFormEnabled(e.target.checked)}
            className="rounded border-gray-300"
          />
          <span className="text-sm font-medium text-gray-800">Bật lịch backup tự động</span>
        </label>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm text-gray-600 mb-1">Giờ chạy (24h)</label>
            <div className="flex gap-2">
              <input
                type="number"
                min={0}
                max={23}
                value={formHour}
                onChange={(e) => setFormHour(Number(e.target.value))}
                className="w-20 rounded border border-gray-300 px-2 py-1.5 text-sm"
              />
              <span className="self-center text-gray-500">:</span>
              <input
                type="number"
                min={0}
                max={59}
                value={formMinute}
                onChange={(e) => setFormMinute(Number(e.target.value))}
                className="w-20 rounded border border-gray-300 px-2 py-1.5 text-sm"
              />
            </div>
          </div>
          <div className="flex items-end">
            <p className="text-sm text-gray-600 pb-2">
              Sau mỗi lần backup: <strong>giữ 2 file</strong> mới nhất, các bản cũ hơn tự xóa.
            </p>
          </div>
        </div>

        <div className="mb-4">
          <span className="block text-sm text-gray-600 mb-2">Ngày trong tuần</span>
          <div className="flex flex-wrap gap-2">
            {WEEKDAYS.map((d) => (
              <button
                key={d.value}
                type="button"
                onClick={() => toggleDay(d.value)}
                className={`px-3 py-1 rounded-full text-sm border ${
                  formDays.includes(d.value)
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white text-gray-700 border-gray-300'
                }`}
              >
                {d.label}
              </button>
            ))}
          </div>
        </div>

        <label className="flex items-center gap-2 mb-4 cursor-pointer">
          <input
            type="checkbox"
            checked={formIncludeCache}
            onChange={(e) => setFormIncludeCache(e.target.checked)}
            className="rounded border-gray-300"
          />
          <span className="text-sm text-gray-700">Backup cả data bảng cache (file nặng hơn)</span>
        </label>

        {settings?.notify_on_complete && (
          <p className="text-xs text-gray-500 mb-2">
            Email thông báo gửi tới mọi admin có email (cần SMTP trong .env).
          </p>
        )}
        {settings?.last_triggered_at && (
          <p className="text-xs text-gray-500 mb-4">
            Lần chạy theo lịch gần nhất: {formatDt(settings.last_triggered_at)}
          </p>
        )}

        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={handleSaveSchedule}
            disabled={saving}
            className="rounded-lg bg-gray-900 text-white px-4 py-2 text-sm font-medium hover:bg-gray-800 disabled:opacity-50"
          >
            {saving ? 'Đang lưu…' : 'Lưu lịch'}
          </button>
          <button
            type="button"
            onClick={handleTrigger}
            disabled={!backupAvailable || triggering || hasActiveRun}
            className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
          >
            {triggering ? 'Đang xếp hàng…' : hasActiveRun ? 'Backup đang chạy…' : 'Chạy backup ngay'}
          </button>
        </div>

        {settings && (
          <p className="text-xs text-gray-500 mt-3">
            Thư mục: <code className="bg-gray-100 px-1 rounded">{settings.backup_root}</code>
          </p>
        )}
      </section>

      <section className="mb-8 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
          <h2 className="text-lg font-semibold text-gray-900">File backup đã lưu</h2>
          <span className="text-sm text-gray-600">
            {archives.length} file · {archiveTotalPretty}
          </span>
        </div>

        {archives.length === 0 ? (
          <p className="text-sm text-gray-500">Chưa có file backup trên VPS.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b text-left text-gray-600">
                  <th className="py-2 pr-4">Tên file</th>
                  <th className="py-2 pr-4">Dung lượng</th>
                  <th className="py-2 pr-4">Thời gian</th>
                  <th className="py-2">Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {archives.map((a) => (
                  <tr key={a.filename} className="border-b border-gray-100">
                    <td className="py-2 pr-4 font-mono text-xs">{a.filename}</td>
                    <td className="py-2 pr-4">{a.size_pretty}</td>
                    <td className="py-2 pr-4">{formatDt(a.modified_at)}</td>
                    <td className="py-2">
                      <div className="flex flex-wrap gap-3">
                        <button
                          type="button"
                          onClick={() => handleDownloadArchive(a.filename)}
                          disabled={downloadingFile === a.filename}
                          className="text-blue-600 hover:underline text-xs disabled:opacity-50"
                        >
                          {downloadingFile === a.filename ? 'Đang tải…' : 'Tải xuống'}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDeleteArchive(a.filename)}
                          disabled={deletingFile === a.filename}
                          className="text-red-600 hover:underline text-xs disabled:opacity-50"
                        >
                          {deletingFile === a.filename ? 'Đang xóa…' : 'Xóa'}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Nhật ký các đợt backup</h2>

        {runs.length === 0 ? (
          <p className="text-sm text-gray-500">Chưa có lần chạy nào.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b text-left text-gray-600">
                  <th className="py-2 pr-3">#</th>
                  <th className="py-2 pr-3">Trạng thái</th>
                  <th className="py-2 pr-3">Nguồn</th>
                  <th className="py-2 pr-3">File</th>
                  <th className="py-2 pr-3">Drive</th>
                  <th className="py-2 pr-3">Bắt đầu</th>
                  <th className="py-2 pr-3">Kết thúc</th>
                  <th className="py-2">Ghi chú</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id} className="border-b border-gray-100 align-top">
                    <td className="py-2 pr-3">{r.id}</td>
                    <td className="py-2 pr-3">
                      <span className={`inline-block px-2 py-0.5 rounded text-xs ${statusBadge(r.status)}`}>
                        {statusLabel(r.status)}
                      </span>
                    </td>
                    <td className="py-2 pr-3">{r.trigger === 'scheduled' ? 'Lịch' : 'Thủ công'}</td>
                    <td className="py-2 pr-3">
                      {r.archive_filename ? (
                        <span>
                          <span className="font-mono text-xs block">{r.archive_filename}</span>
                          {r.archive_size_pretty && (
                            <span className="text-xs text-gray-500">{r.archive_size_pretty}</span>
                          )}
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="py-2 pr-3 text-xs">
                      {r.drive_upload_status === 'success' && r.drive_web_link ? (
                        <a
                          href={r.drive_web_link}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 hover:underline"
                        >
                          Mở Drive
                        </a>
                      ) : r.drive_upload_status === 'failed' ? (
                        <span className="text-red-600 block max-w-xs">
                          <span className="font-medium">{driveStatusLabel(r.drive_upload_status)}</span>
                          {r.drive_upload_error ? (
                            <span className="block text-xs mt-0.5 break-words">{r.drive_upload_error}</span>
                          ) : null}
                        </span>
                      ) : (
                        driveStatusLabel(r.drive_upload_status)
                      )}
                    </td>
                    <td className="py-2 pr-3">{formatDt(r.started_at)}</td>
                    <td className="py-2 pr-3">{formatDt(r.finished_at)}</td>
                    <td className="py-2 text-xs text-red-600 max-w-xs break-words">{r.error_message || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
