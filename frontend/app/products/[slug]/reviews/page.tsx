'use client';

import { useState, useEffect } from 'react';
import Image from 'next/image';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { apiClient } from '@/lib/api-client';
import type { Product, ProductReviewItem } from '@/types/api';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { formatPrice } from '@/lib/utils';
import { getOptimizedImage as getOptImg } from '@/lib/image-utils';
import ProductReviewFormModal from '../components/ProductReviewFormModal/ProductReviewFormModal';
import { useToast } from '@/components/ToastProvider';

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
      {Array.from({ length: 5 }, (_, i) => (i < star ? '★' : '☆')).join('')}
    </span>
  );
}

export default function ProductReviewsPage() {
  const params = useParams();
  const slug = params.slug as string;
  const { isAuthenticated } = useAuth();
  const { pushToast } = useToast();
  const [product, setProduct] = useState<Product | null>(null);
  const [reviews, setReviews] = useState<ProductReviewItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [togglingUsefulId, setTogglingUsefulId] = useState<number | null>(null);
  const [reviewFormOpen, setReviewFormOpen] = useState(false);
  const [canReview, setCanReview] = useState(false);
  const [hasReviewed, setHasReviewed] = useState(false);

  useEffect(() => {
    if (!slug) return;
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const productData = await apiClient.getProductBySlug(slug);
        if (cancelled) return;
        if (!productData) {
          setError('Không tìm thấy sản phẩm');
          return;
        }
        setProduct(productData);
        const list = await apiClient.getProductReviews(productData.id);
        if (cancelled) return;
        setReviews(Array.isArray(list) ? list : []);
      } catch (e) {
        if (!cancelled) setError((e as Error)?.message || 'Không thể tải đánh giá');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [slug]);

  useEffect(() => {
    if (!product?.id || !isAuthenticated) {
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
  }, [product?.id, isAuthenticated]);

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

  const myReviews = reviews.filter((r) => r.is_current_user);
  const otherReviews = reviews.filter((r) => !r.is_current_user);

  if (loading) {
    return (
      <div className="min-h-[40vh] flex items-center justify-center">
        <p className="text-gray-500">Đang tải...</p>
      </div>
    );
  }

  if (error || !product) {
    return (
      <div className="container mx-auto px-4 py-8">
        <p className="text-red-600">{error || 'Không tìm thấy sản phẩm'}</p>
        <Link href="/account/orders" className="mt-4 inline-block text-[#ea580c] hover:underline">
          ← Quay lại đơn hàng
        </Link>
      </div>
    );
  }

  const renderReviewList = (list: ProductReviewItem[], title?: string) => (
    <div className="space-y-4">
      {title && (
        <h2 className="text-lg font-semibold text-gray-900 border-b border-gray-200 pb-2">{title}</h2>
      )}
      {list.map((r) => (
        <div
          key={r.id}
          className={`bg-white rounded-xl border p-4 space-y-2 ${r.is_current_user ? 'border-[#ea580c]/40 bg-orange-50/30' : 'border-gray-100'}`}
        >
          {r.is_current_user && (
            <span className="inline-block px-2 py-0.5 rounded text-xs font-medium bg-[#ea580c] text-white mb-1">
              Đánh giá của bạn
            </span>
          )}
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <span className="font-semibold text-gray-900">{r.user_name || 'Khách'}</span>
              <span className="ml-2 text-xs text-gray-500">{formatDate(r.display_created_at ?? r.created_at)}</span>
            </div>
            <StarRating star={r.star || 5} />
          </div>
          {r.title && <p className="text-sm font-medium text-[#ea580c]">{r.title}</p>}
          <p className="text-sm text-gray-700">{r.content}</p>
          {r.reply_content && (
            <div className="pl-3 border-l-2 border-[#ea580c] bg-orange-50/50 rounded-r py-2 pr-2 mt-2">
              <p className="text-xs font-semibold text-gray-800">
                {r.reply_name || '188.COM.VN'} · {formatDate(r.display_reply_at ?? r.reply_at)}
              </p>
              <p className="text-sm text-gray-700 mt-0.5">{r.reply_content}</p>
            </div>
          )}
          <div className="flex items-center gap-2 flex-wrap pt-1">
            {r.useful > 0 && (
              <span className="text-xs text-gray-500">{r.useful} người thấy hữu ích</span>
            )}
            <button
              type="button"
              onClick={() => handleToggleUseful(r.id)}
              disabled={togglingUsefulId === r.id}
              className={`inline-flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium transition disabled:opacity-50 ${
                r.user_has_voted ? 'bg-orange-100 text-orange-700' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
              title="Hữu ích"
            >
              <svg className="h-3.5 w-3.5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 11H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h3z" />
              </svg>
              Hữu ích
            </button>
          </div>
        </div>
      ))}
    </div>
  );

  return (
    <div className="container mx-auto px-4 py-6 max-w-3xl">
      {/* Breadcrumb */}
      <nav className="text-sm text-gray-500 mb-4">
        <Link href="/" className="hover:text-[#ea580c]">Trang chủ</Link>
        <span className="mx-2">/</span>
        <Link href={`/products/${product.slug}`} className="hover:text-[#ea580c]">{product.name}</Link>
        <span className="mx-2">/</span>
        <span className="text-gray-900 font-medium">Tất cả đánh giá</span>
      </nav>

      <h1 className="text-xl font-bold text-gray-900 mb-4">Tất cả đánh giá</h1>

      {/* Product card */}
      <div className="flex items-center gap-4 p-4 bg-gray-50 rounded-xl border border-gray-100 mb-6">
        <Link
          href={`/products/${product.slug}`}
          className="shrink-0 w-20 h-20 rounded-lg overflow-hidden bg-white border border-gray-200 relative"
        >
          <Image
            src={getOptImg(product.main_image || product.images?.[0], { fallbackStrategy: 'local' })}
            alt={product.name}
            fill
            sizes="80px"
            className="object-cover"
          />
        </Link>
        <div className="min-w-0 flex-1">
          <Link href={`/products/${product.slug}`} className="font-semibold text-gray-900 hover:text-[#ea580c] line-clamp-2">
            {product.name}
          </Link>
          <p className="text-[#ea580c] font-semibold mt-0.5">{formatPrice(product.price)}</p>
        </div>
        <div className="shrink-0 flex flex-col gap-2">
          <Link
            href={`/products/${product.slug}`}
            className="px-4 py-2 rounded-lg border border-gray-300 text-gray-700 text-sm font-medium hover:bg-gray-50"
          >
            Xem sản phẩm
          </Link>
          {!hasReviewed && canReview && (
            <button
              type="button"
              onClick={() => setReviewFormOpen(true)}
              className="px-4 py-2 rounded-lg bg-[#ea580c] text-white text-sm font-medium hover:bg-[#c2410c]"
            >
              Viết đánh giá
            </button>
          )}
        </div>
      </div>

      {/* Reviews: của bạn lên đầu, sau đó khách khác */}
      {reviews.length === 0 ? (
        <div className="bg-gray-50 rounded-xl p-8 text-center text-gray-600">
          Chưa có đánh giá nào.
          {canReview && !hasReviewed && (
            <button
              type="button"
              onClick={() => setReviewFormOpen(true)}
              className="mt-3 block mx-auto px-4 py-2 rounded-lg bg-[#ea580c] text-white text-sm font-medium hover:bg-[#c2410c]"
            >
              Viết đánh giá
            </button>
          )}
        </div>
      ) : (
        <div className="space-y-8">
          {myReviews.length > 0 && renderReviewList(myReviews, 'Đánh giá của bạn')}
          {otherReviews.length > 0 && renderReviewList(otherReviews, myReviews.length > 0 ? 'Đánh giá khách hàng khác' : 'Đánh giá khách hàng')}
        </div>
      )}

      <div className="mt-6">
        <Link href="/account/orders" className="text-[#ea580c] hover:underline text-sm">
          ← Quay lại đơn hàng
        </Link>
      </div>

      {product && (
        <ProductReviewFormModal
          product={product}
          isOpen={reviewFormOpen}
          onClose={() => setReviewFormOpen(false)}
          onSuccess={() => {
            setReviewFormOpen(false);
            apiClient.getProductReviews(product.id).then((list) => setReviews(Array.isArray(list) ? list : []));
            setHasReviewed(true);
          }}
          purchaseRequired={!canReview}
        />
      )}
    </div>
  );
}
