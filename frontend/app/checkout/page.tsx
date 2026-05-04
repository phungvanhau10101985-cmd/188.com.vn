// frontend/app/checkout/page.tsx - CHECKOUT (Tailwind only, không dùng antd)
'use client';

import { useState, useEffect, useMemo } from 'react';
import Image from 'next/image';
import { useRouter } from 'next/navigation';
import { useCart } from '@/features/cart/hooks/useCart';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { apiClient } from '@/lib/api-client';
import type { CartItem } from '@/features/cart/types/cart';
import { useToast } from '@/components/ToastProvider';
import { trackEvent } from '@/lib/analytics';
import { shouldRedirectToDepositAfterCreate } from '@/lib/order-deposit';
import { buildAuthLoginHrefFromFullPath } from '@/lib/auth-redirect';

function formatVnd(n: number) {
  return new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(n);
}

export default function CheckoutPage() {
  const router = useRouter();
  const { cart, clearCart, hideAddToCartPopup } = useCart();
  const { isAuthenticated, user } = useAuth();
  const { pushToast } = useToast();
  const cartItems = useMemo<CartItem[]>(() => cart?.items ?? [], [cart?.items]);
  const totalPrice = useMemo(() => cart?.total_price ?? 0, [cart?.total_price]);

  useEffect(() => {
    hideAddToCartPopup();
  }, [hideAddToCartPopup]);

  useEffect(() => {
    if (!isAuthenticated) {
      router.replace(buildAuthLoginHrefFromFullPath('/checkout'));
    }
  }, [isAuthenticated, router]);
  const [currentStep, setCurrentStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [requiresDeposit, setRequiresDeposit] = useState(false);
  const [depositType, setDepositType] = useState<'percent_30' | 'percent_100'>('percent_30');
  const [depositAmount, setDepositAmount] = useState(0);
  const [remainingAmount, setRemainingAmount] = useState(0);
  const [orderSummary, setOrderSummary] = useState({
    subtotal: 0,
    shippingFee: 30000,
    discount: 0,
    total: 0,
  });
  const [paymentMethod, setPaymentMethod] = useState('bank_transfer');
  const [formData, setFormData] = useState({
    name: '',
    phone: '',
    email: '',
    address: '',
    note: '',
  });
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (user) {
      setFormData((prev) => ({
        ...prev,
        name: user.full_name || '',
        phone: user.phone || '',
        email: user.email || '',
      }));
    }
  }, [user]);

  useEffect(() => {
    if (cartItems.length > 0) {
      const hasDepositRequired = cartItems.some((item) => item.product_data?.deposit_require || false);
      setRequiresDeposit(hasDepositRequired);
      const subtotal = totalPrice;
      const shippingFee = subtotal < 500000 ? 30000 : 0;
      const total = subtotal + shippingFee;
      setOrderSummary({ subtotal, shippingFee, discount: 0, total });
      if (hasDepositRequired) {
        const deposit = depositType === 'percent_30' ? total * 0.3 : total;
        setDepositAmount(deposit);
        setRemainingAmount(total - deposit);
      } else {
        setDepositAmount(0);
        setRemainingAmount(total);
      }
    }
  }, [cartItems, totalPrice, depositType]);

  useEffect(() => {
    if (cartItems.length > 0) {
      trackEvent('begin_checkout', { status: 'view', item_count: cartItems.length });
    }
  }, [cartItems.length]);

  const validateStep1 = (): boolean => {
    const err: Record<string, string> = {};
    if (!formData.name?.trim()) err.name = 'Vui lòng nhập họ tên';
    if (!formData.phone?.trim()) err.phone = 'Vui lòng nhập số điện thoại';
    else if (!/^[0-9]{10,11}$/.test(formData.phone)) err.phone = 'Số điện thoại không hợp lệ';
    if (!formData.email?.trim()) err.email = 'Vui lòng nhập email';
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) err.email = 'Email không hợp lệ';
    if (!formData.address?.trim()) err.address = 'Vui lòng nhập địa chỉ';
    setFormErrors(err);
    return Object.keys(err).length === 0;
  };

  const handleNextStep1 = (e: React.FormEvent) => {
    e.preventDefault();
    if (validateStep1()) setCurrentStep(1);
  };

  const handlePlaceOrder = async () => {
    setLoading(true);
    try {
      const orderData = {
        customer_name: formData.name.trim(),
        customer_phone: formData.phone.trim(),
        customer_email: formData.email.trim(),
        customer_address: formData.address.trim(),
        customer_note: formData.note.trim() || undefined,
        payment_method: paymentMethod as 'cod' | 'bank_transfer',
        shipping_method: 'standard',
        deposit_type: requiresDeposit ? depositType : undefined,
        items: cartItems.map((item) => ({
          product_id: item.product_id,
          quantity: item.quantity,
          selected_size: item.selected_size,
          selected_color: item.selected_color,
        })),
      };
      const order = await apiClient.createOrderFull(orderData);
      clearCart();
      trackEvent('purchase', {
        order_id: order.id,
        value: requiresDeposit ? depositAmount : orderSummary.total,
        item_count: cartItems.length,
      });
      pushToast({ title: 'Đặt hàng thành công', variant: 'success', durationMs: 2500 });
      if (shouldRedirectToDepositAfterCreate(order as { requires_deposit?: boolean; status?: string })) {
        router.push(`/account/orders/${order.id}/deposit`);
      } else {
        router.push(`/account/orders?highlight=${order.id}`);
      }
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : 'Lỗi đặt hàng';
      trackEvent('purchase', { status: 'failed', error: msg });
      pushToast({ title: 'Không thể đặt hàng', description: msg, variant: 'error', durationMs: 3500 });
    } finally {
      setLoading(false);
    }
  };

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center px-6">
        <p className="text-sm text-gray-600">Đang chuyển đến đăng nhập...</p>
      </div>
    );
  }

  if (cartItems.length === 0) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center px-6">
        <div className="bg-white border border-gray-200 rounded-2xl p-8 max-w-lg w-full text-center">
          <h2 className="text-xl font-bold text-gray-900 mb-2">Giỏ hàng trống</h2>
          <p className="text-sm text-gray-600 mb-6">Vui lòng thêm sản phẩm trước khi thanh toán.</p>
          <button
            type="button"
            onClick={() => router.push('/cart')}
            className="px-5 py-2.5 bg-[#ea580c] text-white rounded-lg font-medium hover:bg-[#c2410c]"
          >
            Quay lại giỏ hàng
          </button>
        </div>
      </div>
    );
  }

  const stepTitles = ['Thông tin giao hàng', 'Phương thức thanh toán', 'Xác nhận đơn hàng'];

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="max-w-6xl mx-auto px-4">
        {/* Steps */}
        <div className="flex items-center justify-center gap-2 mb-8">
          {stepTitles.map((title, i) => (
            <div key={i} className="flex items-center">
              <div
                className={`px-3 py-1 rounded-full text-sm font-medium ${
                  i === currentStep ? 'bg-orange-500 text-white' : i < currentStep ? 'bg-orange-200 text-orange-800' : 'bg-gray-200 text-gray-600'
                }`}
              >
                {i + 1}. {title}
              </div>
              {i < stepTitles.length - 1 && <span className="mx-1 text-gray-400">→</span>}
            </div>
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <div className="lg:col-span-2">
            {currentStep === 0 && (
              <div className="bg-white rounded-xl shadow border border-gray-200 p-6">
                <h2 className="text-lg font-semibold mb-4">Thông tin giao hàng</h2>
                <form onSubmit={handleNextStep1} className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Họ và tên *</label>
                    <input
                      type="text"
                      value={formData.name}
                      onChange={e => setFormData(f => ({ ...f, name: e.target.value }))}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-transparent"
                      placeholder="Họ và tên"
                    />
                    {formErrors.name && <p className="text-red-500 text-sm mt-1">{formErrors.name}</p>}
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Số điện thoại *</label>
                    <input
                      type="tel"
                      value={formData.phone}
                      onChange={e => setFormData(f => ({ ...f, phone: e.target.value.replace(/\D/g, '').slice(0, 11) }))}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500"
                      placeholder="10–11 số"
                    />
                    {formErrors.phone && <p className="text-red-500 text-sm mt-1">{formErrors.phone}</p>}
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Email *</label>
                    <input
                      type="email"
                      value={formData.email}
                      onChange={e => setFormData(f => ({ ...f, email: e.target.value }))}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500"
                      placeholder="email@example.com"
                    />
                    {formErrors.email && <p className="text-red-500 text-sm mt-1">{formErrors.email}</p>}
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Địa chỉ giao hàng *</label>
                    <textarea
                      value={formData.address}
                      onChange={e => setFormData(f => ({ ...f, address: e.target.value }))}
                      rows={3}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500"
                      placeholder="Số nhà, đường, phường/xã, quận/huyện, tỉnh/thành"
                    />
                    {formErrors.address && <p className="text-red-500 text-sm mt-1">{formErrors.address}</p>}
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Ghi chú</label>
                    <textarea
                      value={formData.note}
                      onChange={e => setFormData(f => ({ ...f, note: e.target.value }))}
                      rows={2}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500"
                      placeholder="Ghi chú thêm về đơn hàng..."
                    />
                  </div>
                  <div className="text-right">
                    <button type="submit" className="px-4 py-2 bg-orange-500 text-white font-medium rounded-lg hover:bg-orange-600">
                      Tiếp tục
                    </button>
                  </div>
                </form>
              </div>
            )}

            {currentStep === 1 && (
              <div className="bg-white rounded-xl shadow border border-gray-200 p-6">
                <h2 className="text-lg font-semibold mb-4">Phương thức thanh toán</h2>
                {requiresDeposit && (
                  <div className="mb-6 p-4 bg-amber-50 border border-amber-200 rounded-lg text-amber-800 text-sm">
                    Sản phẩm trong đơn yêu cầu đặt cọc. Chọn phương thức đặt cọc phù hợp.
                  </div>
                )}
                {requiresDeposit && (
                  <div className="mb-6 p-4 border rounded-lg bg-gray-50">
                    <h3 className="font-semibold mb-3">Lựa chọn đặt cọc</h3>
                    <div className="space-y-3">
                      <label className="flex items-start gap-3 p-3 border rounded cursor-pointer hover:border-orange-500">
                        <input type="radio" name="deposit" checked={depositType === 'percent_30'} onChange={() => setDepositType('percent_30')} className="mt-1" />
                        <div>
                          <span className="font-semibold">Đặt cọc 30%</span>
                          <p className="text-gray-600 text-sm">Thanh toán phần còn lại khi nhận hàng</p>
                        </div>
                      </label>
                      <label className="flex items-start gap-3 p-3 border rounded cursor-pointer hover:border-orange-500">
                        <input type="radio" name="deposit" checked={depositType === 'percent_100'} onChange={() => setDepositType('percent_100')} className="mt-1" />
                        <div>
                          <span className="font-semibold">Thanh toán 100%</span>
                          <p className="text-gray-600 text-sm">Thanh toán toàn bộ đơn hàng ngay</p>
                        </div>
                      </label>
                    </div>
                  </div>
                )}
                <h3 className="font-semibold mb-3">Chọn phương thức thanh toán</h3>
                <div className="space-y-3">
                  {!requiresDeposit && (
                    <label className="flex items-center gap-3 p-4 border rounded cursor-pointer hover:border-orange-500">
                      <input type="radio" name="pay" value="cod" checked={paymentMethod === 'cod'} onChange={() => setPaymentMethod('cod')} />
                      <span className="font-medium">Thanh toán khi nhận hàng (COD)</span>
                    </label>
                  )}
                  <label className="flex items-center gap-3 p-4 border rounded cursor-pointer hover:border-orange-500">
                    <input type="radio" name="pay" value="bank_transfer" checked={paymentMethod === 'bank_transfer'} onChange={() => setPaymentMethod('bank_transfer')} />
                    <span className="font-medium">Chuyển khoản ngân hàng</span>
                  </label>
                </div>
                {paymentMethod === 'bank_transfer' && (
                  <div className="mt-6 p-4 border rounded-lg bg-gray-50 text-sm">
                    <h4 className="font-semibold mb-2">Thông tin chuyển khoản</h4>
                    <p>Ngân hàng: <strong>Vietcombank</strong></p>
                    <p>Số tài khoản: <strong>0123456789</strong></p>
                    <p>Chủ tài khoản: <strong>CÔNG TY TNHH THƯƠNG MẠI ABC</strong></p>
                    <p>Nội dung: <code className="bg-yellow-100 px-1 rounded">Mã đơn hàng</code></p>
                  </div>
                )}
                <div className="flex justify-between mt-6">
                  <button type="button" onClick={() => setCurrentStep(0)} className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50">
                    Quay lại
                  </button>
                  <button type="button" onClick={() => setCurrentStep(2)} className="px-4 py-2 bg-orange-500 text-white rounded-lg hover:bg-orange-600">
                    Tiếp tục
                  </button>
                </div>
              </div>
            )}

            {currentStep === 2 && (
              <div className="bg-white rounded-xl shadow border border-gray-200 p-6">
                <h2 className="text-lg font-semibold mb-4">Xác nhận đơn hàng</h2>
                <div className="space-y-6">
                  <div className="border rounded-lg p-4">
                    <h3 className="font-semibold mb-3">Tóm tắt đơn hàng</h3>
                    {cartItems.map((item) => (
                      <div key={item.id} className="flex justify-between py-2 border-b last:border-0">
                        <div>
                          <p>{item.product_data?.name ?? 'Sản phẩm'}</p>
                          <p className="text-sm text-gray-600">{item.quantity} × {formatVnd(item.product_data?.price ?? item.unit_price ?? 0)}</p>
                        </div>
                        <span className="font-semibold">{formatVnd(item.total_price)}</span>
                      </div>
                    ))}
                  </div>
                  <div className="border rounded-lg p-4">
                    <h3 className="font-semibold mb-3">Chi tiết thanh toán</h3>
                    <div className="space-y-2">
                      <div className="flex justify-between"><span>Tổng tiền hàng</span><span>{formatVnd(orderSummary.subtotal)}</span></div>
                      <div className="flex justify-between"><span>Phí vận chuyển</span><span>{formatVnd(orderSummary.shippingFee)}</span></div>
                      {requiresDeposit && (
                        <>
                          <hr className="my-2" />
                          <div className="flex justify-between text-blue-600">
                            <span>Tiền cọc ({depositType === 'percent_30' ? '30%' : '100%'})</span>
                            <span className="font-bold">{formatVnd(depositAmount)}</span>
                          </div>
                          <div className="flex justify-between"><span>Còn lại</span><span>{formatVnd(remainingAmount)}</span></div>
                        </>
                      )}
                      <hr className="my-2" />
                      <div className="flex justify-between text-lg font-bold">
                        <span>Tổng thanh toán</span>
                        <span className="text-red-600">{formatVnd(requiresDeposit ? depositAmount : orderSummary.total)}</span>
                      </div>
                    </div>
                  </div>
                  <div className="flex justify-between">
                    <button type="button" onClick={() => setCurrentStep(1)} className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50">
                      Quay lại
                    </button>
                    <button
                      type="button"
                      disabled={loading}
                      onClick={handlePlaceOrder}
                      className="px-6 py-2 bg-orange-500 text-white font-medium rounded-lg hover:bg-orange-600 disabled:opacity-50 flex items-center gap-2"
                    >
                      {loading && <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />}
                      {requiresDeposit ? 'Đặt hàng & Đặt cọc' : 'Đặt hàng ngay'}
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>

          <div>
            <div className="bg-white rounded-xl shadow border border-gray-200 p-6 sticky top-4">
              <h2 className="text-lg font-semibold mb-4">Đơn hàng của bạn</h2>
              <div className="space-y-4">
                {cartItems.map((item) => (
                  <div key={item.id} className="flex gap-3 border-b pb-3">
                    <div className="w-16 h-16 bg-gray-100 rounded overflow-hidden flex-shrink-0 relative">
                      {item.product_data?.main_image && (
                        <Image src={item.product_data.main_image} alt="" fill sizes="64px" className="object-cover" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm line-clamp-2">{item.product_data?.name ?? 'Sản phẩm'}</p>
                      <p className="text-gray-600 text-xs">{item.quantity} × {formatVnd(item.unit_price ?? item.product_data?.price ?? 0)}</p>
                    </div>
                  </div>
                ))}
                <div className="pt-4 border-t space-y-2">
                  <div className="flex justify-between text-sm"><span>Tạm tính</span><span>{formatVnd(orderSummary.subtotal)}</span></div>
                  <div className="flex justify-between text-sm"><span>Phí vận chuyển</span><span>{formatVnd(orderSummary.shippingFee)}</span></div>
                  {requiresDeposit && (
                    <div className="flex justify-between text-sm text-blue-600"><span>Tiền cọc</span><span className="font-bold">{formatVnd(depositAmount)}</span></div>
                  )}
                  <hr />
                  <div className="flex justify-between font-bold">
                    <span>Thanh toán</span>
                    <span className="text-red-600">{formatVnd(requiresDeposit ? depositAmount : orderSummary.total)}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
