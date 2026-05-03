'use client';

import { useState, useEffect } from 'react';
import Image from 'next/image';
import { Product } from '@/types/api';
import { apiClient } from '@/lib/api-client';
import type { ProductReviewItem } from '@/types/api';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { formatPrice } from '@/lib/utils';
import { getOptimizedImage } from '@/lib/image-utils';
import ProductReviewFormModal from '../ProductReviewFormModal/ProductReviewFormModal';
import { useToast } from '@/components/ToastProvider';
import VerifiedPurchaserBadge from '../VerifiedPurchaserBadge';
import { reviewShowsVerifiedPurchaserBadge } from '@/lib/product-qa-verified-display';

interface ProductReviewSectionProps {
  product: Product;
  modalOnly?: boolean;
  modalOpen?: boolean;
  onModalClose?: () => void;
  onModalOpen?: () => void;
}

function formatDate(s: string | null | undefined) {
  if (!s) return '';
  try {
    return new Date(s).toLocaleDateString('vi-VN', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    });
  } catch {
    return s;
  }
}

function StarRating({ star }: { star: number }) {
  return (
    <span className="flex text-amber-400" aria-label={`${star} sao`}>
      {Array.from({ length: 5 }, (_, i) => (
        <span key={i}>{i < star ? '★' : '☆'}</span>
      ))}
    </span>
  );
}

