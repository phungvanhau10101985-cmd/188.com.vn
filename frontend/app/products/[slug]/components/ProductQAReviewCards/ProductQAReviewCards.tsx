'use client';

import { useState, useEffect } from 'react';
import { Product } from '@/types/api';
import type { ProductQuestionItem, ProductReviewItem } from '@/types/api';
import { apiClient } from '@/lib/api-client';
import { useAuth } from '@/features/auth/hooks/useAuth';
import ProductReviewFormModal from '../ProductReviewFormModal/ProductReviewFormModal';
import { useToast } from '@/components/ToastProvider';
import VerifiedPurchaserBadge from '../VerifiedPurchaserBadge';

function formatQaDate(s: string | null | undefined) {
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

interface ProductQAReviewCardsProps {
  product: Product;
  onOpenQA?: () => void;
  onOpenReviews?: () => void;
  /** 'grid' = 2 cột (desktop), 'stack' = 1 cột (mobile, Đánh giá trên Câu hỏi dưới) */
  layout?: 'grid' | 'stack';
}

export default function ProductQAReviewCards({
  product,
  onOpenQA,
  onOpenReviews,
  layout = 'grid',
}: ProductQAReviewCardsProps) {
  const [sampleQuestion, setSampleQuestion] = useState<ProductQuestionItem | null>(null);
  const [questionCount, setQuestionCount] = useState<number>(0);
  const [togglingUsefulId, setTogglingUsefulId] = useState<number | null>(null);
  const [sampleReview, setSampleReview] = useState<ProductReviewItem | null>(null);
  const [reviewCount, setReviewCount] = useState<number>(0);
  const [togglingReviewUsefulId, setTogglingReviewUsefulId] = useState<number | null>(null);
  const [reviewFormOpen, setReviewFormOpen] = useState(false);
  const [canReview, setCanReview] = useState(false);
  const [hasReviewed, setHasReviewed] = useState(false);
  const { isAuthenticated } = useAuth();
  const { pushToast } = useToast();

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

  const refreshReviews = () => {
    apiClient.getProductReviews(product.id).then((list) => {
      if (Array.isArray(list)) {
        setReviewCount(list.length);
        setSampleReview(list.length > 0 ? list[0] : null);
      }
    }).catch(() => {});
  };

  useEffect(() => {
    let cancelled = false;
    apiClient
      .getProductQuestions(product.id)
      .then((list) => {
        if (!cancelled && Array.isArray(list)) {
          setQuestionCount(list.length);
          setSampleQuestion(list.length > 0 ? list[0] : null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSampleQuestion(null);
          setQuestionCount(0);
        }
      });
    return () => { cancelled = true; };
  }, [product.id]);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .getProductReviews(product.id)
      .then((list) => {
        if (!cancelled && Array.isArray(list)) {
          setReviewCount(list.length);
          setSampleReview(list.length > 0 ? list[0] : null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSampleReview(null);
          setReviewCount(0);
        }
      });
    return () => { cancelled = true; };
  }, [product.id]);

  const handleToggleUseful = async (questionId: number) => {
    if (!isAuthenticated) {
      pushToast({ title: 'Vui lòng đăng nhập để bình chọn', variant: 'info', durationMs: 2500 });
      return;
    }
    setTogglingUsefulId(questionId);
    try {
      const res = await apiClient.toggleQuestionUseful(questionId);
      setSampleQuestion((prev) =>
        prev && prev.id === questionId ? { ...prev, useful: res.useful, user_has_voted: res.user_has_voted } : prev
      );
    } catch {
      // ignore
    } finally {
      setTogglingUsefulId(null);
    }
  };

  const handleToggleReviewUseful = async (reviewId: number) => {
    if (!isAuthenticated) {
      pushToast({ title: 'Vui lòng đăng nhập để bình chọn', variant: 'info', durationMs: 2500 });
      return;
    }
    setTogglingReviewUsefulId(reviewId);
    try {
      const res = await apiClient.toggleReviewUseful(reviewId);
      setSampleReview((prev) =>
        prev && prev.id === reviewId ? { ...prev, useful: res.useful, user_has_voted: res.user_has_voted } : prev
      );
    } catch {
      // ignore
    } finally {
      setTogglingReviewUsefulId(null);
    }
  };

  const containerClass = layout === 'stack'
    ? 'flex flex-col gap-3 sm:gap-4 border-t border-gray-200 pt-4 mt-4'
    : 'grid grid-cols-1 lg:grid-cols-2 gap-3 sm:gap-4 border-t border-gray-200 pt-4 mt-4';

  return (
    <div className={containerClass}>
      {/* Đánh giá (trên / cột phải desktop) */}
      <article className="flex flex-col rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden min-h-[180px]">
        <header className="px-3 py-2 border-b border-gray-100 bg-gradient-to-r from-gray-50 to-white">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-amber-100 text-amber-600" aria-hidden>
                <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" /></svg>
              </span>
              <div className="min-w-0">
                <h2 className="font-semibold text-gray-900 text-sm truncate">Đánh giá từ khách hàng</h2>
                <p className="text-xs text-gray-500">{reviewCount > 0 ? reviewCount : (product.rating_total ?? 0)} đánh giá</p>
              </div>
            </div>
            <div className="flex items-center gap-1 shrink-0 rounded-lg bg-amber-50 px-2 py-0.5">
              <span className="text-amber-600 text-base font-bold leading-none">{product.rating_point?.toFixed(1) ?? '0'}</span>
              <span className="text-amber-500/80 text-xs">/5</span>
              <span className="text-amber-400 text-xs" aria-hidden>★</span>
            </div>
          </div>
        </header>
        <div className="p-3 flex-1 flex flex-col min-h-0">
          {sampleReview ? (
            <>
              <div className="rounded-lg border border-gray-100 bg-gray-50/60 p-2.5 space-y-2 flex-1">
                <div className="flex items-start justify-between gap-2 flex-wrap">
                  <div className="min-w-0 flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
                    <span className="font-semibold text-gray-900 text-sm">{sampleReview.user_name || 'Khách'}:</span>
                    {sampleReview.user_id != null && sampleReview.user_id !== undefined && (
                      <VerifiedPurchaserBadge compact />
                    )}
                    <span className="text-xs text-gray-500">{formatQaDate(sampleReview.display_created_at ?? sampleReview.created_at)}</span>
                  </div>
                  <span className="flex text-amber-400 text-sm shrink-0" aria-label={`${sampleReview.star || 5} sao`}>
                    {Array.from({ length: 5 }, (_, i) => (i < (sampleReview.star || 5) ? '★' : '☆')).join('')}
                  </span>
                </div>
                {sampleReview.title && (
                  <p className="text-sm font-medium text-[#ea580c]">{sampleReview.title}</p>
                )}
                <p className="text-sm text-gray-700 leading-snug">{sampleReview.content}</p>
                {sampleReview.reply_content && (
                  <div className="pl-2.5 border-l-2 border-[#ea580c] bg-orange-50/60 rounded-r py-1.5 pr-2">
                    <p className="text-xs font-semibold text-gray-800">
                      {sampleReview.reply_name || '188.COM.VN'} <span className="font-normal text-gray-500">· {formatQaDate(sampleReview.display_reply_at ?? sampleReview.reply_at)}</span>
                    </p>
                    <p className="text-xs text-gray-700 leading-snug mt-0.5">{sampleReview.reply_content}</p>
                  </div>
                )}
                <div className="flex items-center gap-2 flex-wrap pt-0.5">
                  {sampleReview.useful > 0 && (
                    <span className="text-xs text-gray-500">{sampleReview.useful} người thấy hữu ích</span>
                  )}
                  <button
                    type="button"
                    onClick={() => handleToggleReviewUseful(sampleReview.id)}
                    disabled={togglingReviewUsefulId === sampleReview.id}
                    className={`inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium transition disabled:opacity-50 ${
                      sampleReview.user_has_voted ? 'bg-orange-100 text-orange-700' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                    }`}
                    title="Hữu ích"
                  >
                    <svg className="h-3 w-3" fill="currentColor" viewBox="0 0 24 24"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 11H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h3z" /></svg>
                    Hữu ích
                  </button>
                </div>
              </div>
              <div className="mt-2 pt-2 border-t border-gray-100 flex flex-wrap gap-2">
                {onOpenReviews ? (
                  <button type="button" onClick={onOpenReviews} className="flex-1 min-w-[100px] py-2 rounded-lg bg-[#ea580c] text-white text-sm font-medium hover:bg-[#c2410c] active:bg-[#9a3412] transition shadow-sm">
                    Xem tất cả đánh giá
                  </button>
                ) : (
                  <a href={`/products/${product.slug}#reviews`} className="flex-1 min-w-[100px] py-2 text-center rounded-lg bg-[#ea580c] text-white text-sm font-medium hover:bg-[#c2410c] transition shadow-sm">
                    Xem tất cả đánh giá
                  </a>
                )}
                {hasReviewed ? (
                  onOpenReviews ? (
                    <button type="button" onClick={onOpenReviews} className="py-2 px-3 rounded-lg border border-[#ea580c] text-[#ea580c] text-sm font-medium hover:bg-orange-50 transition">
                      Xem thêm đánh giá...
                    </button>
                  ) : (
                    <a href={`/products/${product.slug}#reviews`} className="inline-block py-2 px-3 rounded-lg border border-[#ea580c] text-[#ea580c] text-sm font-medium hover:bg-orange-50 transition text-center">
                      Xem thêm đánh giá...
                    </a>
                  )
                ) : (
                  <button type="button" onClick={() => setReviewFormOpen(true)} className="py-2 px-3 rounded-lg border border-[#ea580c] text-[#ea580c] text-sm font-medium hover:bg-orange-50 transition">
                    Viết đánh giá
                  </button>
                )}
              </div>
            </>
          ) : (
            <div className="flex flex-col flex-1 items-center justify-center py-6 px-3 text-center">
              <span className="flex h-12 w-12 items-center justify-center rounded-full bg-amber-50 text-amber-400 mb-2" aria-hidden>
                <svg className="h-6 w-6" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" /></svg>
              </span>
              <p className="text-sm text-gray-500 mb-2">Chưa có đánh giá nào</p>
              <div className="flex flex-wrap gap-2 justify-center">
                {onOpenReviews ? (
                  <button type="button" onClick={onOpenReviews} className="py-2 px-4 rounded-lg bg-[#ea580c] text-white text-sm font-medium hover:bg-[#c2410c] transition shadow-sm">
                    Xem thêm đánh giá...
                  </button>
                ) : (
                  <a href={`/products/${product.slug}#reviews`} className="inline-block py-2 px-4 rounded-lg bg-[#ea580c] text-white text-sm font-medium hover:bg-[#c2410c] transition shadow-sm">
                    Xem thêm đánh giá...
                  </a>
                )}
                <button type="button" onClick={() => setReviewFormOpen(true)} className="py-2 px-4 rounded-lg border border-gray-300 text-gray-700 text-sm font-medium hover:bg-gray-50 transition">
                  Viết đánh giá
                </button>
              </div>
            </div>
          )}
        </div>
      </article>

      {/* Câu hỏi / Hỏi đáp (dưới / cột trái desktop) */}
      <article className="flex flex-col rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden min-h-[180px]">
        <header className="px-3 py-2 border-b border-gray-100 bg-gradient-to-r from-gray-50 to-white">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-orange-100 text-orange-600" aria-hidden>
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
            </span>
            <div className="min-w-0">
              <h2 className="font-semibold text-gray-900 text-sm truncate">Hỏi đáp về sản phẩm</h2>
              <p className="text-xs text-gray-500">{questionCount > 0 ? questionCount : (product.question_total ?? 0)} câu hỏi và trả lời</p>
            </div>
          </div>
        </header>
        <div className="p-3 flex-1 flex flex-col min-h-0">
          {sampleQuestion ? (
            <>
              <div className="rounded-lg border border-gray-100 bg-gray-50/60 p-2.5 space-y-1 flex-1">
                <div>
                  <p className="text-sm font-medium text-gray-900 leading-snug">
                    <span className="text-gray-600 font-normal">{sampleQuestion.user_name || 'Khách'} hỏi: </span>
                    {sampleQuestion.content}
                  </p>
                  <p className="text-xs text-gray-500 mt-0.5">{formatQaDate(sampleQuestion.display_created_at ?? sampleQuestion.created_at)}</p>
                </div>
                {sampleQuestion.reply_admin_content && (
                  <div className="pl-2 border-l-2 border-[#ea580c] bg-orange-50/60 rounded-r py-1 pr-1.5">
                    <p className="text-xs font-semibold text-gray-800">
                      {sampleQuestion.reply_admin_name || '188.COM.VN'} <span className="font-normal text-gray-500">· {formatQaDate(sampleQuestion.display_reply_admin_at ?? sampleQuestion.reply_admin_at)}</span>
                    </p>
                    <p className="text-xs text-gray-700 leading-snug mt-0.5">{sampleQuestion.reply_admin_content}</p>
                  </div>
                )}
                {sampleQuestion.reply_user_one_content && (
                  <div className="pl-2 border-l-2 border-gray-200 bg-gray-50 rounded-r py-1 pr-1.5">
                    <p className="text-xs font-semibold text-gray-800 flex flex-wrap items-center gap-x-1 gap-y-0.5">
                      <span className="inline-flex items-center gap-1">
                        {sampleQuestion.reply_user_one_name}
                        {sampleQuestion.reply_user_one_id != null && <VerifiedPurchaserBadge compact />}
                      </span>
                      <span className="font-normal text-gray-500">
                        trả lời · {formatQaDate(sampleQuestion.display_reply_user_one_at ?? sampleQuestion.reply_user_one_at)}
                      </span>
                    </p>
                    <p className="text-xs text-gray-600 leading-snug mt-0.5">{sampleQuestion.reply_user_one_content}</p>
                  </div>
                )}
                {sampleQuestion.reply_user_two_content && (
                  <div className="pl-2 border-l-2 border-gray-200 bg-gray-50 rounded-r py-1 pr-1.5">
                    <p className="text-xs font-semibold text-gray-800 flex flex-wrap items-center gap-x-1 gap-y-0.5">
                      <span className="inline-flex items-center gap-1">
                        {sampleQuestion.reply_user_two_name}
                        {sampleQuestion.reply_user_two_id != null && <VerifiedPurchaserBadge compact />}
                      </span>
                      <span className="font-normal text-gray-500">
                        trả lời · {formatQaDate(sampleQuestion.display_reply_user_two_at ?? sampleQuestion.reply_user_two_at)}
                      </span>
                    </p>
                    <p className="text-xs text-gray-600 leading-snug mt-0.5">{sampleQuestion.reply_user_two_content}</p>
                  </div>
                )}
                <div className="flex items-center gap-2 flex-wrap pt-0.5">
                  {sampleQuestion.useful > 0 && (
                    <span className="text-xs text-gray-500">{sampleQuestion.useful} người thấy hữu ích</span>
                  )}
                  <button
                    type="button"
                    onClick={() => handleToggleUseful(sampleQuestion.id)}
                    disabled={togglingUsefulId === sampleQuestion.id}
                    className={`inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium transition disabled:opacity-50 ${
                      sampleQuestion.user_has_voted ? 'bg-orange-100 text-orange-700' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                    }`}
                    title="Hữu ích"
                  >
                    <svg className="h-3 w-3" fill="currentColor" viewBox="0 0 24 24"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 11H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h3z" /></svg>
                    Hữu ích
                  </button>
                </div>
              </div>
              <div className="mt-2 pt-2 border-t border-gray-100">
                {onOpenQA ? (
                  <button type="button" onClick={onOpenQA} className="w-full py-2 rounded-lg bg-[#ea580c] text-white text-sm font-medium hover:bg-[#c2410c] active:bg-[#9a3412] transition shadow-sm">
                    Xem thêm câu hỏi, trả lời và đặt câu hỏi...
                  </button>
                ) : (
                  <a href={`/products/${product.slug}#qa`} className="block w-full py-2 text-center rounded-lg bg-[#ea580c] text-white text-sm font-medium hover:bg-[#c2410c] transition shadow-sm">
                    Xem thêm câu hỏi, trả lời và đặt câu hỏi...
                  </a>
                )}
              </div>
            </>
          ) : (
            <div className="flex flex-col flex-1 items-center justify-center py-6 px-3 text-center">
              <span className="flex h-12 w-12 items-center justify-center rounded-full bg-gray-100 text-gray-400 mb-2" aria-hidden>
                <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
              </span>
              <p className="text-sm text-gray-500 mb-2">Chưa có câu hỏi nào</p>
              {onOpenQA ? (
                <button type="button" onClick={onOpenQA} className="py-2 px-4 rounded-lg bg-[#ea580c] text-white text-sm font-medium hover:bg-[#c2410c] transition shadow-sm">
                  Xem danh sách câu hỏi
                </button>
              ) : (
                <a href={`/products/${product.slug}#qa`} className="inline-block py-2 px-4 rounded-lg bg-[#ea580c] text-white text-sm font-medium hover:bg-[#c2410c] transition shadow-sm">
                  Xem danh sách câu hỏi
                </a>
              )}
            </div>
          )}
        </div>
      </article>

      <ProductReviewFormModal
        product={product}
        isOpen={reviewFormOpen}
        onClose={() => setReviewFormOpen(false)}
        onSuccess={() => { refreshReviews(); setHasReviewed(true); }}
        purchaseRequired={!canReview}
      />
    </div>
  );
}
