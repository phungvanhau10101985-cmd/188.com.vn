// app/cart/page.tsx - WITH ADDRESS BOOK & CHECKOUT
'use client';

import { useState, useEffect, useMemo, useRef } from 'react';
import Image from 'next/image';
import { useCart } from '@/features/cart/hooks/useCart';
import { apiClient } from '@/lib/api-client';
import { useAuth } from '@/features/auth/hooks/useAuth';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import Button from '@/components/ui/Button';
import LoadingLink from '@/components/ui/LoadingLink';
import type { UserAddress, AddressCreateInput } from '@/types/api';
import { VIETNAM_PROVINCES } from '@/lib/vietnam-provinces';
import { getStoredReferralCode } from '@/lib/affiliate-ref';
import { trackEvent } from '@/lib/analytics';
import { trackMetaOrderAwaitingDeposit, trackMetaPurchase, trackMetaInitiateCheckout } from '@/lib/meta-pixel';
import {
  trackTikTokCompletePayment,
  trackTikTokInitiateCheckout,
  trackTikTokPlaceAnOrder,
} from '@/lib/tiktok-pixel';
import {
  trackGoogleAdsCartPageView,
  trackGoogleAdsOrderAwaitingDeposit,
  trackGoogleAdsPurchase,
  peekGoogleAdsConversionsFingerprint,
} from '@/lib/google-ads-gtag';
import { shouldRedirectToDepositAfterCreate } from '@/lib/order-deposit';
import { markGoogleCustomerReviewsForOrder } from '@/lib/google-customer-reviews';
import { buildAuthLoginHrefFromFullPath } from '@/lib/auth-redirect';
import { isClientAuthLikelyLoggedIn, probeCookieAuthSession } from '@/lib/client-auth-session';
import type { CartLineRef } from '@/features/cart/types/cart';
import CartLineThumbnail from '@/components/cart/CartLineThumbnail';
import CartEmptySameShopSection from '@/components/cart/CartEmptySameShopSection';
import { productPathSlugFromApi } from '@/lib/product-path-slug';
import BirthdayPromoBanner from '@/components/BirthdayPromoBanner';
import SiteSaleBanner from '@/components/SiteSaleBanner';
import SiteSaleLiveCountdown from '@/components/SiteSaleLiveCountdown';
import CartVoucherPicker from '@/components/cart/CartVoucherPicker';
import {
  calendarSaleProgramLabel,
  cartLineHasActiveFlash,
  FLASH_SALE_PROGRAM_NAME,
  liveCalendarState,
  mergeCartLineSiteSaleFromCalendar,
  nextCartSaleRefreshAtMs,
  resolveCartLineCheckoutTotal,
  resolveCartLineDisplayPricing,
  siteSaleProgramLabel,
  stackedSaleProgramLabel,
  sumCartLineCalendarSaleSavings,
  sumCartLineCheckoutTotals,
  sumCartLineClearanceSavings,
  sumCartLineFlashSaleSavings,
  sumCartLineListSubtotal,
  WAREHOUSE_SALE_PROGRAM_NAME,
} from '@/lib/site-sale';
import {
  cartLineMaxQuantity,
  isWarehouseCartLine,
  resolveWarehouseCartPdpSlug,
} from '@/lib/warehouse-clearance';
import { useSiteSale } from '@/lib/use-site-sale';
import { formatPrice } from '@/lib/utils';
import type { PromotionVoucherItem } from '@/lib/api-client';
import {
  getActiveGoogleAutomatedDiscountToken,
  googleDiscountPercentFromPricing,
  isGoogleDiscountCartLine,
} from '@/lib/google-automated-discount';
import {
  calculateWelcomeDiscount,
  WELCOME_PROMO_CODE,
  type AppliedWelcomePromo,
} from '@/lib/welcome-promo';
import { applyGrandOrderDiscountCap, lineProgramSavingsFromList, MAX_ORDER_DISCOUNT_PERCENT, resolveCappedPromoPercentDisplay } from '@/lib/order-discount-limits';
import { BIRTHDAY_PROGRAM_NAME } from '@/lib/birthday-discount';
import CappedPromoPercentLabel from '@/components/cart/CappedPromoPercentLabel';
import {
  computeShippingFee,
  DEPOSIT_PERCENT,
  PURCHASE_GUIDE_URL,
  RETURN_POLICY_URL,
  SHIPPING_POLICY_URL,
  TERMS_URL,
} from '@/lib/business-info';
import { useToast } from '@/components/ToastProvider';

function formatAddressLine(addr: UserAddress): string {
  const parts = [addr.street_address];
  if (addr.ward) parts.push(addr.ward);
  if (addr.district) parts.push(addr.district);
  if (addr.province) parts.push(addr.province);
  return parts.join(', ');
}

