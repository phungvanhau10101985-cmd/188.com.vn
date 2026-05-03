'use client';

import { useState } from 'react';
import { apiClient } from '@/lib/api-client';

export default function AdminNotificationsPage() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setResult(null);
      setError(null);
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.importNotifications(file);
      setResult(res);
    } catch (err: any) {
      setError(err.message || 'Có lỗi xảy ra khi import');
    } finally {
      setLoading(false);
    }
  };

  return (
      <div className="container mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold mb-6">Quản lý Thông báo</h1>
        
        <div className="bg-white p-6 rounded-lg shadow-md max-w-2xl mx-auto">
          <h2 className="text-lg font-semibold mb-4">Import Thông báo từ Excel/CSV</h2>
          
          <div className="mb-4">
            <p className="text-sm text-gray-600 mb-2">Định dạng file yêu cầu:</p>
            <ul className="list-disc list-inside text-sm text-gray-600 bg-gray-50 p-3 rounded">
              <li>Cột 1: <strong>phone</strong> (Số điện thoại)</li>
              <li>Cột 2: <strong>title</strong> (Tiêu đề)</li>
              <li>Cột 3: <strong>content</strong> (Nội dung)</li>
              <li>Cột 4: <strong>time_will_send</strong> (Thời gian gửi: dd/mm/yyyy HH:MM:SS)</li>
            </ul>
            <p className="text-xs text-gray-500 mt-2 italic">Lưu ý: Thông báo sẽ tự động xóa sau 15 ngày kể từ ngày gửi.</p>
          </div>

          <div className="flex items-center gap-4 mb-4">
            <input 
              type="file" 
              accept=".xlsx, .xls, .csv"
              onChange={handleFileChange}
              className="block w-full text-sm text-gray-500
                file:mr-4 file:py-2 file:px-4
                file:rounded-full file:border-0
                file:text-sm file:font-semibold
                file:bg-blue-50 file:text-blue-700
                hover:file:bg-blue-100"
            />
          </div>

          <button
            onClick={handleUpload}
            disabled={!file || loading}
            className={`w-full py-2 px-4 rounded-md text-white font-medium transition-colors ${
              !file || loading 
                ? 'bg-gray-400 cursor-not-allowed' 
                : 'bg-blue-600 hover:bg-blue-700'
            }`}
          >
            {loading ? 'Đang xử lý...' : 'Upload và Import'}
          </button>

          {error && (
            <div className="mt-4 p-3 bg-red-50 text-red-700 rounded-md border border-red-200">
              {error}
            </div>
          )}

          {result && (
            <div className="mt-6 border-t pt-4">
              <h3 className="font-semibold mb-2">Kết quả Import:</h3>
              <div className="grid grid-cols-3 gap-4 mb-4 text-center">
                <div className="bg-gray-100 p-2 rounded">
                  <div className="text-xs text-gray-500">Tổng số dòng</div>
                  <div className="font-bold">{result.total_processed}</div>
                </div>
                <div className="bg-green-100 p-2 rounded">
                  <div className="text-xs text-green-600">Thành công</div>
                  <div className="font-bold text-green-700">{result.success_count}</div>
                </div>
                <div className="bg-red-100 p-2 rounded">
                  <div className="text-xs text-red-600">Lỗi</div>
                  <div className="font-bold text-red-700">{result.error_count}</div>
                </div>
              </div>

              {result.errors && result.errors.length > 0 && (
                <div className="bg-red-50 p-3 rounded-md border border-red-200 max-h-60 overflow-y-auto">
                  <p className="font-medium text-red-800 mb-2">Chi tiết lỗi:</p>
                  <ul className="list-disc list-inside text-sm text-red-700 space-y-1">
                    {result.errors.map((err: string, idx: number) => (
                      <li key={idx}>{err}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
  );
}