export default function ProductReviewSection({
  product,
  modalOnly,
  modalOpen: modalOpenProp,
  onModalClose,
  onModalOpen,
}: ProductReviewSectionProps) {
  const { isAuthenticated } = useAuth();
  const { pushToast } = useToast();
  const [reviews, setReviews] = useState<ProductReviewItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [togglingUsefulId, setTogglingUsefulId] = useState<number | null>(null);
  const [reviewFormOpen, setReviewFormOpen] = useState(false);
  const [canReview, setCanReview] = useState(false);
  const [hasReviewed, setHasReviewed] = useState(false);

  useEffect(() => {
    if (!isAuthenticated) {
      setCanReview(false);
      setHasReviewed(false);
      return;
    }
    Promise.all([
      apiClient.canReviewProduct(product.id).then((r) => r.can_review ?? false),
      apiClient.getUserReviewedProductIds([product.id]).then((r) => (r.product_ids || []).includes(product.id)),
    ])
      .then(([can, reviewed]) => {
        setCanReview(can);
        setHasReviewed(reviewed);
      })
      .catch(() => {
        setCanReview(false);
        setHasReviewed(false);
      });
  }, [isAuthenticated, product.id]);
  const modalOpen = modalOnly ? (modalOpenProp ?? false) : false;
  const setModalOpen = modalOnly ? () => onModalClose?.() : () => {};

  useEffect(() => {
    let cancelled = false;
    apiClient
      .getProductReviews(product.id)
      .then((list) => {
        if (!cancelled) setReviews(Array.isArray(list) ? list : []);
      })
      .catch(() => {
        if (!cancelled) setReviews([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [product.id]);

  useEffect(() => {
    if (!modalOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onModalClose?.();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [modalOpen, onModalClose]);

  const handleToggleUseful = async (reviewId: number) => {
    if (!isAuthenticated) {
      pushToast({ title: 'Vui lòng đăng nhập để bình chọn', variant: 'info', durationMs: 2500 });
      return;
    }
    setTogglingUsefulId(reviewId);
    try {
      const res = await apiClient.toggleReviewUseful(reviewId);
      setReviews((prev) =>
        prev.map((r) =>
          r.id === reviewId ? { ...r, useful: res.useful, user_has_voted: res.user_has_voted } : r
        )
      );
    } catch {
      // ignore
    } finally {
      setTogglingUsefulId(null);
    }
  };

  const productInfoBlock = (
    <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg mb-4">
      <div className="shrink-0 w-14 h-14 rounded-lg overflow-hidden bg-white border border-gray-200 relative">
        <Image
          src={getOptimizedImage(product.main_image || product.images?.[0], { fallbackStrategy: 'local' })}
          alt={product.name}
          fill
          sizes="56px"
          className="object-cover"
        />
      </div>
      <div className="min-w-0 flex-1">
        <p className="font-medium text-gray-900 truncate">{product.name}</p>
        <p className="text-[#ea580c] font-semibold">{formatPrice(product.price)}</p>
      </div>
    </div>
  );

  const renderReviewList = (list: ProductReviewItem[]) => (
    <div className="space-y-4">
      {list.map((r) => (
        <div key={r.id} className="bg-gray-50 rounded-lg p-4 space-y-2">
            <div className="flex items-start justify-between gap-2">
              <div>
              <span className="inline-flex flex-wrap items-center gap-x-1.5 gap-y-0">
                <span className="font-medium text-gray-900">{r.user_name || 'Khách'}</span>
                {reviewShowsVerifiedPurchaserBadge(r) && <VerifiedPurchaserBadge compact />}
              </span>
              <span className="block text-xs text-gray-500 mt-0.5">
                {formatDate(r.display_created_at ?? r.created_at)}
              </span>
              </div>
            <StarRating star={r.star || 5} />
          </div>
          {r.title && <p className="text-sm font-medium text-amber-600">{r.title}</p>}
          <p className="text-sm text-gray-700">{r.content}</p>
          {r.reply_content && (
            <div className="pl-4 border-l-2 border-orange-200 text-sm text-gray-600">
              <p className="font-medium text-gray-800">
                {r.reply_name || '188.COM.VN'} phản hồi: {formatDate(r.display_reply_at ?? r.reply_at)}
              </p>
              <p>{r.reply_content}</p>
            </div>
          )}
          <div className="flex items-center gap-2 flex-wrap mt-1">
            {r.useful > 0 && (
              <span className="text-xs text-gray-500">{r.useful} người thấy đánh giá này hữu ích</span>
            )}
            <button
              type="button"
              onClick={() => handleToggleUseful(r.id)}
              disabled={togglingUsefulId === r.id}
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-sm font-medium transition ${
                r.user_has_voted ? 'bg-[#dc2626] text-white hover:bg-[#b91c1c]' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              } disabled:opacity-50`}
              title="Hữu ích"
            >
              <span className="w-4 h-4 inline-flex items-center justify-center shrink-0" aria-hidden>
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4">
                  <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 11H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h3z" />
                </svg>
              </span>
              Hữu ích
            </button>
          </div>
        </div>
      ))}
    </div>
  );

  if (!modalOnly) return null;

  return (
    <>
      {modalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50"
          onClick={() => onModalClose?.()}
          role="dialog"
          aria-modal="true"
          aria-labelledby="reviews-modal-title"
        >
          <div
            className="bg-white rounded-xl shadow-xl max-w-2xl w-full max-h-[90vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between shrink-0 px-4 py-3 border-b border-gray-200">
              <h2 id="reviews-modal-title" className="font-semibold text-lg text-gray-900">
                Đánh giá sản phẩm
              </h2>
              <div className="flex items-center gap-2">
                {!hasReviewed && (
                  <button
                    type="button"
                    onClick={() => setReviewFormOpen(true)}
                    className="px-3 py-1.5 text-sm font-medium text-[#ea580c] border border-[#ea580c] rounded-lg hover:bg-orange-50"
                  >
                    Viết đánh giá
                  </button>
                )}
                <button
                type="button"
                onClick={() => onModalClose?.()}
                className="p-2 rounded-lg text-gray-500 hover:bg-gray-100 hover:text-gray-700 transition"
                aria-label="Đóng"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
              </div>
            </div>
            <div className="overflow-y-auto flex-1 p-4">
              {productInfoBlock}
              {loading ? (
                <div className="py-8 text-center text-gray-500">Đang tải đánh giá...</div>
              ) : reviews.length === 0 ? (
                <div className="bg-gray-50 rounded-lg p-4 text-gray-600 text-sm">
                  Chưa có đánh giá nào.
                </div>
              ) : (
                renderReviewList(reviews)
              )}
            </div>
          </div>
        </div>
      )}

      <ProductReviewFormModal
        product={product}
        isOpen={reviewFormOpen}
        onClose={() => setReviewFormOpen(false)}
        onSuccess={() => {
          setHasReviewed(true);
          apiClient.getProductReviews(product.id).then((list) => {
            setReviews(Array.isArray(list) ? list : []);
          }).catch(() => {});
        }}
        purchaseRequired={!canReview}
      />
    </>
  );
}
