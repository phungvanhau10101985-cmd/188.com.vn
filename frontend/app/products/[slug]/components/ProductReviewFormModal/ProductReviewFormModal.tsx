'use client';

import { useState, useEffect } from 'react';
import { Product } from '@/types/api';
import { apiClient } from '@/lib/api-client';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { useToast } from '@/components/ToastProvider';

interface ProductReviewFormModalProps {
  product: Product;
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
  /** Hiển thị thông báo cần mua trước thay vì form */
  purchaseRequired?: boolean;
}

const STAR_LABELS: Record<number, string> = {
  1: 'Rất không hài lòng',
  2: 'Không hài lòng',
  3: 'Tạm được',
  4: 'Hài lòng',
  5: 'Cực hài lòng',
};

export default function ProductReviewFormModal({
  product,
  isOpen,
  onClose,
  onSuccess,
  purchaseRequired = false,
}: ProductReviewFormModalProps) {
  const { isAuthenticated } = useAuth();
  const { pushToast } = useToast();
  const [star, setStar] = useState(5);
  const [content, setContent] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOpen, onClose]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = content.trim();
    if (!text) {
      pushToast({ title: 'Vui lòng nhập nội dung đánh giá', variant: 'info', durationMs: 2000 });
      return;
    }
    if (!isAuthenticated) {
      pushToast({ title: 'Vui lòng đăng nhập để gửi đánh giá', variant: 'info', durationMs: 2500 });
      return;
    }
    setSubmitting(true);
    try {
      await apiClient.submitProductReview({
        product_id: product.id,
        star,
        title: STAR_LABELS[star] || '',
        content: text,
      });
      setContent('');
      setStar(5);
      onSuccess?.();
      onClose();
      pushToast({ title: 'Cảm ơn bạn đã đánh giá!', variant: 'success', durationMs: 2500 });
    } catch (err) {
      pushToast({ title: 'Gửi đánh giá thất bại', description: (err as Error)?.message || 'Vui lòng thử lại', variant: 'error', durationMs: 3000 });
    } finally {
      setSubmitting(false);
    }
  };

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) onClose();
  };

  if (!isOpen) return null;

  if (purchaseRequired) {
    return (
      <div
        className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50"
        onClick={handleBackdropClick}
        role="dialog"
        aria-modal="true"
      >
        <div
          className="bg-white rounded-xl shadow-xl max-w-md w-full p-6"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-lg text-gray-900">Đánh giá sản phẩm</h2>
            <button
              type="button"
              onClick={onClose}
              className="p-2 rounded-lg text-gray-500 hover:bg-gray-100"
              aria-label="Đóng"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <p className="text-gray-600 text-sm">
            Khách hàng cần mua sản phẩm này trước mới đủ điều kiện để đánh giá sản phẩm.
          </p>
          <button
            type="button"
            onClick={onClose}
            className="mt-4 w-full py-2 bg-gray-200 text-gray-800 rounded-lg font-medium hover:bg-gray-300"
          >
            Đóng
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50"
      onClick={handleBackdropClick}
      role="dialog"
      aria-modal="true"
      aria-labelledby="review-form-title"
    >
      <div
        className="bg-white rounded-xl shadow-xl max-w-md w-full max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
          <h2 id="review-form-title" className="font-semibold text-lg text-gray-900">
            Đánh giá sản phẩm
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-lg text-gray-500 hover:bg-gray-100 hover:text-gray-700 transition"
            aria-label="Đóng"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          {/* Đánh giá sao */}
          <div>
            <p className="text-sm font-medium text-gray-700 mb-2">
              {STAR_LABELS[star]} • {star} sao
            </p>
            <div className="flex items-center gap-1">
              {[1, 2, 3, 4, 5].map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setStar(s)}
                  className="text-3xl text-amber-400 hover:scale-110 transition transform focus:outline-none"
                  title={STAR_LABELS[s]}
                >
                  {s <= star ? '★' : '☆'}
                </button>
              ))}
            </div>
          </div>

          {/* Nội dung đánh giá */}
          <div>
            <label htmlFor="review-content" className="block text-sm font-medium text-gray-700 mb-1">
              Nội dung đánh giá
            </label>
            <textarea
              id="review-content"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="Hãy chia sẻ những điều bạn thích về sản phẩm này nhé"
              rows={4}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm resize-none focus:ring-2 focus:ring-[#ea580c] focus:border-[#ea580c]"
              disabled={!isAuthenticated}
            />
          </div>

          {/* Chọn ảnh (placeholder - chưa implement upload) */}
          <div>
            <p className="text-sm font-medium text-gray-700 mb-2">Chọn video hoặc ảnh (tùy chọn)</p>
            <div className="flex gap-2 text-gray-400 text-sm">
              <span className="px-3 py-2 border border-dashed border-gray-300 rounded-lg">📹 Thêm video</span>
              <span className="px-3 py-2 border border-dashed border-gray-300 rounded-lg">📷 Thêm ảnh</span>
            </div>
          </div>

          {/* Nút gửi */}
          <button
            type="submit"
            disabled={submitting || !content.trim()}
            className="w-full py-3 bg-[#ea580c] text-white font-medium rounded-lg hover:bg-[#c2410c] disabled:opacity-50 disabled:cursor-not-allowed transition"
          >
            {submitting ? 'Đang gửi...' : 'Gửi'}
          </button>

          {/* Lưu ý */}
          <p className="text-xs text-red-600">
            Chúng tôi sẽ ngừng hợp tác với những nhà cung cấp sản phẩm kém chất lượng, khách hàng vui lòng đánh giá khách quan.
          </p>
        </form>
      </div>
    </div>
  );
}
