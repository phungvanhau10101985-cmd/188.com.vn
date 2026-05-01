'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import Image from 'next/image';
import type { Product, ProductColor } from '@/types/api';
import { formatPrice } from '@/lib/utils';
import { getOptimizedImage } from '@/lib/image-utils';
import { apiClient } from '@/lib/api-client';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { colorLabelForCart, colorVariantKeyPart, colorEntryImageUrl } from '@/lib/product-color-variant';

/** Số tồn hiển thị (ảo) random 1–3 cho mỗi phiên bản. */
function getRandomDisplayStock(): number {
  return Math.floor(Math.random() * 3) + 1;
}

/** Key cho từng biến thể (màu theo chỉ số + size). */
function getVariantKey(colorPart: string, size: string): string {
  const c = colorPart || '';
  const s = size || '';
  if (c && s) return `${c}|${s}`;
  if (c) return c;
  if (s) return s;
  return 'default';
}

/** Danh sách key cho tất cả biến thể — màu dùng c0,c1,… để không gộp khi trùng tên. */
function getAllVariantKeys(colors: ProductColor[], sizes: string[]): string[] {
  const colorParts = colors.map((_, i) => colorVariantKeyPart(colors.length, i));
  if (colors.length > 0 && sizes.length > 0) {
    return colorParts.flatMap((cp) => sizes.map((s) => `${cp}|${s}`));
  }
  if (colors.length > 0) return colorParts;
  if (sizes.length > 0) return sizes.map((s) => s);
  return ['default'];
}

interface ProductVariantModalProps {
  product: Product;
  isOpen: boolean;
  onClose: () => void;
  onAddToCart: (p: Product, qty: number, size?: string, color?: string) => void;
  onBuyNow: (p: Product, qty: number, size?: string, color?: string) => void;
  isCartLoading: boolean;
  /** 'add' = chỉ hiện Thêm giỏ, 'buy' = chỉ hiện Mua hàng, 'both' = cả hai */
  action?: 'add' | 'buy' | 'both';
  /** Tồn ảo theo biến thể (key = productId_variantKey); từ parent để sau khi mua tồn = 0 vẫn giữ. */
  displayStockByVariant?: Record<string, number>;
  setDisplayStockByVariant?: React.Dispatch<React.SetStateAction<Record<string, number>>>;
}

