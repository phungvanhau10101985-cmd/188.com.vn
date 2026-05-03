'use client';

import { useState, useEffect } from 'react';
import Image from 'next/image';
import { apiClient } from '@/lib/api-client';
import { getOptimizedImage } from '@/lib/image-utils';
import type { ProductReviewAdmin } from '@/lib/admin-api';
import type { Product, ProductReviewItem } from '@/types/api';
import VerifiedPurchaserBadge from '@/app/products/[slug]/components/VerifiedPurchaserBadge';

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
    <span className="flex text-amber-400 text-sm" aria-label={`${star} sao`}>
      {Array.from({ length: 5 }, (_, i) => (
        <span key={i}>{i < star ? '★' : '☆'}</span>
      ))}
    </span>
  );
}

interface ViewReviewModalProps {
  productSlug: string;
  selectedReview: ProductReviewAdmin;
  onClose: () => void;
}

export default function ViewReviewModal({ productSlug, selectedReview, onClose }: ViewReviewModalProps) {
  const [product, setProduct] = useState<Product | null>(null);
  const [reviews, setReviews] = useState<ProductReviewItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const prod = await apiClient.getProductBySlug(productSlug);
        if (cancelled) return;
        setProduct(prod);
        const list = await apiClient.getProductReviews(prod.id);
        if (cancelled) return;
        setReviews(Array.isArray(list) ? list : []);
      } catch {
        if (!cancelled) {
          setProduct(null);
          setReviews([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [productSlug]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  const orderedReviews: ProductReviewItem[] = [];
  const selectedInList = reviews.find((r) => r.id === selectedReview.id);
  if (selectedInList) {
    orderedReviews.push(selectedInList);
  }
  reviews.forEach((r) => {
    if (r.id !== selectedReview.id) orderedReviews.push(r);
  });
  if (!selectedInList && selectedReview) {
    orderedReviews.unshift({
      id: selectedReview.id,
      user_name: selectedReview.user_name,
      star: selectedReview.star,
      title: selectedReview.title,
      content: selectedReview.content,
      group: selectedReview.group,
      product_id: selectedReview.product_id,
      useful: selectedReview.useful ?? 0,
      user_id: selectedReview.user_id,
      display_created_at: selectedReview.created_at ?? undefined,
      reply_name: selectedReview.reply_name,
      reply_content: selectedReview.reply_content,
      reply_at: selectedReview.reply_at ?? undefined,
      images: selectedReview.images,
    });
  }

  const renderReview = (r: ProductReviewItem, isSelected: boolean) => (
    <div
      key={r.id}
      className={`rounded-lg p-4 space-y-2 ${isSelected ? 'bg-amber-50 border-2 border-amber-300' : 'bg-gray-50'}`}
    >
      {isSelected && (
        <span className="inline-block px-2 py-0.5 text-xs font-medium bg-amber-500 text-white rounded mb-1">
          Đánh giá đang xem
        </span>
      )}
      <div className="flex items-start justify-between gap-2">
        <div>
          <span className="inline-flex flex-wrap items-center gap-x-1.5 gap-y-0">
            <span className="font-medium text-gray-900">{r.user_name || 'Khách'}</span>
            {r.user_id != null && <VerifiedPurchaserBadge compact />}
          </span>
          <span className="ml-0 block mt-0.5 text-xs text-gray-500">
            {formatDate(r.display_created_at ?? r.created_at)}
          </span>
        </div>
        <StarRating star={r.star || 5} />
      </div>
      {r.title && <p className="text-sm font-medium text-amber-600">{r.title}</p>}
      <p className="text-sm text-gray-700">{r.content}</p>
      {r.images && r.images.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1">
          {r.images.slice(0, 5).map((url, i) => (
            <div key={i} className="relative w-16 h-16 rounded border border-gray-200 overflow-hidden">
              <Image
                src={getOptimizedImage(url, { width: 80, height: 80 })}
                alt=""
                fill
                sizes="64px"
                className="object-cover"
              />
            </div>
          ))}
        </div>
      )}
      {r.reply_content && (
        <div className="pl-4 border-l-2 border-orange-200 text-sm text-gray-600 mt-2">
          <p className="font-medium text-gray-800">
            {r.reply_name || '188.COM.VN'} phản hồi: {formatDate(r.display_reply_at ?? r.reply_at)}
          </p>
          <p>{r.reply_content}</p>
        </div>
      )}
      {r.useful > 0 && (
        <span className="text-xs text-gray-500">{r.useful} người thấy đánh giá này hữu ích</span>
      )}
    </div>
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="view-review-modal-title"
    >
      <div
        className="bg-white rounded-xl shadow-xl max-w-2xl w-full max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between shrink-0 px-4 py-3 border-b border-gray-200">
          <h2 id="view-review-modal-title" className="font-semibold text-lg text-gray-900">
            Xem đánh giá
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

        <div className="overflow-y-auto flex-1 p-4 space-y-4">
          {loading ? (
            <div className="py-8 text-center text-gray-500">Đang tải...</div>
          ) : (
            <>
              {product && (
                <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
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
                    <a
                      href={`/products/${productSlug}#reviews`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm text-blue-600 hover:underline"
                    >
                      Xem trên trang sản phẩm →
                    </a>
                  </div>
                </div>
              )}

              <div>
                <h3 className="text-sm font-medium text-gray-700 mb-2">Đánh giá đang xem</h3>
                {renderReview(
                  orderedReviews[0] ?? {
                    id: selectedReview.id,
                    user_name: selectedReview.user_name,
                    star: selectedReview.star,
                    title: selectedReview.title,
                    content: selectedReview.content,
                    group: selectedReview.group,
                    product_id: selectedReview.product_id,
                    useful: selectedReview.useful ?? 0,
                    user_id: selectedReview.user_id,
                    display_created_at: selectedReview.created_at ?? undefined,
                    reply_name: selectedReview.reply_name,
                    reply_content: selectedReview.reply_content,
                    reply_at: selectedReview.reply_at ?? undefined,
                    images: selectedReview.images,
                  },
                  true
                )}
              </div>

              {orderedReviews.length > 1 && (
                <div>
                  <h3 className="text-sm font-medium text-gray-700 mb-2">Các đánh giá khác</h3>
                  <div className="space-y-3">
                    {orderedReviews.slice(1).map((r) => renderReview(r, false))}
                  </div>
                </div>
              )}

              {orderedReviews.length <= 1 && !loading && (
                <p className="text-sm text-gray-500">Không có đánh giá khác cho sản phẩm này.</p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
