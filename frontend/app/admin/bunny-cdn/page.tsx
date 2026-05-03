'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  adminBunnyCdnAPI,
  type BunnyCdnStatus,
  type BunnyCdnUploadResult,
} from '@/lib/admin-api';

export default function AdminBunnyCdnPage() {
  const [status, setStatus] = useState<BunnyCdnStatus | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(true);
  const [subfolder, setSubfolder] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [lastResult, setLastResult] = useState<BunnyCdnUploadResult | null>(null);
  const [toast, setToast] = useState<{ type: 'ok' | 'err'; msg: string } | null>(null);

  const showToast = (type: 'ok' | 'err', msg: string) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 4500);
  };

  const loadStatus = useCallback(async () => {
    setLoadingStatus(true);
    try {
      const s = await adminBunnyCdnAPI.getStatus();
      setStatus(s);
    } catch (e) {
      showToast('err', (e as Error)?.message || 'Không tải được trạng thái Bunny');
    } finally {
      setLoadingStatus(false);
    }
  }, []);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      showToast('err', 'Chọn một file ảnh');
      return;
    }
    setUploading(true);
    setLastResult(null);
    try {
      const r = await adminBunnyCdnAPI.upload(file, subfolder);
      setLastResult(r);
      showToast('ok', 'Đã đăng ảnh lên Bunny Storage.');
      setFile(null);
    } catch (err) {
      showToast('err', (err as Error)?.message || 'Upload thất bại');
    } finally {
      setUploading(false);
    }
  };

  const copyUrl = async () => {
    if (!lastResult?.public_url) return;
    try {
      await navigator.clipboard.writeText(lastResult.public_url);
      showToast('ok', 'Đã copy URL');
    } catch {
      showToast('err', 'Không copy được — chọn và copy thủ công');
    }
  };

  return (
      <div className="p-6 max-w-2xl">
        <h1 className="text-xl font-bold text-gray-900 mb-2">Đăng ảnh lên Bunny CDN</h1>
        <p className="text-sm text-gray-600 mb-4">
          Upload ảnh lên Storage Zone — Pull Zone public ({status?.cdn_public_base || '…'}). Đường dẫn object:
          prefix trong .env (<code className="text-xs bg-gray-100 px-1 rounded">BUNNY_UPLOAD_PATH_PREFIX</code>) + thư mục con (tuỳ chọn) + ngày + tên file duy nhất.
        </p>

        {loadingStatus ? (
          <p className="text-gray-500 text-sm mb-6">Đang kiểm tra cấu hình…</p>
        ) : status?.configured ? (
          <div className="mb-6 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-900">
            Đã cấu hình Bunny. CDN: <strong>{status.cdn_public_base}</strong>
            {status.upload_path_prefix ? (
              <>
                {' '}
                — prefix upload: <strong>{status.upload_path_prefix}</strong>
              </>
            ) : null}
          </div>
        ) : (
          <div className="mb-6 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950">
            Backend chưa đủ biến môi trường:{' '}
            <code className="text-xs">BUNNY_STORAGE_ZONE_NAME</code>,{' '}
            <code className="text-xs">BUNNY_STORAGE_ACCESS_KEY</code>,{' '}
            <code className="text-xs">BUNNY_CDN_PUBLIC_BASE</code>. Thêm vào{' '}
            <code className="text-xs">backend/.env</code> rồi khởi động lại API.
          </div>
        )}

        <form onSubmit={(e) => void handleSubmit(e)} className="bg-white rounded-lg border border-gray-200 shadow-sm p-5 space-y-4">
          <label className="block">
            <span className="text-sm font-medium text-gray-700">Thư mục con (tuỳ chọn)</span>
            <input
              type="text"
              value={subfolder}
              onChange={(e) => setSubfolder(e.target.value)}
              placeholder="vd: banners, promo/tet — chỉ chữ thường, số, / - _"
              className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
              disabled={!status?.configured || uploading}
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-gray-700">Ảnh (JPG, PNG, GIF, WEBP — tối đa 15MB)</span>
            <input
              type="file"
              accept="image/jpeg,image/png,image/gif,image/webp"
              className="mt-1 w-full text-sm"
              disabled={!status?.configured || uploading}
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
          <button
            type="submit"
            disabled={!status?.configured || uploading || !file}
            className="px-4 py-2 rounded-lg bg-[#ea580c] text-white text-sm font-semibold hover:bg-orange-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {uploading ? 'Đang tải lên…' : 'Đăng lên Bunny'}
          </button>
        </form>

        {lastResult && (
          <div className="mt-6 rounded-lg border border-gray-200 bg-gray-50 p-4 space-y-2">
            <p className="text-sm font-semibold text-gray-900">URL public</p>
            <div className="flex flex-wrap gap-2 items-center">
              <a
                href={lastResult.public_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-[#ea580c] break-all hover:underline"
              >
                {lastResult.public_url}
              </a>
              <button
                type="button"
                onClick={() => void copyUrl()}
                className="text-xs px-2 py-1 rounded border border-gray-300 bg-white hover:bg-gray-100"
              >
                Copy URL
              </button>
            </div>
            <p className="text-xs text-gray-600">
              Đường dẫn trong zone: <code className="bg-white px-1 rounded">{lastResult.remote_path}</code> —{' '}
              {(lastResult.bytes / 1024).toFixed(1)} KB
            </p>
          </div>
        )}

        {toast && (
          <div
            className={`fixed bottom-6 right-6 px-4 py-2 rounded-lg shadow text-sm z-[100] ${
              toast.type === 'ok' ? 'bg-green-700 text-white' : 'bg-red-600 text-white'
            }`}
          >
            {toast.msg}
          </div>
        )}
      </div>
  );
}
