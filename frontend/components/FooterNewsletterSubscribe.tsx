'use client';

import { FormEvent, useEffect, useState } from 'react';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { apiClient } from '@/lib/api-client';
import { useToast } from '@/components/ToastProvider';

export default function FooterNewsletterSubscribe() {
  const { user, isAuthenticated } = useAuth();
  const { pushToast } = useToast();
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [banner, setBanner] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);

  useEffect(() => {
    if (isAuthenticated && user?.email) {
      setEmail((prev) => prev || user.email || '');
    }
  }, [isAuthenticated, user?.email]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const trimmed = email.trim();
    if (!trimmed) {
      setBanner({ type: 'err', text: 'Vui lòng nhập email.' });
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed)) {
      setBanner({ type: 'err', text: 'Email không hợp lệ.' });
      return;
    }

    setSubmitting(true);
    setBanner(null);
    try {
      const res = await apiClient.subscribeNewsletter(trimmed);
      setBanner({ type: 'ok', text: res.message });
      pushToast({ title: 'Đăng ký nhận tin', description: res.message, variant: 'success' });
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Không gửi được. Vui lòng thử lại.';
      setBanner({ type: 'err', text: msg });
      pushToast({ title: 'Không đăng ký được', description: msg, variant: 'error' });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-2">
      <h5 className="text-xs font-semibold uppercase tracking-wider text-gray-900">Đăng ký nhận tin</h5>
      <p className="text-xs text-gray-600">Nhận ưu đãi và tin sale qua email — không spam.</p>
      <form onSubmit={handleSubmit} className="space-y-2" noValidate>
        <div className="flex gap-2">
          <input
            type="email"
            name="newsletter-email"
            autoComplete="email"
            placeholder="Email của bạn"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={submitting}
            aria-label="Email đăng ký nhận tin"
            className="flex-1 px-3 py-2.5 bg-gray-50 border border-gray-200 rounded-xl text-sm text-gray-900 placeholder-gray-600 focus:outline-none focus:border-orange-500 focus:ring-1 focus:ring-orange-500 disabled:opacity-60"
          />
          <button
            type="submit"
            disabled={submitting}
            className="bg-[#ea580c] text-white hover:bg-orange-600 min-h-[44px] min-w-[72px] px-4 py-2.5 rounded-xl text-sm font-medium transition-colors shadow-sm disabled:opacity-60"
          >
            {submitting ? '…' : 'Gửi'}
          </button>
        </div>
        {banner && (
          <div
            role="status"
            className={
              banner.type === 'ok'
                ? 'rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800'
                : 'rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700'
            }
          >
            {banner.text}
          </div>
        )}
      </form>
    </div>
  );
}