export default function ProductVariantModal({
  product,
  isOpen,
  onClose,
  onAddToCart,
  onBuyNow,
  isCartLoading,
  action = 'both',
  displayStockByVariant: displayStockByVariantProp,
  setDisplayStockByVariant: setDisplayStockByVariantProp,
}: ProductVariantModalProps) {
  const [selectedSize, setSelectedSize] = useState('');
  /** Chỉ số vào `product.colors`; luôn phân biệt từng ô dù trùng `name`. */
  const [selectedColorIndex, setSelectedColorIndex] = useState(-1);
  const [quantity, setQuantity] = useState(1);
  const [confirmImageIndex, setConfirmImageIndex] = useState(0);
  const [displayStockByVariantLocal, setDisplayStockByVariantLocal] = useState<Record<string, number>>({});
  const displayStockByVariant = displayStockByVariantProp ?? displayStockByVariantLocal;
  const setDisplayStockByVariant = setDisplayStockByVariantProp ?? setDisplayStockByVariantLocal;
  const { isAuthenticated } = useAuth();
  const [loyaltyStatus, setLoyaltyStatus] = useState<any>(null);

  const sizes = useMemo(() => product.sizes || [], [product.sizes]);
  const colors = useMemo(() => product.colors || ([] as ProductColor[]), [product.colors]);
  const realStock = product.available ?? 0;
  const available = realStock > 0;

  useEffect(() => {
    if (isAuthenticated && isOpen) {
      apiClient.getMyLoyaltyStatus().then(setLoyaltyStatus).catch(() => {});
    }
  }, [isAuthenticated, isOpen]);

  const colorPart =
    colors.length > 0 && selectedColorIndex >= 0
      ? colorVariantKeyPart(colors.length, selectedColorIndex)
      : '';
  const variantKey = getVariantKey(colorPart, selectedSize);
  const cartColorLabel =
    selectedColorIndex >= 0 && colors.length > 0
      ? colorLabelForCart(colors, selectedColorIndex)
      : '';
  const fullKey = `${product.id}_${variantKey}`;
  const displayStockForVariant = available
    ? Math.max(1, displayStockByVariant[fullKey] ?? 1)
    : 0;
  /** Số lượng tối đa = min(tồn ảo, tồn thật). Tồn ảo còn 1 → maxQty=1 → vẫn mua được 1; chỉ tồn ảo=0 mới không mua được. */
  const maxQty = Math.min(displayStockForVariant, realStock);
  /** Số lượng hiệu lực: clamp theo maxQty. Tồn ảo còn 1 = vẫn mua được 1; tồn ảo=0 mới không mua được. */
  const effectiveQuantity = Math.min(Math.max(1, quantity), maxQty);
  /** Số còn lại hiển thị: khi số lượng = 1 thì không đổi; cộng lên 2 thì trừ 1 (đang 3 → còn 2). */
  const remainingDisplay = Math.max(0, displayStockForVariant - (effectiveQuantity - 1));

  const loyaltyDiscountPercent = loyaltyStatus?.current_tier?.discount_percent || 0;
  const loyaltyDiscountAmount = (product.price * loyaltyDiscountPercent * effectiveQuantity) / 100;
  const loyaltyTierName = loyaltyStatus?.current_tier?.name || 'L0';

  const images = [
    ...(product.main_image ? [product.main_image] : []),
    ...(product.images?.filter((img) => img !== product.main_image) || []),
  ];
  const mainDisplayImage =
    selectedColorIndex >= 0 && colors[selectedColorIndex]
      ? colorEntryImageUrl(colors[selectedColorIndex]) || images[confirmImageIndex] || product.main_image
      : images[confirmImageIndex] || product.main_image;

  useEffect(() => {
    if (isOpen) {
      setSelectedSize(sizes[0] || '');
      setSelectedColorIndex(colors.length > 0 ? 0 : -1);
      setQuantity(1);
      setConfirmImageIndex(0);
      const keys = getAllVariantKeys(colors, sizes);
      setDisplayStockByVariant((prev) => {
        const next = { ...prev };
        keys.forEach((vk) => {
          const key = `${product.id}_${vk}`;
          if (next[key] === undefined) {
            next[key] = getRandomDisplayStock();
          } else if (available && next[key] < 1) {
            next[key] = 1;
          }
        });
        return next;
      });
    }
  }, [isOpen, colors, sizes, product.id, available, setDisplayStockByVariant]);

  useEffect(() => {
    setQuantity(1);
  }, [selectedColorIndex, selectedSize]);

  useEffect(() => {
    setQuantity((q) => Math.min(q, maxQty));
  }, [maxQty]);

  const handleConfirmAddToCart = useCallback(() => {
    const qty = Math.min(Math.max(1, quantity), maxQty);
    setDisplayStockByVariant((prev) => ({
      ...prev,
      [fullKey]: Math.max(0, (prev[fullKey] ?? 0) - qty),
    }));
    onAddToCart(product, qty, selectedSize || undefined, cartColorLabel || undefined);
    onClose();
  }, [fullKey, quantity, maxQty, product, selectedSize, cartColorLabel, onAddToCart, onClose, setDisplayStockByVariant]);

  const handleConfirmBuyNow = useCallback(() => {
    const qty = Math.min(Math.max(1, quantity), maxQty);
    setDisplayStockByVariant((prev) => ({
      ...prev,
      [fullKey]: Math.max(0, (prev[fullKey] ?? 0) - qty),
    }));
    onBuyNow(product, qty, selectedSize || undefined, cartColorLabel || undefined);
    onClose();
  }, [fullKey, quantity, maxQty, product, selectedSize, cartColorLabel, onBuyNow, onClose, setDisplayStockByVariant]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center">
      <div
        className="absolute inset-0 bg-black/50"
        onClick={onClose}
        aria-hidden
      />
      <div
        className="relative w-full max-w-3xl max-h-[85vh] overflow-y-auto bg-white rounded-t-2xl sm:rounded-2xl shadow-xl animate-in slide-in-from-bottom duration-200"
        role="dialog"
        aria-modal="true"
        aria-labelledby="variant-modal-title"
      >
        {/* Header: nút đóng */}
        <div className="sticky top-0 z-10 flex justify-end h-8 bg-white border-b border-gray-100">
          <button
            type="button"
            onClick={onClose}
            className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-gray-100 text-gray-600"
            aria-label="Đóng"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="p-4 pb-32">
          <h2 id="variant-modal-title" className="sr-only">
            Chọn biến thể sản phẩm
          </h2>

          {/* Ảnh xác nhận to + mã sp, tên, giá, kho (desktop) */}
          <div className="hidden md:flex gap-4 mb-3">
            <div className="flex-shrink-0 w-1/2 aspect-square rounded-xl overflow-hidden bg-gray-100 border border-gray-200">
              <Image
                src={getOptimizedImage(mainDisplayImage, { width: 512, height: 512 })}
                alt={product.name}
                width={512}
                height={512}
                className="w-full h-full object-cover"
              />
            </div>
            <div className="flex-1 min-w-0 flex flex-col gap-0.5">
              <p className="text-[11px] text-gray-500">Mã sp: {product.code || product.product_id || '—'}</p>
              <p className="text-sm font-medium text-gray-900 line-clamp-2 leading-tight">{product.name}</p>
              <p className="text-base font-bold text-red-600 mt-0.5">{formatPrice(product.price)}</p>
              
              {realStock === 0 ? (
                <p className="text-[11px] font-medium text-red-600 flex items-center gap-1">
                  <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-red-100 text-red-600" aria-hidden>!</span>
                  Hết hàng
                </p>
              ) : maxQty === 0 ? (
                <p className="text-[11px] text-amber-700 flex items-center gap-1">
                  <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-amber-100 text-amber-600" aria-hidden>★</span>
                  Còn 0 — Biến thể này đã hết
                </p>
              ) : (
                <p className="text-[11px] text-amber-700 flex items-center gap-1">
                  <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-amber-100 text-amber-600" aria-hidden>★</span>
                  Còn {remainingDisplay} sản phẩm — Sắp hết hàng
                </p>
              )}

              {/* MÀU: các ảnh nhỏ để chọn màu/kiểu */}
              {colors.length > 0 && (
                <div className="mt-2">
                  <p className="text-xs font-semibold text-gray-900 mb-1.5">MÀU</p>
                  <div className="flex flex-wrap gap-1.5">
                    {colors.map((color, colorIndex) => {
                      const swatch = colorEntryImageUrl(color);
                      return (
                      <button
                        key={`color-${colorIndex}-${swatch || 'n'}`}
                        type="button"
                        onClick={() => setSelectedColorIndex(colorIndex)}
                        className={`flex items-center gap-1.5 rounded-xl border-2 p-1.5 transition-all ${
                          selectedColorIndex === colorIndex
                            ? 'border-[#ea580c] bg-orange-50'
                            : 'border-gray-200 hover:border-gray-300'
                        }`}
                      >
                        {swatch ? (
                          <div className="w-8 h-8 rounded-lg overflow-hidden flex-shrink-0 border border-gray-200 relative">
                            <Image
                              src={getOptimizedImage(swatch, { width: 64, height: 64 })}
                              alt=""
                              width={32}
                              height={32}
                              className="w-full h-full object-cover"
                            />
                          </div>
                        ) : (
                          <div className="w-8 h-8 rounded-lg bg-gray-200 flex-shrink-0" />
                        )}
                        <span className="text-xs font-medium text-gray-900 uppercase max-w-[100px] truncate">
                          {color.name}
                        </span>
                      </button>
                    );
                    })}
                  </div>
                </div>
              )}

              {/* SIZE + Hướng dẫn chọn kích cỡ */}
              {sizes.length > 0 && (
                <div className="mt-2">
                  <div className="flex items-center justify-between mb-1.5">
                    <p className="text-xs font-semibold text-gray-900">SIZE</p>
                    <a
                      href="/info/huong-dan-chon-size"
                      className="text-[11px] text-[#ea580c] hover:text-[#c2410c] font-medium"
                    >
                      Hướng dẫn chọn kích cỡ &gt;
                    </a>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {sizes.map((size) => (
                      <button
                        key={size}
                        type="button"
                        onClick={() => setSelectedSize(size)}
                        className={`min-w-10 px-2.5 py-1.5 border-2 rounded-lg text-xs font-medium transition-all ${
                          selectedSize === size
                            ? 'border-[#ea580c] bg-orange-50 text-orange-700'
                            : 'border-gray-300 text-gray-700 hover:border-gray-400'
                        }`}
                      >
                        {size}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Số lượng: - disabled khi =1; + disabled khi đã = maxQty (tồn ảo còn 1 thì maxQty=1, không cộng thêm được nhưng vẫn mua được 1; chỉ tồn ảo=0 mới không mua được). */}
              <div className="mt-2">
                <p className="text-xs font-semibold text-gray-900 mb-1.5">Số lượng</p>
                <div className="flex items-center gap-2.5">
                  <button
                    type="button"
                    onClick={() => setQuantity((q) => Math.max(1, q - 1))}
                    disabled={effectiveQuantity <= 1}
                    className="w-9 h-9 rounded-lg border-2 border-gray-300 flex items-center justify-center text-gray-600 hover:bg-gray-50 font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    -
                  </button>
                  <span className="w-10 text-center font-semibold text-gray-900">{effectiveQuantity}</span>
                  <button
                    type="button"
                    onClick={() => setQuantity((q) => Math.min(q + 1, maxQty))}
                    disabled={effectiveQuantity >= maxQty}
                    className="w-9 h-9 rounded-lg border-2 border-gray-300 flex items-center justify-center text-gray-600 hover:bg-gray-50 font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    +
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Ảnh xác nhận + thông tin (mobile) */}
          <div className="md:hidden mb-2">
            <div className="flex gap-3 mb-3">
              <div className="w-24 h-24 flex-shrink-0 rounded-lg overflow-hidden bg-gray-100 border border-gray-200">
                <Image
                  src={getOptimizedImage(mainDisplayImage, { width: 256, height: 256 })}
                  alt={product.name}
                  width={128}
                  height={128}
                  className="w-full h-full object-cover"
                />
              </div>
              <div className="flex-1 min-w-0 flex flex-col justify-between py-0.5">
                <div>
                  <p className="text-[10px] text-gray-500 mb-0.5">Mã: {product.code || product.product_id || '—'}</p>
                  <p className="text-sm font-medium text-gray-900 line-clamp-2 leading-tight mb-1">{product.name}</p>
                </div>
                <div>
                  <p className="text-base font-bold text-red-600">{formatPrice(product.price)}</p>
                  
                  {realStock === 0 ? (
                    <p className="text-[10px] font-medium text-red-600 flex items-center gap-1">
                      <span className="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-red-100 text-red-600" aria-hidden>!</span>
                      Hết hàng
                    </p>
                  ) : maxQty === 0 ? (
                    <p className="text-[10px] text-amber-700 flex items-center gap-1">
                      <span className="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-amber-100 text-amber-600" aria-hidden>★</span>
                      Hết hàng
                    </p>
                  ) : (
                    <p className="text-[10px] text-amber-700 flex items-center gap-1">
                      <span className="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-amber-100 text-amber-600" aria-hidden>★</span>
                      Còn {remainingDisplay}
                    </p>
                  )}
                </div>
              </div>
            </div>

            <div className="space-y-3">
              {/* MÀU */}
              {colors.length > 0 && (
                <div>
                  <p className="text-[11px] font-semibold text-gray-900 mb-1.5">MÀU</p>
                  <div className="flex flex-wrap gap-1.5">
                    {colors.map((color, colorIndex) => {
                      const swatch = colorEntryImageUrl(color);
                      return (
                      <button
                        key={`color-m-${colorIndex}-${swatch || 'n'}`}
                        type="button"
                        onClick={() => setSelectedColorIndex(colorIndex)}
                        className={`flex items-center gap-1.5 rounded-lg border p-1 pr-2 transition-all ${
                          selectedColorIndex === colorIndex
                            ? 'border-[#ea580c] bg-orange-50 ring-1 ring-[#ea580c]'
                            : 'border-gray-200 hover:border-gray-300'
                        }`}
                      >
                        {swatch ? (
                          <div className="w-9 h-9 rounded overflow-hidden flex-shrink-0 border border-gray-200 relative">
                            <Image
                              src={getOptimizedImage(swatch, { width: 72, height: 72 })}
                              alt=""
                              width={36}
                              height={36}
                              className="w-full h-full object-cover"
                            />
                          </div>
                        ) : (
                          <div className="w-9 h-9 rounded bg-gray-200 flex-shrink-0" />
                        )}
                        <span className="text-[11px] font-medium text-gray-900 uppercase max-w-[80px] truncate">
                          {color.name}
                        </span>
                      </button>
                    );
                    })}
                  </div>
                </div>
              )}

              {/* SIZE */}
              {sizes.length > 0 && (
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <p className="text-[11px] font-semibold text-gray-900">SIZE</p>
                    <a
                      href="/info/huong-dan-chon-size"
                      className="text-[10px] text-[#ea580c] hover:text-[#c2410c] font-medium"
                    >
                      Hướng dẫn chọn size &gt;
                    </a>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {sizes.map((size) => (
                      <button
                        key={size}
                        type="button"
                        onClick={() => setSelectedSize(size)}
                        className={`min-w-8 px-2 py-1 border rounded-md text-[11px] font-medium transition-all ${
                          selectedSize === size
                            ? 'border-[#ea580c] bg-orange-50 text-orange-700 ring-1 ring-[#ea580c]'
                            : 'border-gray-300 text-gray-700 hover:border-gray-400'
                        }`}
                      >
                        {size}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Số lượng */}
              <div>
                <p className="text-[11px] font-semibold text-gray-900 mb-1.5">Số lượng</p>
                <div className="flex items-center gap-3">
                  <div className="flex items-center border border-gray-300 rounded-lg">
                    <button
                      type="button"
                      onClick={() => setQuantity((q) => Math.max(1, q - 1))}
                      disabled={effectiveQuantity <= 1}
                      className="w-8 h-8 flex items-center justify-center text-gray-600 hover:bg-gray-50 disabled:opacity-50"
                    >
                      -
                    </button>
                    <span className="w-8 text-center text-sm font-semibold text-gray-900 border-x border-gray-300 h-8 flex items-center justify-center bg-gray-50">{effectiveQuantity}</span>
                    <button
                      type="button"
                      onClick={() => setQuantity((q) => Math.min(q + 1, maxQty))}
                      disabled={effectiveQuantity >= maxQty}
                      className="w-8 h-8 flex items-center justify-center text-gray-600 hover:bg-gray-50 disabled:opacity-50"
                    >
                      +
                    </button>
                  </div>
                  <span className="text-[10px] text-gray-500">
                    (Còn {remainingDisplay} sản phẩm)
                  </span>
                </div>
              </div>
            </div>
          </div>

        </div>
        {/* Sticky action buttons */}
        <div className="sticky bottom-0 z-10 bg-white border-t border-gray-200 p-3">
          {/* Loyalty Discount Message */}
          {isAuthenticated && loyaltyDiscountAmount > 0 && (
            <div className="bg-green-50 border border-green-100 rounded-lg px-3 py-2 mb-3 text-center">
              <span className="text-xs text-green-700 font-medium flex items-center justify-center gap-1.5">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" /></svg>
                Hạng <strong>{loyaltyTierName}</strong> giảm <strong>{formatPrice(loyaltyDiscountAmount)}</strong> khi mua hàng
              </span>
            </div>
          )}

          <div className="flex flex-row gap-2">
            {(action === 'add' || action === 'both') && (
              <button
                type="button"
                onClick={handleConfirmAddToCart}
                disabled={!available || maxQty === 0 || effectiveQuantity < 1 || isCartLoading}
                className="flex-1 py-3.5 rounded-xl font-semibold text-sm bg-gray-500 text-white hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {!available ? 'Hết hàng' : maxQty === 0 ? 'Hết hàng' : isCartLoading ? 'Đang thêm...' : 'Thêm vào Giỏ hàng'}
              </button>
            )}
            {(action === 'buy' || action === 'both') && (
              <button
                type="button"
                onClick={handleConfirmBuyNow}
                disabled={!available || maxQty === 0 || effectiveQuantity < 1 || isCartLoading}
                className="flex-1 py-3.5 rounded-xl font-semibold text-sm bg-[#ea580c] text-white hover:bg-[#c2410c] disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {!available ? 'Hết hàng' : maxQty === 0 ? 'Hết hàng' : isCartLoading ? 'Đang xử lý...' : 'Mua hàng'}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
