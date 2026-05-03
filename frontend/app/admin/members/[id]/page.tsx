'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { useParams } from 'next/navigation';
import { adminMemberAPI, type AdminMember } from '@/lib/admin-api';

function formatDateTime(s: string | null | undefined) {
  if (!s) return '—';
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  return (
    d.toLocaleDateString('vi-VN') +
    ' ' +
    d.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  );
}

function formatBirthDate(s: string | null | undefined) {
  if (!s) return '—';
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) {
    const [y, m, d] = s.slice(0, 10).split('-');
    return `${d}/${m}/${y}`;
  }
  const dt = new Date(s);
  return Number.isNaN(dt.getTime()) ? s : dt.toLocaleDateString('vi-VN');
}

function genderLabel(g: string | null | undefined) {
  if (!g) return '—';
  const m: Record<string, string> = { male: 'Nam', female: 'Nữ', other: 'Khác' };
  return m[g.toLowerCase()] || g;
}

export default function AdminMemberDetailPage() {
  const params = useParams();
  const id = Number(params?.id);
  const [member, setMember] = useState<AdminMember | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [toast, setToast] = useState<{ type: 'ok' | 'err'; msg: string } | null>(null);
  const [updating, setUpdating] = useState(false);

  const showToast = (type: 'ok' | 'err', msg: string) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 3000);
  };

  const load = useCallback(async () => {
    if (!Number.isFinite(id) || id < 1) {
      setNotFound(true);
      setLoading(false);
      return;
    }
    setLoading(true);
    setNotFound(false);
    try {
      const u = await adminMemberAPI.getMember(id);
      setMember(u);
    } catch {
      setMember(null);
      setNotFound(true);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const handleToggleActive = async () => {
    if (!member) return;
    setUpdating(true);
    try {
      const next = await adminMemberAPI.updateMember(member.id, { is_active: !member.is_active });
      setMember(next);
      showToast('ok', next.is_active ? 'Đã bật kích hoạt' : 'Đã tắt kích hoạt');
    } catch (err: unknown) {
      showToast('err', (err as Error)?.message || 'Lỗi cập nhật');
    } finally {
      setUpdating(false);
    }
  };

  return (
      <div className="p-6 max-w-3xl">
        {toast && (
          <div
            className={`fixed top-4 right-4 z-50 px-4 py-2 rounded-lg shadow-lg ${
              toast.type === 'ok' ? 'bg-green-600 text-white' : 'bg-red-600 text-white'
            }`}
          >
            {toast.msg}
          </div>
        )}

        <div className="mb-6">
          <Link
            href="/admin/members"
            className="text-sm font-medium text-slate-600 hover:text-slate-900"
          >
            ← Danh sách thành viên
          </Link>
        </div>

        {loading ? (
          <div className="text-gray-500">Đang tải...</div>
        ) : notFound || !member ? (
          <div className="rounded-xl border border-gray-200 bg-white p-8 text-center text-gray-600">
            Không tìm thấy thành viên.
          </div>
        ) : (
          <div className="bg-white rounded-xl shadow border border-gray-100 overflow-hidden">
            <div className="p-6 border-b border-gray-100 flex flex-wrap items-start justify-between gap-4">
              <div>
                <h1 className="text-2xl font-bold text-gray-900">
                  {member.full_name?.trim() || `Thành viên #${member.id}`}
                </h1>
                <p className="text-gray-500 text-sm mt-1 font-mono">ID: {member.id}</p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={`inline-flex px-2.5 py-1 rounded text-xs font-medium ${
                    member.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                  }`}
                >
                  {member.is_active ? 'Đang hoạt động' : 'Đã khóa'}
                </span>
                <span
                  className={`inline-flex px-2.5 py-1 rounded text-xs font-medium ${
                    member.is_verified ? 'bg-blue-100 text-blue-800' : 'bg-gray-100 text-gray-700'
                  }`}
                >
                  {member.is_verified ? 'Đã xác thực' : 'Chưa xác thực'}
                </span>
                <button
                  type="button"
                  onClick={handleToggleActive}
                  disabled={updating}
                  className={`px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50 ${
                    member.is_active
                      ? 'bg-amber-100 text-amber-900 hover:bg-amber-200'
                      : 'bg-green-100 text-green-900 hover:bg-green-200'
                  }`}
                >
                  {updating ? '...' : member.is_active ? 'Khóa tài khoản' : 'Mở khóa'}
                </button>
              </div>
            </div>

            <div className="p-6 grid gap-6 sm:grid-cols-2">
              {member.avatar ? (
                <div className="sm:col-span-2 flex items-center gap-4">
                  <div className="relative h-20 w-20 rounded-full overflow-hidden bg-gray-100 border border-gray-200">
                    <Image
                      src={member.avatar}
                      alt=""
                      fill
                      className="object-cover"
                      unoptimized
                    />
                  </div>
                  <div>
                    <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Ảnh đại diện</p>
                    <p className="text-sm text-gray-700 break-all">{member.avatar}</p>
                  </div>
                </div>
              ) : null}

              <DetailRow label="Email" value={member.email || '—'} mono />
              <DetailRow label="Số điện thoại" value={member.phone || '—'} mono />
              <DetailRow label="Họ và tên" value={member.full_name || '—'} />
              <DetailRow label="Ngày sinh" value={formatBirthDate(member.date_of_birth)} />
              <DetailRow label="Giới tính" value={genderLabel(member.gender)} />
              <DetailRow label="Thời gian tạo tài khoản" value={formatDateTime(member.created_at)} />
              <DetailRow label="Cập nhật lần cuối" value={formatDateTime(member.updated_at)} />
              <DetailRow label="Đăng nhập gần nhất" value={formatDateTime(member.last_login)} />
              <div className="sm:col-span-2">
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Địa chỉ</p>
                <p className="text-gray-900 whitespace-pre-wrap">{member.address?.trim() || '—'}</p>
              </div>
            </div>
          </div>
        )}
      </div>
  );
}

function DetailRow({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">{label}</p>
      <p className={`text-gray-900 ${mono ? 'font-mono text-sm' : ''}`}>{value}</p>
    </div>
  );
}