/** Skeleton thống nhất SSR + client — tránh mismatch khi CartProvider còn state sau soft-nav. */
function CartPageSkeleton() {
  return (
    <div className="min-h-screen bg-gray-50">
      <div className="mx-auto max-w-7xl px-3 pb-5 pt-2 sm:px-3 md:px-4 md:py-8 md:pb-6 md:pt-3">
        <div className="animate-pulse">
          <div className="mb-3 h-5 max-w-[8rem] rounded-md bg-gray-200 sm:h-6 md:mb-8 md:h-8 md:max-w-[12rem]" />
          {[...Array(3)].map((_, i) => (
            <div
              key={i}
              className="mb-3 rounded-xl border border-gray-100 bg-white p-4 shadow-sm md:mb-4 md:rounded-lg md:p-6"
            >
              <div className="flex gap-4">
                <div className="h-20 w-20 shrink-0 rounded-lg bg-gray-200 md:h-24 md:w-24" />
                <div className="min-w-0 flex-1 space-y-2 md:space-y-3">
                  <div className="h-4 rounded bg-gray-200 md:w-3/4" />
                  <div className="h-4 rounded bg-gray-200 md:w-1/2" />
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function CartPage() {
  const { cart, updateCartItem, removeFromCart, clearCart, isLoading, error, refreshCart } = useCart();
  const { isAuthenticated, user, isLoading: authLoading } = useAuth();
  const { state: globalSiteSale, reload: reloadSiteSale } = useSiteSale();
  const router = useRouter();
  const { pushToast } = useToast();
  const [pageReady, setPageReady] = useState(false);
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

  const [selectedItemIds, setSelectedItemIds] = useState<Set<number>>(new Set());
  const prevCartLineIdsRef = useRef<Set<number>>(new Set());
  const [walletBalance, setWalletBalance] = useState(0);
  const [useWallet, setUseWallet] = useState(false);
  const [appliedPromo, setAppliedPromo] = useState<AppliedWelcomePromo | null>(null);
  const [promoApplying, setPromoApplying] = useState(false);
  const [promoError, setPromoError] = useState<string | null>(null);
  const [promoVouchers, setPromoVouchers] = useState<PromotionVoucherItem[]>([]);
  const [promoVouchersLoading, setPromoVouchersLoading] = useState(false);
  const latestQtyByIdRef = useRef<Map<number, number>>(new Map());
  const [qtyDrafts, setQtyDrafts] = useState<Record<number, string>>({});
  const [saleClockMs, setSaleClockMs] = useState(() => Date.now());

  useEffect(() => {
    setPageReady(true);
  }, []);

  useEffect(() => {
    let cancelled = false;

    const loadCartAccountData = () => {
      apiClient.getAddresses().then(setAddresses).catch(() => setAddresses([]));
      apiClient
        .getAffiliateMe()
        .then((me) => setWalletBalance(Number(me.balance) || 0))
        .catch(() => setWalletBalance(0));
    };

    (async () => {
      if (isClientAuthLikelyLoggedIn(isAuthenticated, authLoading)) {
        loadCartAccountData();
        return;
      }
      if (authLoading) return;

      const probed = await probeCookieAuthSession();
      if (cancelled) return;
      if (probed?.user) {
        window.dispatchEvent(new Event('188-auth-session-changed'));
        return;
      }

      router.replace(buildAuthLoginHrefFromFullPath('/cart'));
    })();

    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, authLoading, router]);

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

  const cartItems = cart?.items ?? [];
  const cartLineIdKey = useMemo(
    () =>
      cartItems
        .map((i) => i.id)
        .slice()
        .sort((a, b) => a - b)
        .join(','),
    [cartItems]
  );

  useEffect(() => {
    const idsOnServer = cartItems.map((i) => i.id);
    const currentIdSet = new Set(idsOnServer);
    const prevSnapshot = prevCartLineIdsRef.current;

    setSelectedItemIds((prevSelected) => {
      const next = new Set<number>();
      for (const id of idsOnServer) {
        const existedBefore = prevSnapshot.has(id);
        const wasSelected = prevSelected.has(id);
        if (!existedBefore) next.add(id);
        else if (wasSelected) next.add(id);
      }
      return next;
    });

    prevCartLineIdsRef.current = currentIdSet;
  }, [cartLineIdKey]);

  const selectionForTotals = useMemo(() => selectedItemIds, [selectedItemIds]);

  const selectedCartItems = useMemo(
    () => cartItems.filter((i) => selectionForTotals.has(i.id)),
    [cartItems, selectionForTotals]
  );
  const selectedRegularItems = useMemo(
    () => selectedCartItems.filter((i) => !isWarehouseCartLine(i)),
    [selectedCartItems],
  );
  const selectedWarehouseItems = useMemo(
    () => selectedCartItems.filter((i) => isWarehouseCartLine(i)),
    [selectedCartItems],
  );
  const selectedFulfillmentSources = useMemo(
    () =>
      new Set(
        selectedCartItems.map((item) =>
          item.product_data?.fulfillment_source === 'china' ? 'china' : 'vietnam',
        ),
      ),
    [selectedCartItems],
  );
  const isMixedFulfillment = selectedFulfillmentSources.size > 1;
  const noneSelected = selectedCartItems.length === 0;
  const hasRegularSelection = selectedRegularItems.length > 0;
  const hasWarehouseSelection = selectedWarehouseItems.length > 0;

  const loyaltyPercent = cart?.loyalty_discount_percent ?? 0;
  const welcomeApplied = appliedPromo !== null;
  const birthdayActive = cart?.birthday_discount_active === true;
  const birthdayPercent = cart?.birthday_discount_percent ?? 0;
  const birthdayLineActive = birthdayActive && !welcomeApplied && birthdayPercent > 0;
  const siteSaleState = liveCalendarState(cart?.site_sale ?? globalSiteSale ?? null, saleClockMs);
  const siteSaleActive = siteSaleState?.phase === 'active';
  const siteSaleTeaser = siteSaleState?.phase === 'teaser';
  const cartFlashLine = useMemo(
    () =>
      cartItems
        .map((item) => mergeCartLineSiteSaleFromCalendar(item, siteSaleState))
        .find((item) => cartLineHasActiveFlash(item)),
    [cartItems, siteSaleState],
  );
  const cartHasFlash = Boolean(cartFlashLine);

  const regularSubtotal = useMemo(
    () => sumCartLineCheckoutTotals(selectedRegularItems, siteSaleState),
    [selectedRegularItems, siteSaleState],
  );
  const warehouseSubtotal = useMemo(
    () => sumCartLineCheckoutTotals(selectedWarehouseItems, siteSaleState),
    [selectedWarehouseItems, siteSaleState],
  );
  const selectedSubtotal = regularSubtotal + warehouseSubtotal;

  const regularListSubtotal = useMemo(
    () => sumCartLineListSubtotal(selectedRegularItems, siteSaleState),
    [selectedRegularItems, siteSaleState],
  );
  const warehouseListSubtotal = useMemo(
    () => sumCartLineListSubtotal(selectedWarehouseItems, siteSaleState),
    [selectedWarehouseItems, siteSaleState],
  );
  const selectedOriginalSubtotal = regularListSubtotal + warehouseListSubtotal;

  const regularFlashSaleSavings = useMemo(
    () => sumCartLineFlashSaleSavings(selectedRegularItems, siteSaleState),
    [selectedRegularItems, siteSaleState],
  );
  const regularCalendarSaleSavings = useMemo(
    () => sumCartLineCalendarSaleSavings(selectedRegularItems, siteSaleState),
    [selectedRegularItems, siteSaleState],
  );
  const warehouseClearanceSavings = useMemo(
    () => sumCartLineClearanceSavings(selectedWarehouseItems),
    [selectedWarehouseItems],
  );

  const googleCartSavings = useMemo(
    () =>
      selectedRegularItems.reduce((sum, item) => {
        if (!isGoogleDiscountCartLine(item)) return sum;
        const pricing = resolveCartLineDisplayPricing(
          mergeCartLineSiteSaleFromCalendar(item, siteSaleState),
          false,
          0,
        );
        return sum + pricing.lineSavings;
      }, 0),
    [selectedRegularItems, siteSaleState],
  );

  /** Site sale + Google + mọi giảm dòng — đồng bộ backend (list − subtotal) cho trần 15%. */
  const regularProgramSavings = useMemo(
    () => lineProgramSavingsFromList(regularListSubtotal, regularSubtotal),
    [regularListSubtotal, regularSubtotal],
  );

  const selectedTeaserSavings = useMemo(
    () =>
      selectedRegularItems.reduce((sum, item) => {
        const pricing = resolveCartLineDisplayPricing(
          mergeCartLineSiteSaleFromCalendar(item, siteSaleState),
          false,
          0,
        );
        if (pricing.sitePhase === 'teaser' && pricing.teaserLineSavings > 0) {
          return sum + pricing.teaserLineSavings;
        }
        return sum;
      }, 0),
    [selectedRegularItems, siteSaleState],
  );

  const rawWelcomeDiscount = calculateWelcomeDiscount(regularSubtotal, appliedPromo);
  const rawBirthdayDiscount =
    !welcomeApplied && birthdayActive && birthdayPercent > 0
      ? (regularSubtotal * birthdayPercent) / 100
      : 0;
  const subtotalAfterPrimary = Math.max(0, regularSubtotal - rawWelcomeDiscount - rawBirthdayDiscount);
  const rawLoyaltyDiscount =
    loyaltyPercent > 0 ? (subtotalAfterPrimary * loyaltyPercent) / 100 : 0;
  const cappedDiscounts = applyGrandOrderDiscountCap(
    regularListSubtotal,
    regularProgramSavings,
    rawWelcomeDiscount,
    rawBirthdayDiscount,
    rawLoyaltyDiscount,
  );
  const selectedWelcomeDiscount = cappedDiscounts.welcome;
  const selectedBirthdayDiscount = cappedDiscounts.birthday;
  const selectedLoyaltyDiscount = cappedDiscounts.loyalty;
  const discountCapped = cappedDiscounts.capped;
  const regularFinalPrice = Math.max(
    0,
    regularSubtotal - selectedWelcomeDiscount - selectedBirthdayDiscount - selectedLoyaltyDiscount,
  );
  const selectedFinalPrice = regularFinalPrice + warehouseSubtotal;
  const selectedShippingFee = computeShippingFee(selectedFinalPrice);
  const orderTotalWithShipping = selectedFinalPrice + selectedShippingFee;
  const regularPromoDiscount =
    selectedWelcomeDiscount + selectedBirthdayDiscount + selectedLoyaltyDiscount;
  const regularTotalDiscount = regularProgramSavings + regularPromoDiscount;
  const cappedLabelBase = {
    listSubtotal: regularListSubtotal,
    siteSaleSavings: regularProgramSavings,
    siteSaleActive,
    discountCapped,
  };
  const welcomePercentDisplay = resolveCappedPromoPercentDisplay({
    ...cappedLabelBase,
    rawAmount: rawWelcomeDiscount,
    appliedAmount: selectedWelcomeDiscount,
    nominalPercent: appliedPromo?.discountPercent ?? 0,
  });
  const birthdayPercentDisplay = resolveCappedPromoPercentDisplay({
    ...cappedLabelBase,
    rawAmount: rawBirthdayDiscount,
    appliedAmount: selectedBirthdayDiscount,
    nominalPercent: birthdayPercent,
  });
  const loyaltyPercentDisplay = resolveCappedPromoPercentDisplay({
    ...cappedLabelBase,
    rawAmount: rawLoyaltyDiscount,
    appliedAmount: selectedLoyaltyDiscount,
    nominalPercent: loyaltyPercent,
  });
  const walletUsable = useWallet
    ? Math.min(walletBalance, selectedCartItems.length > 0 ? orderTotalWithShipping : 0)
    : 0;
  const payableAfterWallet = Math.max(0, orderTotalWithShipping - walletUsable);

  const prevSiteSalePhaseRef = useRef<string | null | undefined>(undefined);
  useEffect(() => {
    const phase = siteSaleState?.phase ?? null;
    if (prevSiteSalePhaseRef.current !== undefined && prevSiteSalePhaseRef.current !== phase) {
      void refreshCart();
    }
    prevSiteSalePhaseRef.current = phase;
  }, [siteSaleState?.phase, refreshCart]);

  useEffect(() => {
    if (!isAuthenticated) return;
    const target = nextCartSaleRefreshAtMs(
      cartItems,
      cart?.site_sale ?? globalSiteSale ?? null,
    );
    if (target == null) return;
    const timer = window.setInterval(() => {
      if (Date.now() >= target) {
        setSaleClockMs(Date.now());
        void refreshCart();
        void reloadSiteSale();
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [isAuthenticated, cartItems, cart?.site_sale, globalSiteSale, refreshCart, reloadSiteSale]);

  const promoVouchersLoadedRef = useRef(false);
  useEffect(() => {
    if (!isAuthenticated) {
      setPromoVouchers([]);
      setPromoVouchersLoading(false);
      promoVouchersLoadedRef.current = false;
      return;
    }
    let cancelled = false;
    if (!promoVouchersLoadedRef.current) setPromoVouchersLoading(true);
    apiClient
      .getMyPromoVouchers(regularSubtotal > 0 ? regularSubtotal : undefined)
      .then((res) => {
        if (!cancelled) setPromoVouchers(res.items ?? []);
      })
      .catch(() => {
        if (!cancelled) setPromoVouchers([]);
      })
      .finally(() => {
        if (!cancelled) {
          setPromoVouchersLoading(false);
          promoVouchersLoadedRef.current = true;
        }
      });
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, regularSubtotal]);

  const allLineIds = useMemo(() => cartItems.map((i) => i.id), [cartItems]);
  const allSelected =
    cartItems.length > 0 && allLineIds.every((id) => selectionForTotals.has(id));
  const welcomeVoucher = useMemo(
    () => promoVouchers.find((v) => v.code === WELCOME_PROMO_CODE && v.eligible) ?? null,
    [promoVouchers]
  );
  const hasWalletPromo = promoVouchers.some((v) => v.eligible);

  const cartTotalAll = useMemo(
    () =>
      cartItems.reduce(
        (sum, item) => sum + resolveCartLineCheckoutTotal(item, siteSaleState),
        0,
      ),
    [cartItems, siteSaleState]
  );

  const cartAdsFingerprint = useMemo(() => {
    const convCfg = peekGoogleAdsConversionsFingerprint();
    return `${convCfg}|${cartItems
      .map((i) =>
        `${i.id}:${i.quantity}:${resolveCartLineCheckoutTotal(i, siteSaleState)}`,
      )
      .slice()
      .sort()
      .join('|')}`;
  }, [cartItems, siteSaleState]);

  useEffect(() => {
    if (!isAuthenticated || cartItems.length === 0) return;
    trackGoogleAdsCartPageView(cartItems, cartTotalAll);
    trackTikTokInitiateCheckout({ items: cartItems, value: cartTotalAll });
    trackMetaInitiateCheckout({ items: cartItems, value: cartTotalAll });
  }, [isAuthenticated, cartAdsFingerprint, cartTotalAll]);

  if (!pageReady || (isLoading && !cart)) {
    return <CartPageSkeleton />;
  }

  if (!isClientAuthLikelyLoggedIn(isAuthenticated, authLoading)) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center px-6">
        <p className="text-sm text-gray-600">
          {authLoading ? 'Đang tải phiên đăng nhập…' : 'Đang chuyển đến đăng nhập...'}
        </p>
      </div>
    );
  }

  const toggleLineSelected = (lineId: number) => {
    setSelectedItemIds((prev) => {
      const next = new Set(prev);
      if (next.has(lineId)) next.delete(lineId);
      else next.add(lineId);
      return next;
    });
  };

  const toggleSelectAllLines = () => {
    if (cartItems.length === 0) return;
    setSelectedItemIds(() => {
      if (allSelected) return new Set();
      return new Set(allLineIds);
    });
  };

  const depositRequiredForSelected =
    selectedCartItems.some(
      (item) =>
        item.requires_deposit === true || item.product_data?.deposit_require === true
    ) || false;
  const paymentMethodLabel = depositRequiredForSelected
    ? `Chuyển khoản cọc ${DEPOSIT_PERCENT}%`
    : 'Thanh toán khi nhận hàng (COD)';

  const selectedAddress = addresses.find((a) => a.id === selectedAddressId);
  const customerAddressLine = selectedAddress
    ? formatAddressLine(selectedAddress)
    : '';

  const cartLineRef = (item: {
    id: number;
    product_id: number;
    selected_size?: string;
    selected_color?: string;
  }): CartLineRef => ({
    id: item.id,
    product_id: item.product_id,
    selected_size: item.selected_size,
    selected_color: item.selected_color,
  });

  type CartQtyLine = {
    id: number;
    product_id: number;
    selected_size?: string;
    selected_color?: string;
    product_data?: Record<string, unknown> | null;
    quantity: number;
  };

  const applyQuantity = async (item: CartQtyLine, newQuantity: number) => {
    if (!Number.isFinite(newQuantity)) return;
    let qty = Math.floor(newQuantity);
    if (qty < 1) qty = 1;
    const maxQ = cartLineMaxQuantity(item);
    if (qty > maxQ) {
      latestQtyByIdRef.current.set(item.id, maxQ);
      setQtyDrafts((prev) => {
        const next = { ...prev };
        delete next[item.id];
        return next;
      });
      pushToast({
        title: 'Số lượng tối đa',
        description: isWarehouseCartLine(item)
          ? `Hàng kho thanh lý chỉ còn ${maxQ} — không thể chọn quá ${maxQ}.`
          : `Tối đa ${maxQ} sản phẩm mỗi dòng.`,
        variant: 'info',
        durationMs: 3500,
      });
      await updateCartItem(cartLineRef(item), { quantity: maxQ });
      return;
    }
    const current = latestQtyByIdRef.current.get(item.id) ?? item.quantity;
    if (qty === current && qty === item.quantity) return;
    latestQtyByIdRef.current.set(item.id, qty);
    setQtyDrafts((prev) => {
      const next = { ...prev };
      delete next[item.id];
      return next;
    });
    try {
      await updateCartItem(cartLineRef(item), { quantity: qty });
    } catch (err: unknown) {
      latestQtyByIdRef.current.delete(item.id);
      const msg = err instanceof Error ? err.message : String(err);
      pushToast({ title: 'Không cập nhật được số lượng', description: msg, variant: 'error', durationMs: 4000 });
    }
  };

  const handleQuantityDelta = async (item: CartQtyLine, delta: number) => {
    const current = latestQtyByIdRef.current.get(item.id) ?? item.quantity;
    await applyQuantity(item, current + delta);
  };

  const handleQuantityInputChange = (lineId: number, raw: string) => {
    const digits = raw.replace(/\D/g, '').slice(0, 3);
    setQtyDrafts((prev) => ({ ...prev, [lineId]: digits }));
  };

  const handleQuantityInputCommit = async (item: CartQtyLine, raw?: string) => {
    const draft = raw ?? qtyDrafts[item.id];
    if (draft == null) return;
    const parsed = parseInt(draft, 10);
    if (!Number.isFinite(parsed) || draft === '') {
      setQtyDrafts((prev) => {
        const next = { ...prev };
        delete next[item.id];
        return next;
      });
      return;
    }
    await applyQuantity(item, parsed);
  };

  const handleRemoveItem = async (item: {
    id: number;
    product_id: number;
    selected_size?: string;
    selected_color?: string;
  }) => {
    await removeFromCart(cartLineRef(item));
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

  const handleSelectPromoVoucher = async (voucher: PromotionVoucherItem) => {
    if (!voucher.eligible) return;
    if (regularSubtotal <= 0) {
      setPromoError('Mã khuyến mãi chỉ áp dụng cho hàng thường (không gồm thanh lý kho).');
      return;
    }
    setPromoApplying(true);
    setPromoError(null);
    try {
      const res = await apiClient.validatePromoCode({
        code: voucher.code,
        subtotal: regularSubtotal,
      });
      setAppliedPromo({
        code: res.code,
        discountPercent: res.discount_percent,
        maxDiscount: res.max_discount_amount,
      });
      pushToast({
        title: 'Đã áp dụng mã khuyến mãi',
        description: `Tiết kiệm ${new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(res.estimated_discount)}`,
        variant: 'success',
        durationMs: 3000,
      });
    } catch (err: unknown) {
      setAppliedPromo(null);
      const message = err instanceof Error ? err.message : 'Mã khuyến mãi không hợp lệ.';
      setPromoError(message);
    } finally {
      setPromoApplying(false);
    }
  };

  const handleRemovePromo = () => {
    setAppliedPromo(null);
    setPromoError(null);
  };

  const handleCheckout = async () => {
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

    const linesToOrder = selectedCartItems;
    if (linesToOrder.length === 0) {
      pushToast({
        title: 'Chưa chọn sản phẩm',
        description: 'Vui lòng chọn ít nhất một sản phẩm để đặt hàng.',
        variant: 'info',
        durationMs: 2800,
      });
      return;
    }

    const depositType = depositRequiredForSelected ? 'percent_30' : undefined;

    setIsCheckingOut(true);
    try {
      trackEvent('begin_checkout', { status: 'start', item_count: linesToOrder.length });
      const referralCode = getStoredReferralCode();
      const checkout = await apiClient.createOrderFull({
        customer_name: selectedAddress.full_name,
        customer_phone: selectedAddress.phone,
        customer_email: accountEmail,
        customer_address: customerAddressLine,
        customer_note: undefined,
        payment_method: depositRequiredForSelected ? 'bank_transfer' : 'cod',
        shipping_method: 'standard',
        deposit_type: depositType,
        wallet_amount: useWallet && walletUsable > 0 ? walletUsable : undefined,
        referral_code: referralCode || undefined,
        promo_code: appliedPromo?.code,
        items: linesToOrder.map((item) => ({
          product_id: item.product_id,
          quantity: item.quantity,
          selected_size: item.selected_size ?? undefined,
          selected_color: item.selected_color ?? undefined,
          google_pv2_token:
            (item.product_data as { google_automated_discount?: unknown } | undefined)?.google_automated_discount
              ? undefined
              : getActiveGoogleAutomatedDiscountToken(
                  item.product_code ??
                    (item.product_data as { product_id?: string } | undefined)?.product_id,
                ) ?? undefined,
        })),
      });

      const order =
        checkout.orders.find((row) => row.id === checkout.next_action_order_id) ||
        checkout.orders[0];
      if (!order) throw new Error('Hệ thống chưa trả về đơn hàng vừa tạo.');
      const redirectDeposit = shouldRedirectToDepositAfterCreate(order);
      if (!redirectDeposit) {
        trackMetaPurchase({
          items: linesToOrder.map((i) => ({ ...i })),
          value: selectedFinalPrice,
          orderId: order.id,
        });
        trackTikTokCompletePayment({
          items: linesToOrder.map((i) => ({ ...i })),
          value: selectedFinalPrice,
          orderId: order.id,
        });
        trackGoogleAdsPurchase({
          items: linesToOrder.map((i) => ({ ...i })),
          value: selectedFinalPrice,
          orderId: order.id,
        });
      } else {
        trackMetaOrderAwaitingDeposit({
          items: linesToOrder.map((i) => ({ ...i })),
          value: selectedFinalPrice,
          depositAmount: order.deposit_amount,
          orderId: order.id,
        });
        trackTikTokPlaceAnOrder({
          items: linesToOrder.map((i) => ({ ...i })),
          value: selectedFinalPrice,
          depositAmount: order.deposit_amount,
          orderId: order.id,
        });
        trackGoogleAdsOrderAwaitingDeposit({
          items: linesToOrder.map((i) => ({ ...i })),
          value: selectedFinalPrice,
          depositAmount: order.deposit_amount,
          orderId: order.id,
        });
        try {
          if (typeof localStorage !== 'undefined') {
            localStorage.setItem(`meta_order_awaiting_deposit_${order.id}`, '1');
          }
        } catch {
          /* ignore */
        }
      }

      for (const item of linesToOrder) {
        await removeFromCart(cartLineRef(item));
      }

      if (!redirectDeposit) {
        trackEvent('purchase', {
          order_id: order.id,
          value: selectedFinalPrice,
          item_count: linesToOrder.length,
          product_ids: linesToOrder.map((i) => i.product_id),
        });
      } else {
        trackEvent('order_awaiting_deposit', {
          order_id: order.id,
          item_count: linesToOrder.length,
          product_ids: linesToOrder.map((i) => i.product_id),
        });
      }
      checkout.orders.forEach((created) => markGoogleCustomerReviewsForOrder(created.id));
      if (checkout.orders.length > 1) {
        pushToast({
          title: 'Đã tách thành 2 đơn hàng',
          description: `${checkout.orders
            .map(
              (created) =>
                `${created.order_code || `#${created.id}`} (${
                  created.fulfillment_source === 'china' ? 'Trung Quốc' : 'Việt Nam'
                })`,
            )
            .join(' và ')}. Phí giao hàng chỉ tính một lần.`,
          variant: 'success',
          durationMs: 6500,
        });
        router.push(`/account/orders?checkout_group=${encodeURIComponent(checkout.checkout_group_id)}`);
      } else {
        router.push(redirectDeposit ? `/account/orders/${order.id}/deposit` : `/account/orders/${order.id}`);
      }
    } catch (err: unknown) {
      const message = (err as Error)?.message || 'Đặt hàng thất bại';
      pushToast({ title: 'Đặt hàng thất bại', description: message, variant: 'error', durationMs: 3500 });
      trackEvent('purchase', { status: 'failed', error: message });
    } finally {
      setIsCheckingOut(false);
    }
  };

  const handleOpenProduct = async (item: {
    product_id: number;
    product_code?: string | null;
    product_data?: Record<string, unknown> | null;
  }) => {
    if (isWarehouseCartLine(item)) {
      const parentSeg = resolveWarehouseCartPdpSlug(item);
      if (parentSeg) {
        router.push(`/products/${parentSeg}`);
        return;
      }
      const code = String(item.product_data?.product_id ?? item.product_code ?? '');
      const baseSku = code.split('/')[0];
      if (baseSku) {
        try {
          const p = await apiClient.getProductBySku(baseSku);
          const seg = productPathSlugFromApi(p?.slug, p?.product_id);
          if (seg) {
            router.push(`/products/${seg}`);
            return;
          }
        } catch {
          // fall through
        }
      }
    }
    const rawSlug = item.product_data?.slug;
    const seg = productPathSlugFromApi(
      typeof rawSlug === 'string' ? rawSlug : undefined,
      String(item.product_id),
    );
    if (seg) {
      router.push(`/products/${seg}`);
      return;
    }
    try {
      const p = await apiClient.getProductById(item.product_id);
      const seg2 = productPathSlugFromApi(p?.slug, p?.product_id);
      if (seg2) {
        router.push(`/products/${seg2}`);
      }
    } catch {
      // ignore
    }
  };

  const mdCartGridCols = 'md:grid-cols-[44px_minmax(0,1fr)_120px_120px_120px_40px]';

  if (!cart || !Array.isArray(cart.items) || cart.items.length === 0) {
    return (
      <div className="min-h-screen bg-gray-50">
        <div className="mx-auto max-w-7xl px-3 pb-8 pt-2 sm:px-3 md:px-4 md:py-12 md:pb-6 md:pt-3">
          <div className="mx-auto max-w-2xl text-center">
            <div className="rounded-2xl border border-gray-100 bg-white p-8 shadow-sm sm:p-10 md:p-12">
              <div className="mx-auto mb-4 flex h-20 w-20 items-center justify-center rounded-full bg-gray-100 md:mb-6 md:h-24 md:w-24">
                <svg className="h-10 w-10 text-gray-400 md:h-12 md:w-12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" />
                </svg>
              </div>
              <h1 className="mb-2 text-base font-bold tracking-tight text-gray-900 sm:text-lg md:mb-4 md:text-2xl">
                Giỏ hàng trống
              </h1>
              <p className="mb-6 text-xs text-gray-600 sm:text-sm md:mb-8 md:text-base">
                Bạn chưa có sản phẩm nào trong giỏ hàng.
              </p>
              <Link
                href="/"
                className="inline-flex min-h-[44px] items-center justify-center rounded-lg bg-[#ea580c] px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#c2410c] md:min-h-0 md:px-6 md:py-3 md:text-base"
              >
                Tiếp tục mua sắm
              </Link>
            </div>
          </div>
          <CartEmptySameShopSection />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="mx-auto max-w-7xl px-3 pb-5 pt-2 sm:px-3 md:px-4 md:py-8 md:pb-6 md:pt-3">
        <div className="mb-3 flex flex-col gap-3 md:mb-6 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-base font-bold tracking-tight text-gray-900 sm:text-lg md:text-2xl">
              Giỏ hàng
            </h1>
            <p className="mt-0.5 text-xs text-gray-600 sm:text-sm md:mt-1 md:text-base">
              {(cart?.items ?? []).length} sản phẩm
            </p>
          </div>
          <button
            type="button"
            onClick={handleClearCart}
            className="inline-flex items-center gap-2 self-start text-sm font-medium text-red-600 hover:text-red-700 md:self-auto"
          >
            Xóa tất cả
          </button>
        </div>

        <BirthdayPromoBanner
          active={birthdayLineActive}
          percent={birthdayPercent || 10}
          nextBirthdayLabel={cart?.birthday_next_date ?? null}
          className="mb-4"
        />

        <SiteSaleBanner state={siteSaleState} className="mb-4" />

        {cartHasFlash && cartFlashLine?.site_sale?.countdown_to ? (
          <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-950">
            <p className="font-semibold">{FLASH_SALE_PROGRAM_NAME} đang áp dụng trên sản phẩm trong giỏ</p>
            <SiteSaleLiveCountdown
              countdownTo={cartFlashLine.site_sale.countdown_to}
              phase="active"
              eventLabel={FLASH_SALE_PROGRAM_NAME}
              size="sm"
              inline
              className="mt-1 block"
            />
          </div>
        ) : null}

        {(siteSaleTeaser || siteSaleActive) && siteSaleState?.countdown_to ? (
          <SiteSaleLiveCountdown
            countdownTo={siteSaleState.countdown_to}
            phase={siteSaleState.phase}
            eventLabel={calendarSaleProgramLabel(null, siteSaleState)}
            className="mb-4"
          />
        ) : null}

        {welcomeVoucher && !appliedPromo ? (
          <div className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
            <p className="font-semibold">Bạn có quà trong ví!</p>
            <p className="mt-1 text-emerald-800">
              Mã <span className="font-mono font-bold">{welcomeVoucher.code}</span> — giảm{' '}
              <span className="font-bold">{welcomeVoucher.discount_percent}%</span> (tối đa{' '}
              {new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(
                welcomeVoucher.max_discount_amount
              )}
              )
            </p>
            {welcomeVoucher.show_days_remaining && welcomeVoucher.days_remaining != null ? (
              <p className="mt-1.5 text-emerald-700 font-medium">
                {welcomeVoucher.days_remaining > 0
                  ? `Còn ${welcomeVoucher.days_remaining} ngày — chọn mã bên dưới`
                  : 'Hết hạn hôm nay — dùng ngay'}
                {' · '}
                <Link href="/account/khuyen-mai" className="underline">
                  Ví khuyến mãi
                </Link>
              </p>
            ) : (
              <p className="mt-1.5 text-emerald-700">
                <Link href="/account/khuyen-mai" className="underline font-medium">
                  Xem ví khuyến mãi
                </Link>
              </p>
            )}
          </div>
        ) : hasWalletPromo && !appliedPromo ? (
          <div className="mb-4 rounded-xl border border-orange-200 bg-orange-50 px-4 py-3 text-sm text-orange-900">
            Bạn có mã quà chưa dùng — chọn trong phần <span className="font-semibold">Chọn mã giảm giá</span>{' '}
            bên dưới.
          </div>
        ) : null}

        <div className="space-y-4 md:space-y-6">
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
            {error}
          </div>
        )}
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

        <div className="bg-white rounded-2xl shadow-sm overflow-hidden border border-gray-100">
            <div
              className={`hidden md:grid gap-3 px-5 py-3 text-xs font-semibold text-gray-500 uppercase bg-gray-50 ${mdCartGridCols}`}
            >
              <div className="flex items-center justify-center">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={toggleSelectAllLines}
                  disabled={cartItems.length === 0}
                  className="h-4 w-4 rounded border-gray-300 text-[#ea580c] focus:ring-[#ea580c]"
                  aria-label="Chọn tất cả sản phẩm"
                />
              </div>
              <span>Sản phẩm</span>
              <span className="text-right">Đơn giá</span>
              <span className="text-center">Số lượng</span>
              <span className="text-right">Thành tiền</span>
              <span />
            </div>
            <div className="divide-y divide-gray-100">
              {(cart?.items ?? []).map((item) => {
                const lineItem = mergeCartLineSiteSaleFromCalendar(item, siteSaleState);
                const pricing = resolveCartLineDisplayPricing(lineItem, false, 0);
                const isFlashLine = cartLineHasActiveFlash(lineItem) || pricing.isFlashSale;
                const lineKey = `${item.product_id}-${item.selected_size ?? ''}-${item.selected_color ?? ''}-${item.id}`;
                const lineChecked = selectionForTotals.has(item.id);
                const showCompareUnit =
                  pricing.compareUnitPrice != null && pricing.compareUnitPrice > pricing.displayUnitPrice;
                const showCompareLine =
                  pricing.compareLineTotal != null && pricing.compareLineTotal > pricing.displayLineTotal;
                const showTeaserPromo =
                  pricing.sitePhase === 'teaser' &&
                  pricing.sitePercent > 0 &&
                  pricing.expectedSaleUnitPrice != null &&
                  pricing.teaserUnitSavings > 0;
                const maxLineQty = cartLineMaxQuantity(item);
                const isWhLine = isWarehouseCartLine(item);
                const isGoogleLine = isGoogleDiscountCartLine(item);
                const googleDiscountPercent = isGoogleLine
                  ? googleDiscountPercentFromPricing(pricing.compareUnitPrice, pricing.displayUnitPrice)
                  : null;
                const lineProgramName = isGoogleLine
                  ? 'Google Shopping'
                  : stackedSaleProgramLabel({
                      isWarehouse: isWhLine,
                      isFlash: isFlashLine,
                      siteLabel: siteSaleProgramLabel(lineItem.site_sale, siteSaleState),
                    }) || siteSaleProgramLabel(lineItem.site_sale, siteSaleState);
                return (
                  <div key={lineKey} className="px-3 md:px-5 py-3 md:py-4">
                    <div className={`grid grid-cols-1 gap-3 items-center ${mdCartGridCols}`}>
                      <div className="flex gap-3 md:gap-4 items-center md:contents">
                        <div className="flex shrink-0 items-center justify-center md:flex md:justify-center md:items-center md:row-span-1">
                          <input
                            type="checkbox"
                            checked={lineChecked}
                            onChange={() => toggleLineSelected(item.id)}
                            className="h-4 w-4 rounded border-gray-300 text-[#ea580c] focus:ring-[#ea580c]"
                            aria-label={`Chọn ${item.product_data?.name ?? 'sản phẩm'} để đặt hàng`}
                          />
                        </div>
                        <div className="flex flex-1 gap-4 items-center min-w-0 md:col-span-1">
                          <div
                            role="button"
                            tabIndex={0}
                            onClick={() => handleOpenProduct(item)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault();
                                handleOpenProduct(item);
                              }
                            }}
                            className="flex-shrink-0 w-16 h-16 md:w-20 md:h-20 bg-gray-100 rounded-xl overflow-hidden relative touch-manipulation cursor-pointer"
                            aria-label="Xem chi tiết sản phẩm"
                          >
                            <CartLineThumbnail item={item} size={80} className="h-full w-full object-cover" />
                          </div>
                          <div className="min-w-0 flex-1">
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
                                {isWhLine ? ` • ${WAREHOUSE_SALE_PROGRAM_NAME}` : ''}
                                {isGoogleLine ? ' • Google Shopping' : ''}
                              </p>
                            )}
                            <div className="mt-1.5 flex flex-wrap gap-1">
                              {isFlashLine && pricing.sitePercent > 0 ? (
                                <span className="rounded bg-rose-600 px-1.5 py-0.5 text-[10px] font-bold text-white">
                                  {FLASH_SALE_PROGRAM_NAME} -{pricing.sitePercent}%
                                </span>
                              ) : null}
                              {!isFlashLine && !isWhLine && !isGoogleLine && pricing.sitePhase === 'active' && pricing.sitePercent > 0 ? (
                                <span className="rounded bg-red-500 px-1.5 py-0.5 text-[10px] font-bold text-white">
                                  {siteSaleProgramLabel(lineItem.site_sale, siteSaleState)} -{pricing.sitePercent}%
                                </span>
                              ) : null}
                              {!isFlashLine && !isWhLine && !isGoogleLine && pricing.sitePhase === 'teaser' && pricing.sitePercent > 0 ? (
                                <span className="rounded bg-amber-500 px-1.5 py-0.5 text-[10px] font-bold text-white">
                                  Sắp {siteSaleProgramLabel(lineItem.site_sale, siteSaleState)} -{pricing.sitePercent}%
                                </span>
                              ) : null}
                              {isWhLine ? (
                                <span className="rounded bg-amber-700 px-1.5 py-0.5 text-[10px] font-bold text-white">
                                  {WAREHOUSE_SALE_PROGRAM_NAME}
                                  {pricing.sitePercent > 0 ? ` -${pricing.sitePercent}%` : ''}
                                </span>
                              ) : null}
                              {isGoogleLine ? (
                                <span className="rounded bg-emerald-600 px-1.5 py-0.5 text-[10px] font-bold text-white">
                                  Google{googleDiscountPercent != null ? ` -${googleDiscountPercent}%` : ''}
                                </span>
                              ) : null}
                              {birthdayLineActive && !isWhLine ? (
                                <span className="rounded bg-pink-600 px-1.5 py-0.5 text-[10px] font-bold text-white">
                                  {BIRTHDAY_PROGRAM_NAME} -{birthdayPercent}% ở tổng đơn
                                </span>
                              ) : null}
                            </div>
                          </div>
                        </div>
                      </div>

                      <div className="hidden text-right md:block">
                        {showTeaserPromo ? (
                          <>
                            <p className="text-sm md:text-base font-semibold text-gray-900 whitespace-nowrap">
                              {formatPrice(pricing.displayUnitPrice)}
                            </p>
                            <p className="text-xs font-semibold text-emerald-700 whitespace-nowrap">
                              Dự kiến {formatPrice(pricing.expectedSaleUnitPrice!)}
                            </p>
                            <span className="mt-0.5 inline-block rounded bg-amber-500 px-1 py-0.5 text-[10px] font-bold text-white">
                              {siteSaleProgramLabel(lineItem.site_sale, siteSaleState)} -{pricing.sitePercent}%
                            </span>
                          </>
                        ) : (
                          <>
                            <p className="text-sm md:text-base font-semibold text-gray-900 whitespace-nowrap">
                              {formatPrice(pricing.displayUnitPrice)}
                            </p>
                            {showCompareUnit ? (
                              <p className="text-xs text-gray-400 line-through whitespace-nowrap">
                                {formatPrice(pricing.compareUnitPrice!)}
                              </p>
                            ) : null}
                            {(pricing.sitePhase === 'active' || isWhLine) && pricing.sitePercent > 0 && !isGoogleLine ? (
                              <span className={`mt-0.5 inline-block rounded px-1 py-0.5 text-[10px] font-bold text-white ${isFlashLine ? 'bg-rose-600' : isWhLine ? 'bg-amber-700' : 'bg-red-500'}`}>
                                {isWhLine
                                  ? `${WAREHOUSE_SALE_PROGRAM_NAME} -${pricing.sitePercent}%`
                                  : isFlashLine
                                    ? `${FLASH_SALE_PROGRAM_NAME} -${pricing.sitePercent}%`
                                    : `${siteSaleProgramLabel(lineItem.site_sale, siteSaleState)} -${pricing.sitePercent}%`}
                              </span>
                            ) : null}
                            {isGoogleLine && googleDiscountPercent != null ? (
                              <span className="mt-0.5 inline-block rounded bg-emerald-600 px-1 py-0.5 text-[10px] font-bold text-white">
                                Google -{googleDiscountPercent}%
                              </span>
                            ) : null}
                          </>
                        )}
                      </div>

                      <div className="flex w-full items-center justify-end order-3 md:order-none md:w-auto md:justify-center">
                        <div className="inline-flex items-center border border-gray-200 rounded-full">
                          <button
                            type="button"
                            onClick={() => handleQuantityDelta(item, -1)}
                            disabled={item.quantity <= 1}
                            className="flex h-9 w-9 items-center justify-center text-gray-600 hover:bg-gray-50 disabled:opacity-50"
                            aria-label="Giảm số lượng"
                          >
                            -
                          </button>
                          <input
                            type="text"
                            inputMode="numeric"
                            pattern="[0-9]*"
                            autoComplete="off"
                            value={qtyDrafts[item.id] ?? String(item.quantity)}
                            onChange={(e) => handleQuantityInputChange(item.id, e.target.value)}
                            onFocus={(e) => e.currentTarget.select()}
                            onBlur={(e) => {
                              void handleQuantityInputCommit(item, e.currentTarget.value);
                            }}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') {
                                e.preventDefault();
                                e.currentTarget.blur();
                              }
                            }}
                            aria-label={`Số lượng ${item.product_data?.name ?? 'sản phẩm'}`}
                            className="h-9 w-12 bg-transparent text-center text-sm font-semibold text-gray-900 outline-none focus:bg-gray-50"
                          />
                          <button
                            type="button"
                            onClick={() => handleQuantityDelta(item, 1)}
                            disabled={item.quantity >= maxLineQty}
                            className="flex h-9 w-9 items-center justify-center text-gray-600 hover:bg-gray-50 disabled:opacity-50"
                            aria-label="Tăng số lượng"
                          >
                            +
                          </button>
                        </div>
                      </div>

                      <div className="w-full space-y-0.5 order-2 md:order-none md:w-auto">
                        {showTeaserPromo ? (
                          <>
                            <div className="flex items-center justify-between gap-3 text-[11px] md:justify-end md:text-xs">
                              <span className="text-gray-500">Giá chưa trừ</span>
                              <span className="whitespace-nowrap font-medium text-gray-900">
                                {formatPrice(pricing.displayLineTotal)}
                              </span>
                            </div>
                            <div className="flex items-center justify-between gap-3 text-[11px] text-amber-700 md:justify-end md:text-xs">
                              <span>Trừ {lineProgramName} (dự kiến)</span>
                              <span className="whitespace-nowrap font-medium">
                                -{formatPrice(pricing.teaserLineSavings)}
                              </span>
                            </div>
                            <div className="flex items-center justify-between gap-3 md:justify-end">
                              <span className="text-[11px] font-medium text-emerald-700 md:text-xs">
                                Dự kiến sau trừ
                              </span>
                              <span className="whitespace-nowrap text-sm font-bold text-[#ea580c] md:text-base">
                                {formatPrice(pricing.expectedLineTotal!)}
                              </span>
                            </div>
                          </>
                        ) : showCompareLine || pricing.lineSavings > 0 ? (
                          <>
                            <div className="flex items-center justify-between gap-3 text-[11px] md:justify-end md:text-xs">
                              <span className="text-gray-500">Giá chưa trừ</span>
                              <span className="whitespace-nowrap font-medium text-gray-900">
                                {formatPrice(pricing.compareLineTotal ?? pricing.displayLineTotal)}
                              </span>
                            </div>
                            <div className="flex items-center justify-between gap-3 text-[11px] text-emerald-700 md:justify-end md:text-xs">
                              <span>Trừ {lineProgramName}</span>
                              <span className="whitespace-nowrap font-medium">
                                -{formatPrice(pricing.lineSavings)}
                              </span>
                            </div>
                            <div className="flex items-center justify-between gap-3 md:justify-end">
                              <span className="text-[11px] font-medium text-gray-700 md:text-xs">
                                Tổng sau trừ
                              </span>
                              <span className="whitespace-nowrap text-sm font-bold text-[#ea580c] md:text-base">
                                {formatPrice(pricing.displayLineTotal)}
                              </span>
                            </div>
                          </>
                        ) : (
                          <div className="flex items-center justify-between gap-3 md:justify-end">
                            <span className="text-[11px] font-medium text-gray-700 md:hidden">
                              Thành tiền
                            </span>
                            <p className="whitespace-nowrap text-sm font-bold text-[#ea580c] md:text-base">
                              {formatPrice(pricing.displayLineTotal)}
                            </p>
                          </div>
                        )}
                      </div>

                      <div className="flex order-4 md:order-none md:justify-end">
                        <button
                          type="button"
                          onClick={() => handleRemoveItem(item)}
                          className="text-gray-400 hover:text-red-600"
                          aria-label="Xóa khỏi giỏ"
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
            <CartVoucherPicker
              vouchers={promoVouchers}
              loading={promoVouchersLoading}
              appliedCode={appliedPromo?.code ?? null}
              applying={promoApplying}
              disabled={noneSelected}
              onSelect={handleSelectPromoVoucher}
              onClear={handleRemovePromo}
            />
            {promoError ? <p className="mb-3 text-xs text-red-600">{promoError}</p> : null}

            {siteSaleTeaser && selectedTeaserSavings > 0 ? (
              <div className="mb-2 space-y-1.5">
                <div className="flex items-center justify-between text-[11px] md:text-sm">
                  <span className="text-amber-700">
                    Tiết kiệm dự kiến khi {calendarSaleProgramLabel(null, siteSaleState)}{' '}
                    <span className="font-bold">
                      (-{siteSaleState?.discount_percent ?? 0}%)
                    </span>
                  </span>
                  <span className="font-medium text-amber-700">~{formatPrice(selectedTeaserSavings)}</span>
                </div>
                {siteSaleState?.countdown_to ? (
                  <SiteSaleLiveCountdown
                    countdownTo={siteSaleState.countdown_to}
                    phase="teaser"
                    eventLabel={calendarSaleProgramLabel(null, siteSaleState)}
                    size="sm"
                  />
                ) : null}
              </div>
            ) : null}

            {siteSaleActive && siteSaleState?.countdown_to ? (
              <SiteSaleLiveCountdown
                countdownTo={siteSaleState.countdown_to}
                phase="active"
                eventLabel={calendarSaleProgramLabel(null, siteSaleState)}
                size="sm"
                className="mb-2"
              />
            ) : null}

            {hasRegularSelection ? (
              <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-gray-500 md:text-xs">
                Hàng thường
              </p>
            ) : null}

            {hasRegularSelection && regularTotalDiscount > 0 ? (
              <div className="flex items-center justify-between mb-1 text-[11px] md:text-sm">
                <span className="text-gray-500">Giá chưa trừ</span>
                <span className="font-medium text-gray-900">{formatPrice(regularListSubtotal)}</span>
              </div>
            ) : null}

            {regularFlashSaleSavings > 0 ? (
              <div className="flex items-center justify-between mb-1 text-[11px] md:text-sm">
                <span className="text-gray-500">
                  {FLASH_SALE_PROGRAM_NAME}{' '}
                  <span className="font-bold text-rose-600">
                    ({formatPrice(regularFlashSaleSavings)} đã trừ trên giá SP)
                  </span>
                </span>
                <span className="font-medium text-emerald-600">-{formatPrice(regularFlashSaleSavings)}</span>
              </div>
            ) : null}

            {regularCalendarSaleSavings > 0 ? (
              <div className="flex items-center justify-between mb-1 text-[11px] md:text-sm">
                <span className="text-gray-500">
                  {calendarSaleProgramLabel(null, siteSaleState)}{' '}
                  <span className="font-bold text-red-600">
                    {siteSaleState?.discount_percent ? `(-${siteSaleState.discount_percent}%)` : ''}
                  </span>
                </span>
                <span className="font-medium text-emerald-600">-{formatPrice(regularCalendarSaleSavings)}</span>
              </div>
            ) : null}

            {googleCartSavings > 0 ? (
              <div className="flex items-center justify-between mb-1 text-[11px] md:text-sm">
                <span className="text-gray-500">Giá ưu đãi Google Shopping</span>
                <span className="font-medium text-emerald-600">-{formatPrice(googleCartSavings)}</span>
              </div>
            ) : null}

            {welcomeApplied && selectedWelcomeDiscount > 0 ? (
              <div className="flex items-center justify-between mb-1 text-[11px] md:text-sm">
                <span className="text-gray-500">
                  Số tiền trừ · Mã {appliedPromo?.code}{' '}
                  (
                  <CappedPromoPercentLabel
                    display={welcomePercentDisplay}
                    className="font-bold text-emerald-600"
                  />
                  {appliedPromo?.maxDiscount ? `, tối đa ${formatPrice(appliedPromo.maxDiscount)}` : ''}
                  )
                </span>
                <span className="font-medium text-emerald-600">
                  -{formatPrice(selectedWelcomeDiscount)}
                </span>
              </div>
            ) : null}

            {welcomeApplied && birthdayActive ? (
              <p className="mb-1.5 text-[11px] text-pink-700">
                Đang dùng mã — {BIRTHDAY_PROGRAM_NAME} tạm tắt (chọn một trong hai).
              </p>
            ) : null}

            {birthdayActive && !welcomeApplied && selectedBirthdayDiscount > 0 ? (
              <div className="flex items-center justify-between mb-1 text-[11px] md:text-sm">
                <span className="text-gray-500">
                  {BIRTHDAY_PROGRAM_NAME}{' '}
                  <CappedPromoPercentLabel
                    display={birthdayPercentDisplay}
                    className="font-bold text-pink-600"
                  />
                </span>
                <span className="font-medium text-pink-600">
                  -{formatPrice(selectedBirthdayDiscount)}
                </span>
              </div>
            ) : null}

            {/* Loyalty Discount — theo phần đã chọn (khi có giảm giá hạng) */}
            {loyaltyPercent > 0 && selectedLoyaltyDiscount > 0 ? (
              <div className="flex items-center justify-between mb-1 text-[11px] md:text-sm">
                <span className="text-gray-500">
                  Giảm giá hạng <span className="font-bold text-blue-600">{cart?.loyalty_tier_name}</span>{' '}
                  <CappedPromoPercentLabel
                    display={loyaltyPercentDisplay}
                    className="font-bold text-blue-600"
                  />
                </span>
                <span className="font-medium text-green-600">
                  -{new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(selectedLoyaltyDiscount)}
                </span>
              </div>
            ) : null}

            {hasRegularSelection ? (
              <div className="mb-2 flex items-center justify-between text-[11px] md:text-sm">
                <span className="font-medium text-gray-700">
                  {regularTotalDiscount > 0 ? 'Tổng sau trừ' : 'Tạm tính hàng thường'}
                </span>
                <span className="font-semibold text-gray-900">{formatPrice(regularFinalPrice)}</span>
              </div>
            ) : null}

            {hasWarehouseSelection ? (
              <div className="mb-2 rounded-lg border border-amber-100 bg-amber-50/50 px-2 py-2">
                <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-amber-900 md:text-xs">
                  {WAREHOUSE_SALE_PROGRAM_NAME}
                </p>
                {warehouseListSubtotal > warehouseSubtotal ? (
                  <div className="flex items-center justify-between mb-1 text-[11px] md:text-sm">
                    <span className="text-gray-600">Giá gốc (thanh lý)</span>
                    <span className="text-gray-400 line-through">{formatPrice(warehouseListSubtotal)}</span>
                  </div>
                ) : null}
                {warehouseClearanceSavings > 0 ? (
                  <div className="flex items-center justify-between mb-1 text-[11px] md:text-sm">
                    <span className="text-gray-600">{WAREHOUSE_SALE_PROGRAM_NAME}</span>
                    <span className="font-medium text-emerald-700">-{formatPrice(warehouseClearanceSavings)}</span>
                  </div>
                ) : null}
                <div className="flex items-center justify-between text-[11px] md:text-sm">
                  <span className="font-medium text-amber-950">Tạm tính thanh lý kho</span>
                  <span className="font-semibold text-amber-950">{formatPrice(warehouseSubtotal)}</span>
                </div>
              </div>
            ) : null}

            {discountCapped && hasRegularSelection ? (
              <div className="mb-2 flex items-start justify-between gap-2 rounded-lg border border-amber-100 bg-amber-50 px-2 py-1.5 text-[11px] text-amber-800 md:text-sm">
                <span>
                  Trần ưu đãi hàng thường {MAX_ORDER_DISCOUNT_PERCENT}% giá gốc (không gồm thanh lý kho). Mã còn trần riêng nếu có.
                </span>
                <span className="shrink-0 whitespace-nowrap font-semibold text-amber-900">
                  Đã giảm {formatPrice(regularTotalDiscount)}
                </span>
              </div>
            ) : null}

            {walletBalance > 0 ? (
              <label className="flex items-start gap-2 mb-3 rounded-lg border border-orange-100 bg-orange-50/80 px-3 py-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={useWallet}
                  onChange={(e) => setUseWallet(e.target.checked)}
                  className="mt-1"
                />
                <span>
                  Dùng ví affiliate ({new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(walletBalance)})
                  {useWallet && walletUsable > 0 ? (
                    <span className="block text-green-700 font-medium">
                      Trừ {new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(walletUsable)}
                    </span>
                  ) : null}
                </span>
              </label>
            ) : null}

            <div className="mb-2 flex items-center justify-between text-[11px] md:text-sm">
              <span className="text-gray-500">Phí vận chuyển</span>
              <span className="font-medium text-gray-900">
                {selectedShippingFee > 0
                  ? formatPrice(selectedShippingFee)
                  : selectedCartItems.length > 0
                    ? 'Miễn phí'
                    : formatPrice(0)}
              </span>
            </div>

            <div className="mb-2 flex items-center justify-between text-[11px] md:text-sm">
              <span className="text-gray-500">Phương thức thanh toán</span>
              <span className="font-medium text-gray-900 text-right max-w-[60%]">
                {selectedCartItems.length > 0 ? paymentMethodLabel : '—'}
              </span>
            </div>

            {isMixedFulfillment ? (
              <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-900 md:text-sm">
                <p className="font-medium">Giỏ hàng gồm hàng Trung Quốc và hàng có sẵn tại Việt Nam.</p>
                <p className="mt-1">
                  Hệ thống sẽ tạo 2 mã đơn và có thể giao 2 lần. Phí giao hàng chỉ tính một lần như tổng kết bên trên.
                </p>
              </div>
            ) : null}

            {depositRequiredForSelected && selectedCartItems.length > 0 ? (
              <div className="mb-3 rounded-lg border border-blue-100 bg-blue-50/80 px-3 py-2 text-[11px] text-blue-900 md:text-sm">
                <p>
                  Đơn có sản phẩm yêu cầu đặt cọc{' '}
                  <strong>{DEPOSIT_PERCENT}%</strong> trước khi xử lý. Số tiền chính xác của từng đơn sẽ hiển thị sau khi tách; phần còn lại thanh toán khi nhận hàng.
                </p>
                <p className="mt-1">
                  <Link href={PURCHASE_GUIDE_URL} className="text-blue-700 underline font-medium">
                    Xem hướng dẫn mua hàng &amp; đặt cọc
                  </Link>
                </p>
              </div>
            ) : null}

            <div className="flex items-center justify-between">
              <span className="text-sm md:text-base font-semibold text-gray-900">Tổng thanh toán</span>
              <span className="text-lg md:text-xl font-bold text-[#ea580c]">
                {new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(
                  selectedCartItems.length > 0 ? payableAfterWallet : 0
                )}
              </span>
            </div>
            {selectedCartItems.length > 0 && selectedShippingFee === 0 && selectedFinalPrice > 0 ? (
              <p className="text-[11px] text-emerald-700 mt-1 text-right md:text-xs">
                Miễn phí vận chuyển cho đơn từ 500.000đ
              </p>
            ) : null}
            {useWallet && walletUsable > 0 ? (
              <p className="text-xs text-gray-500 mt-1 text-right line-through">
                {new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(orderTotalWithShipping)}
              </p>
            ) : null}

            <p className="mt-3 text-[11px] text-gray-500 leading-relaxed md:text-xs">
              Bằng việc đặt hàng, bạn đồng ý với{' '}
              <Link href={TERMS_URL} className="text-[#ea580c] underline">
                Điều khoản sử dụng
              </Link>
              ,{' '}
              <Link href={SHIPPING_POLICY_URL} className="text-[#ea580c] underline">
                Chính sách giao hàng
              </Link>{' '}
              và{' '}
              <Link href={RETURN_POLICY_URL} className="text-[#ea580c] underline">
                Chính sách đổi trả
              </Link>
              .
            </p>

            <div className="mt-4 flex flex-col md:flex-row gap-3">
              <LoadingLink
                href="/"
                className="w-full md:w-1/2 bg-gray-100 border border-gray-200 text-gray-700 font-semibold py-3 rounded-lg hover:bg-gray-200 text-center transition-colors inline-flex items-center justify-center"
              >
                Mua sắm tiếp
              </LoadingLink>
              <Button
                type="button"
                variant="primary"
                onClick={handleCheckout}
                disabled={isCheckingOut || noneSelected}
                loading={isCheckingOut}
                className="w-full md:w-1/2 font-semibold py-3"
              >
                Đặt hàng
              </Button>
            </div>
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
                  <Button
                    type="submit"
                    variant="primary"
                    disabled={savingAddress}
                    loading={savingAddress}
                  >
                    Lưu vào sổ địa chỉ
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setShowAddAddress(false)}
                  >
                    Hủy
                  </Button>
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
    </div>
  );
}
