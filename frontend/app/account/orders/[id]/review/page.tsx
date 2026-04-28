'use client';

import { useState, useEffect } from 'react';
import Image from 'next/image';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { apiClient } from '@/lib/api-client';
import { getOptimizedImage } from '@/lib/image-utils';
import ProductReviewFormModal from '@/app/products/[slug]/components/ProductReviewFormModal/ProductReviewFormModal';
import type { Product } from '@/types/api';
import { useToast } from '@/components/ToastProvider';

interface OrderItem {
  id: number;
  product_id: number;
  product_name: string;
  product_image?: string | null;
  quantity: number;
  unit_price: number;
  total_price?: number;
}

interface Order {
  id: number;
  order_code: string;
  status: string;
  items: OrderItem[];
}

const STATUS_LABELS: Record<string, string> = {
  delivered: 'Đã nhận hàng',
  completed: 'Đã đánh giá',
};

export default function OrderReviewPage() {
  const params = useParams();
  const id = Number(params?.id);
  const [order, setOrder] = useState<Order | null>(null);
  const [loading, setLoading] = useState(true);
  const [reviewProduct, setReviewProduct] = useState<Product | null>(null);
  const [fetchingProduct, setFetchingProduct] = useState(false);
  const { pushToast } = useToast();

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    apiClient
      .getOrder(id)
      .then((data) => setOrder(data))
      .catch(() => setOrder(null))
      .finally(() => setLoading(false));
  }, [id]);

  const canReview = order && ['delivered', 'completed'].includes(order.status);

  const handleOpenReview = async (productId: number) => {
    setFetchingProduct(true);
    try {
      const product = await apiClient.getProductById(productId);
      setReviewProduct(product);
    } catch {
      pushToast({ title: 'Không thể tải thông tin sản phẩm', variant: 'error', durationMs: 3000 });
    } finally {
      setFetchingProduct(false);
    }
  };

  if (loading) {
    return (
      <div className="max-w-2xl mx-auto py-12 text-center text-gray-500">
        Đang tải đơn hàng...
      </div>
    );
  }

  if (!order) {
    return (
      <div className="max-w-2xl mx-auto py-8">
        <p className="text-gray-600 mb-4">Không tìm thấy đơn hàng.</p>
        <Link href="/account/orders" className="text-blue-600 hover:underline">
          ← Quay lại đơn hàng
        </Link>
      </div>
    );
  }

  if (!canReview) {
    return (
      <div className="max-w-2xl mx-auto py-8">
        <h1 className="text-xl font-bold text-gray-900 mb-4">Đánh giá đơn hàng</h1>
        <p className="text-gray-600 mb-6">
          Chỉ đơn hàng đã nhận (trạng thái &quot;Đã nhận hàng&quot; hoặc &quot;Đã đánh giá&quot;) mới được đánh giá sản phẩm.
        </p>
        <Link href={`/account/orders/${id}`} className="text-blue-600 hover:underline">
          ← Quay lại chi tiết đơn hàng
        </Link>
      </div>
    );
  }

  const itemsWithProductId = (order.items || []).filter((i) => i.product_id != null);
  const uniqueProducts = Array.from(
    new Map(itemsWithProductId.map((i) => [i.product_id, i])).values()
  );

  return (
    <div className="max-w-2xl mx-auto py-8 space-y-6">
      <div className="flex flex-wrap items-center gap-4">
        <Link href={`/account/orders/${id}`} className="text-gray-500 hover:text-gray-700">
          ← Chi tiết đơn hàng
        </Link>
        <h1 className="text-xl font-bold text-gray-900">Đánh giá sản phẩm</h1>
        <span className="px-2 py-1 rounded text-sm font-medium bg-gray-100 text-gray-700">
          Đơn #{order.order_code}
        </span>
      </div>

      <p className="text-gray-600 text-sm">
        Chọn sản phẩm bạn muốn đánh giá. Chỉ khách hàng đã mua và nhận hàng mới được đánh giá.
      </p>

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden divide-y divide-gray-100">
        {uniqueProducts.map((item) => (
          <div
            key={item.id}
            className="flex items-center gap-4 p-4 hover:bg-gray-50/50"
          >
            {item.product_image ? (
              <div className="relative w-20 h-20 rounded-lg overflow-hidden bg-gray-100 flex-shrink-0">
                <Image
                  src={getOptimizedImage(item.product_image, { fallbackStrategy: 'local' })}
                  alt=""
                  fill
                  sizes="80px"
                  className="object-cover"
                />
              </div>
            ) : (
              <div className="w-20 h-20 rounded-lg bg-gray-100 flex-shrink-0" />
            )}
            <div className="flex-1 min-w-0">
              <p className="font-medium text-gray-900 line-clamp-2">{item.product_name}</p>
              <p className="text-sm text-gray-500 mt-0.5">Số lượng: {item.quantity}</p>
            </div>
            <button
              type="button"
              onClick={() => handleOpenReview(item.product_id)}
              disabled={fetchingProduct}
              className="px-4 py-2 bg-[#ea580c] text-white rounded-lg hover:bg-[#c2410c] text-sm font-medium disabled:opacity-50 shrink-0"
            >
              {fetchingProduct ? 'Đang tải...' : 'Đánh giá'}
            </button>
          </div>
        ))}
      </div>

      {reviewProduct && (
        <ProductReviewFormModal
          product={reviewProduct}
          isOpen={!!reviewProduct}
          onClose={() => setReviewProduct(null)}
          onSuccess={() => setReviewProduct(null)}
        />
      )}
    </div>
  );
}
