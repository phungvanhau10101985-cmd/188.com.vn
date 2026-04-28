'use client';

import { useState, useEffect, useMemo } from 'react';
import { apiClient } from '@/lib/api-client';
import ProductReviewFormModal from '@/app/products/[slug]/components/ProductReviewFormModal/ProductReviewFormModal';
import type { Product } from '@/types/api';

interface OrderItem {
  id: number;
  product_id?: number;
  product_name: string;
  quantity: number;
  unit_price: number;
}

interface Order {
  id: number;
  order_code: string;
  status: string;
  items: OrderItem[];
}

interface OrderReviewModalProps {
  order: Order;
  isOpen: boolean;
  onClose: () => void;
}

export default function OrderReviewModal({ order, isOpen, onClose }: OrderReviewModalProps) {
  const [reviewProduct, setReviewProduct] = useState<Product | null>(null);
  const [productIndex, setProductIndex] = useState(0);
  const [loading, setLoading] = useState(false);

  const canReview = order && ['delivered', 'completed'].includes(order.status);
  const uniqueProducts = useMemo(() => {
    const itemsWithProductId = (order.items || []).filter((i) => i.product_id != null);
    return Array.from(new Map(itemsWithProductId.map((i) => [i.product_id!, i])).values());
  }, [order.items]);

  useEffect(() => {
    if (!isOpen) {
      setReviewProduct(null);
      setProductIndex(0);
      return;
    }
    if (!canReview || uniqueProducts.length === 0) return;
    setLoading(true);
    apiClient
      .getProductById(uniqueProducts[productIndex].product_id!)
      .then(setReviewProduct)
      .catch(() => setReviewProduct(null))
      .finally(() => setLoading(false));
  }, [isOpen, order.id, canReview, productIndex, uniqueProducts]);

  const handleSuccess = () => {
    if (productIndex < uniqueProducts.length - 1) {
      setReviewProduct(null);
      setLoading(true);
      setProductIndex((i) => i + 1);
    } else {
      onClose();
    }
  };

  if (!isOpen) return null;
  if (!canReview || uniqueProducts.length === 0) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" onClick={onClose}>
        <div className="bg-white rounded-xl p-6 max-w-sm" onClick={(e) => e.stopPropagation()}>
          <p className="text-gray-600 text-sm">
            {!canReview ? 'Chỉ đơn hàng đã nhận mới được đánh giá.' : 'Không có sản phẩm nào để đánh giá.'}
          </p>
          <button onClick={onClose} className="mt-4 px-4 py-2 bg-gray-200 rounded-lg text-sm">Đóng</button>
        </div>
      </div>
    );
  }
  if (loading && !reviewProduct) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" onClick={onClose}>
        <div className="bg-white rounded-xl p-8 text-center text-gray-500">Đang tải...</div>
      </div>
    );
  }
  if (!reviewProduct) return null;

  return (
    <ProductReviewFormModal
      key={reviewProduct.id}
      product={reviewProduct}
      isOpen={true}
      onClose={onClose}
      onSuccess={handleSuccess}
    />
  );
}
