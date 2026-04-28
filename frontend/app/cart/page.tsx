// app/cart/page.tsx - WITH ADDRESS BOOK & CHECKOUT
'use client';

import { useState, useEffect } from 'react';
import Image from 'next/image';
import { useCart } from '@/features/cart/hooks/useCart';
import { apiClient } from '@/lib/api-client';
import { useAuth } from '@/features/auth/hooks/useAuth';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import type { UserAddress, AddressCreateInput } from '@/types/api';
import { VIETNAM_PROVINCES } from '@/lib/vietnam-provinces';
import { getOptimizedImage } from '@/lib/image-utils';
import { useToast } from '@/components/ToastProvider';
import { trackEvent } from '@/lib/analytics';
import { shouldRedirectToDepositAfterCreate } from '@/lib/order-deposit';

function formatAddressLine(addr: UserAddress): string {
  const parts = [addr.street_address];
  if (addr.ward) parts.push(addr.ward);
  if (addr.district) parts.push(addr.district);
  if (addr.province) parts.push(addr.province);
  return parts.join(', ');
}

export default function CartPage() {
  const { cart, updateCartItem, removeFromCart, clearCart, isLoading, error } = useCart();
  const { isAuthenticated, user } = useAuth();
  const router = useRouter();
  const { pushToast } = useToast();
  const [isCheckingOut, setIsCheckingOut] = useState(false);
  const [addresses, setAddresses] = useState<UserAddress[]>([]);
  const [selectedAddressId, setSelectedAddressId] = useState<number | null>(null);
  const [showAddAddress, setShowAddAddress] = useState(false);
  const [savingAddress, setSavingAddress] = useState(false);
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [addressForm, setAddressForm] = useState<AddressCreateInput>({
    full_name: user?.full_name ?? '',
    phone: user?.phone ?? '',
    province: '',
    district: '',
    ward: '',
    street_address: '',
    is_default: false,
  });

  useEffect(() => {
    if (isAuthenticated) {
      apiClient.getAddresses().then(setAddresses).catch(() => setAddresses([]));
    }
  }, [isAuthenticated]);

  useEffect(() => {
    if (addresses.length > 0 && selectedAddressId == null) {
      const defaultAddr = addresses.find((a) => a.is_default) ?? addresses[0];
      setSelectedAddressId(defaultAddr.id);
    }
  }, [addresses, selectedAddressId]);

  useEffect(() => {
    if (user) {
      setAddressForm((f) => ({
        ...f,
        full_name: (f.full_name || user.full_name) ?? '',
        phone: (f.phone || user.phone) ?? '',
      }));
    }
  }, [user]);

  const hasDepositRequired =
    cart?.requires_deposit === true ||
    (cart?.items ?? []).some(
      (item: { requires_deposit?: boolean; product_data?: { deposit_require?: boolean } }) =>
        item.requires_deposit === true || item.product_data?.deposit_require === true
    ) ||
    false;

  const selectedAddress = addresses.find((a) => a.id === selectedAddressId);
  const customerAddressLine = selectedAddress
    ? formatAddressLine(selectedAddress)
    : '';

  // Backend dùng cart_item id (item.id), guest cart dùng product_id
  const getItemId = (item: { id: number; product_id: number }) =>
    isAuthenticated ? item.id : item.product_id;

  const handleQuantityChange = async (item: { id: number; product_id: number }, newQuantity: number) => {
    if (newQuantity < 1) return;
    await updateCartItem(getItemId(item), { quantity: newQuantity });
  };

  const handleRemoveItem = async (item: { id: number; product_id: number }) => {
    await removeFromCart(getItemId(item));
  };

  const handleClearCart = async () => {
    setShowClearConfirm(true);
  };

  const confirmClearCart = async () => {
    try {
      await clearCart();
      pushToast({ title: 'Đã xóa giỏ hàng', variant: 'success', durationMs: 2500 });
    } catch (err: any) {
      pushToast({ title: 'Không thể xóa giỏ hàng', description: err?.message || 'Vui lòng thử lại', variant: 'error', durationMs: 3000 });
    } finally {
      setShowClearConfirm(false);
    }
  };

  const openAddAddressModal = () => {
    setAddressForm({
      full_name: user?.full_name ?? '',
      phone: user?.phone ?? '',
      province: '',
      district: '',
      ward: '',
      street_address: '',
      is_default: addresses.length === 0,
    });
    setShowAddAddress(true);
  };

  const handleAddAddressSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingAddress(true);
    try {
      const newAddr = await apiClient.createAddress({
        ...addressForm,
        is_default: addressForm.is_default,
      });
      setAddresses((prev) => [...prev, newAddr]);
      setSelectedAddressId(newAddr.id);
      setShowAddAddress(false);
      setAddressForm({
        full_name: user?.full_name ?? '',
        phone: user?.phone ?? '',
        province: '',
        district: '',
        ward: '',
        street_address: '',
        is_default: false,
      });
    } catch (err: any) {
      pushToast({ title: 'Không thể lưu địa chỉ', description: err?.message || 'Vui lòng thử lại', variant: 'error', durationMs: 3000 });
    } finally {
      setSavingAddress(false);
    }
  };

  const handleCheckout = async () => {
    if (!isAuthenticated) {
      trackEvent('begin_checkout', { status: 'guest_redirect_checkout' });
      router.push('/checkout');
      return;
    }
    if (!cart || !Array.isArray(cart.items) || cart.items.length === 0) return;
    if (!selectedAddress) {
      pushToast({ title: 'Vui lòng chọn địa chỉ giao hàng', variant: 'info', durationMs: 2500 });
      return;
    }
    const accountEmail = (user?.email || '').trim();
    if (!accountEmail) {
      pushToast({
        title: 'Thiếu email',
        description: 'Vui lòng cập nhật email trong tài khoản để đặt hàng.',
        variant: 'error',
        durationMs: 3500,
      });
      return;
    }

    const depositType = hasDepositRequired ? 'percent_30' : undefined;

    setIsCheckingOut(true);
    try {
      trackEvent('begin_checkout', { status: 'start', item_count: cart.items.length });
      const order = await apiClient.createOrderFull({
        customer_name: selectedAddress.full_name,
        customer_phone: selectedAddress.phone,
        customer_email: accountEmail,
        customer_address: customerAddressLine,
        customer_note: undefined,
        payment_method: hasDepositRequired ? 'bank_transfer' : 'cod',
        shipping_method: 'standard',
        deposit_type: depositType,
        items: (cart.items ?? []).map((item) => ({
          product_id: item.product_id,
          quantity: item.quantity,
          selected_size: item.selected_size ?? undefined,
          selected_color: item.selected_color ?? undefined,
        })),
      });

      await clearCart();
      trackEvent('purchase', { order_id: order.id, value: cart.total_price ?? 0, item_count: cart.items.length });
      router.push(
        shouldRedirectToDepositAfterCreate(order as { requires_deposit?: boolean; status?: string })
          ? `/account/orders/${order.id}/deposit`
          : `/account/orders/${order.id}`
      );
    } catch (err: unknown) {
      const message = (err as Error)?.message || 'Đặt hàng thất bại';
      pushToast({ title: 'Đặt hàng thất bại', description: message, variant: 'error', durationMs: 3500 });
      trackEvent('purchase', { status: 'failed', error: message });
    } finally {
      setIsCheckingOut(false);
    }
  };

  const handleOpenProduct = async (item: { product_id: number; product_data?: any }) => {
    const slug = item.product_data?.slug;
    if (slug) {
      router.push(`/products/${slug}`);
      return;
    }
    try {
      const p = await apiClient.getProductById(item.product_id);
      if (p?.slug) {
        router.push(`/products/${p.slug}`);
      }
    } catch {
      // ignore
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 py-8">
        <div className="max-w-4xl mx-auto px-4">
          <div className="animate-pulse">
            <div className="h-8 bg-gray-200 rounded w-1/4 mb-8"></div>
            {[...Array(3)].map((_, i) => (
              <div key={i} className="bg-white rounded-lg shadow-sm p-6 mb-4">
                <div className="flex space-x-4">
                  <div className="w-24 h-24 bg-gray-200 rounded"></div>
                  <div className="flex-1 space-y-3">
                    <div className="h-4 bg-gray-200 rounded w-3/4"></div>
                    <div className="h-4 bg-gray-200 rounded w-1/2"></div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (!cart || !Array.isArray(cart.items) || cart.items.length === 0) {
    return (
      <div className="min-h-screen bg-gray-50 py-16">
        <div className="max-w-2xl mx-auto px-4 text-center">
          <div className="bg-white rounded-2xl shadow-sm p-12">
            <div className="w-24 h-24 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-6">
              <svg className="w-12 h-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" />
              </svg>
            </div>
            <h1 className="text-2xl font-bold text-gray-900 mb-4">Giỏ hàng trống</h1>
            <p className="text-gray-600 mb-8">Bạn chưa có sản phẩm nào trong giỏ hàng.</p>
            <Link 
              href="/"
              className="inline-flex items-center px-6 py-3 bg-[#ea580c] text-white font-semibold rounded-lg hover:bg-[#c2410c] transition-colors"
            >
              Tiếp tục mua sắm
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold text-gray-900">Giỏ hàng</h1>
          <p className="text-sm text-gray-500">Bạn đang có {(cart?.items ?? []).length} sản phẩm</p>
        </div>
        <button
          onClick={handleClearCart}
          className="self-start md:self-auto inline-flex items-center gap-2 text-red-600 hover:text-red-700 text-sm font-medium"
        >
          Xóa tất cả
        </button>
      </div>

      <div className="space-y-6">
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
            {error}
          </div>
        )}
        {isAuthenticated && (
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 md:p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Địa chỉ giao hàng</h3>
            {addresses.length === 0 ? (
              <p className="text-gray-500 text-sm mb-3">Chưa có địa chỉ. Thêm địa chỉ để thanh toán.</p>
            ) : (
              <div className="space-y-2 mb-3">
                {addresses.map((addr) => (
                  <label key={addr.id} className="flex items-start gap-3 p-3 border border-gray-200 rounded-lg cursor-pointer hover:bg-gray-50 has-[:checked]:border-[#ea580c] has-[:checked]:bg-orange-50/40">
                    <input
                      type="radio"
                      name="shipping_address"
                      checked={selectedAddressId === addr.id}
                      onChange={() => setSelectedAddressId(addr.id)}
                      className="mt-1 text-[#ea580c]"
                    />
                    <div>
                      <span className="font-medium text-gray-900">{addr.full_name}</span>
                      <span className="text-gray-500 ml-2">{addr.phone}</span>
                      {addr.is_default && (
                        <span className="ml-2 text-xs bg-orange-100 text-[#ea580c] px-1.5 py-0.5 rounded">Mặc định</span>
                      )}
                      <p className="text-sm text-gray-600 mt-0.5">{formatAddressLine(addr)}</p>
                    </div>
                  </label>
                ))}
              </div>
            )}
            <div className="flex items-center gap-4">
              <button
                type="button"
                onClick={openAddAddressModal}
                className="text-[#ea580c] font-medium text-sm hover:text-[#c2410c]"
              >
                + Thêm địa chỉ mới
              </button>
              <Link href="/account/addresses" className="text-gray-500 text-sm hover:text-gray-700">
                Quản lý sổ địa chỉ
              </Link>
            </div>
          </div>
        )}

        <div className="bg-white rounded-2xl shadow-sm overflow-hidden border border-gray-100">
            <div className="hidden md:grid grid-cols-[1fr_120px_120px_120px_40px] gap-3 px-5 py-3 text-xs font-semibold text-gray-500 uppercase bg-gray-50">
              <span>Sản phẩm</span>
              <span className="text-right">Đơn giá</span>
              <span className="text-center">Số lượng</span>
              <span className="text-right">Thành tiền</span>
              <span />
            </div>
            <div className="divide-y divide-gray-100">
              {(cart?.items ?? []).map((item) => {
                const price = item.unit_price ?? item.product_data?.price ?? 0;
                const lineTotal = price * item.quantity;
                return (
                  <div key={item.id} className="px-3 md:px-5 py-3 md:py-4">
                    <div className="grid grid-cols-1 md:grid-cols-[1fr_120px_120px_120px_40px] gap-3 items-center">
                      <div className="flex gap-4 items-center">
                        <button
                          type="button"
                          onClick={() => handleOpenProduct(item)}
                          className="flex-shrink-0 w-16 h-16 md:w-20 md:h-20 bg-gray-100 rounded-xl overflow-hidden relative"
                          aria-label="Xem chi tiết sản phẩm"
                        >
                          {item.product_data?.main_image ? (
                            <Image
                              src={getOptimizedImage(item.product_data?.main_image, { width: 80, height: 80, fallbackStrategy: 'local' })}
                              alt={item.product_data?.name ?? 'Sản phẩm'}
                              fill
                              sizes="80px"
                              className="object-cover"
                            />
                          ) : (
                            <div className="w-full h-full bg-gray-200 flex items-center justify-center">
                              <span className="text-xs text-gray-500">No Img</span>
                            </div>
                          )}
                        </button>
                        <div className="min-w-0">
                          <button
                            type="button"
                            onClick={() => handleOpenProduct(item)}
                            className="text-left text-base md:text-lg font-semibold text-gray-900 line-clamp-2 hover:text-[#ea580c] transition-colors"
                          >
                            {item.product_data?.name ?? 'Sản phẩm'}
                          </button>
                          {(item.selected_size || item.selected_color || item.product_data?.product_id) && (
                            <p className="text-xs md:text-sm text-gray-500 mt-1">
                              {item.selected_size && `Size: ${item.selected_size}`}
                              {item.selected_size && (item.selected_color || item.product_data?.product_id) && ' • '}
                              {item.selected_color && `Màu: ${item.selected_color}`}
                              {item.selected_color && item.product_data?.product_id && ' • '}
                              {item.product_data?.product_id && `ID: ${item.product_data?.product_id}`}
                            </p>
                          )}
                        </div>
                      </div>

                      <div className="text-right">
                        <p className="text-sm md:text-base font-semibold text-gray-900 whitespace-nowrap">
                          {new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(price)}
                        </p>
                      </div>

                      <div className="flex items-center justify-start md:justify-center">
                        <div className="inline-flex items-center border border-gray-200 rounded-full">
                          <button
                            onClick={() => handleQuantityChange(item, item.quantity - 1)}
                            disabled={item.quantity <= 1}
                            className="w-9 h-9 flex items-center justify-center text-gray-600 hover:bg-gray-50 disabled:opacity-50"
                          >
                            -
                          </button>
                          <span className="w-10 text-center text-sm font-semibold text-gray-900">
                            {item.quantity}
                          </span>
                          <button
                            onClick={() => handleQuantityChange(item, item.quantity + 1)}
                            className="w-9 h-9 flex items-center justify-center text-gray-600 hover:bg-gray-50"
                          >
                            +
                          </button>
                        </div>
                      </div>

                      <div className="text-right">
                        <p className="text-sm md:text-base font-bold text-[#ea580c] whitespace-nowrap">
                          {new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(lineTotal)}
                        </p>
                      </div>

                      <div className="flex md:justify-end">
                        <button
                          onClick={() => handleRemoveItem(item)}
                          className="text-gray-400 hover:text-red-600"
                        >
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
          <div className="border-t border-gray-100 bg-gray-50 px-4 py-3 md:px-5 md:py-4">
            {/* Loyalty Discount */}
            {cart?.loyalty_discount_amount && cart.loyalty_discount_amount > 0 ? (
              <div className="flex items-center justify-between mb-1 text-[11px] md:text-sm">
                <span className="text-gray-500">
                  Giảm giá hạng <span className="font-bold text-blue-600">{cart.loyalty_tier_name}</span>
                </span>
                <span className="font-medium text-green-600">
                  -{new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(cart.loyalty_discount_amount)}
                </span>
              </div>
            ) : null}

            <div className="flex items-center justify-between">
              <span className="text-sm md:text-base font-semibold text-gray-900">Tổng thanh toán</span>
              <span className="text-lg md:text-xl font-bold text-[#ea580c]">
                {new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(cart?.final_price ?? cart?.total_price ?? 0)}
              </span>
            </div>
            <div className="mt-4 flex flex-col md:flex-row gap-3">
              <Link
                href="/"
                className="w-full md:w-1/2 bg-gray-100 border border-gray-200 text-gray-700 font-semibold py-3 rounded-lg hover:bg-gray-200 text-center transition-colors"
              >
                Mua sắm tiếp
              </Link>
              <button
                onClick={handleCheckout}
                disabled={isCheckingOut}
                className="w-full md:w-1/2 bg-[#ea580c] text-white font-semibold py-3 rounded-lg hover:bg-[#c2410c] transition-colors disabled:opacity-70"
              >
                {isCheckingOut ? 'Đang xử lý...' : 'Đặt hàng'}
              </button>
            </div>
          </div>
        </div>
      </div>

      {showAddAddress && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
          <div className="bg-white rounded-2xl shadow-xl max-w-lg w-full max-h-[90vh] overflow-y-auto">
            <div className="p-6">
              <div className="flex items-start justify-between gap-3 mb-4">
                <div className="min-w-0">
                  <h3 className="text-lg font-semibold text-gray-900">Thêm địa chỉ giao hàng</h3>
                  <p className="text-sm text-gray-500 mt-1">Địa chỉ sẽ được lưu vào Sổ địa chỉ của bạn.</p>
                </div>
                <button
                  type="button"
                  onClick={() => setShowAddAddress(false)}
                  className="shrink-0 rounded-lg p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-800 focus:outline-none focus:ring-2 focus:ring-orange-500 focus:ring-offset-2"
                  aria-label="Đóng"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              <form onSubmit={handleAddAddressSubmit} className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Họ và tên *</label>
                    <input
                      type="text"
                      required
                      value={addressForm.full_name}
                      onChange={(e) => setAddressForm((f) => ({ ...f, full_name: e.target.value }))}
                      className="w-full rounded-lg border border-gray-300 px-3 py-2"
                      placeholder="Nguyễn Văn A"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Số điện thoại *</label>
                    <input
                      type="tel"
                      required
                      value={addressForm.phone}
                      onChange={(e) => setAddressForm((f) => ({ ...f, phone: e.target.value }))}
                      className="w-full rounded-lg border border-gray-300 px-3 py-2"
                      placeholder="0912345678"
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Tỉnh / Thành phố</label>
                  <select
                    value={addressForm.province}
                    onChange={(e) => setAddressForm((f) => ({ ...f, province: e.target.value }))}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2"
                  >
                    <option value="">— Chọn —</option>
                    {VIETNAM_PROVINCES.map((p) => (
                      <option key={p} value={p}>{p}</option>
                    ))}
                  </select>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Quận / Huyện</label>
                    <input
                      type="text"
                      value={addressForm.district}
                      onChange={(e) => setAddressForm((f) => ({ ...f, district: e.target.value }))}
                      className="w-full rounded-lg border border-gray-300 px-3 py-2"
                      placeholder="Quận 1"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Phường / Xã</label>
                    <input
                      type="text"
                      value={addressForm.ward}
                      onChange={(e) => setAddressForm((f) => ({ ...f, ward: e.target.value }))}
                      className="w-full rounded-lg border border-gray-300 px-3 py-2"
                      placeholder="Phường..."
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Địa chỉ cụ thể *</label>
                  <input
                    type="text"
                    required
                    value={addressForm.street_address}
                    onChange={(e) => setAddressForm((f) => ({ ...f, street_address: e.target.value }))}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2"
                    placeholder="Số nhà, tên đường..."
                  />
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="cart_addr_default"
                    checked={addressForm.is_default}
                    onChange={(e) => setAddressForm((f) => ({ ...f, is_default: e.target.checked }))}
                    className="rounded border-gray-300 text-[#ea580c]"
                  />
                  <label htmlFor="cart_addr_default" className="text-sm text-gray-700">Đặt làm mặc định</label>
                </div>
                <div className="flex gap-3 pt-2">
                  <button
                    type="submit"
                    disabled={savingAddress}
                    className="px-4 py-2 bg-[#ea580c] text-white font-medium rounded-lg hover:bg-[#c2410c] disabled:opacity-70"
                  >
                    {savingAddress ? 'Đang lưu...' : 'Lưu vào sổ địa chỉ'}
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowAddAddress(false)}
                    className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50"
                  >
                    Hủy
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}
      {showClearConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setShowClearConfirm(false)}>
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6 mx-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-bold text-gray-900 mb-2">Xóa giỏ hàng</h3>
            <p className="text-gray-600 text-sm mb-6">Bạn chắc chắn muốn xóa toàn bộ sản phẩm trong giỏ?</p>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowClearConfirm(false)} className="px-4 py-2 border rounded-lg hover:bg-gray-50">
                Hủy
              </button>
              <button onClick={confirmClearCart} className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700">
                Xóa giỏ hàng
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
