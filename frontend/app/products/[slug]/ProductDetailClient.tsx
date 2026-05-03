'use client';

import { useState, useEffect, useRef, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import Image from 'next/image';
import { apiClient } from '@/lib/api-client';
import { useCart } from '@/features/cart/hooks/useCart';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { useFavorites } from '@/features/favorites/hooks/useFavorites';
import type { Product, CategoryLevel1 } from '@/types/api';
import ProductHeader from './components/ProductHeader/ProductHeader';
import ProductGallery from './components/ProductGallery/ProductGallery';
import ProductInfo from './components/ProductInfo/ProductInfo';
import ProductTabs from '@/components/product-detail/ProductTabs';
import ProductQASection from './components/ProductQASection/ProductQASection';
import ProductReviewSection from './components/ProductReviewSection/ProductReviewSection';
import RelatedProducts from '@/components/product-detail/RelatedProducts';
import ProductDetailMobile from './ProductDetailMobile';
import ErrorState from './components/ErrorState/ErrorState';
import { useToast } from '@/components/ToastProvider';
import { trackEvent } from '@/lib/analytics';
import { persistRelatedFiltersFromProduct } from '@/lib/product-related-tabs';
import { cartLineMainImage } from '@/lib/product-color-variant';
import { buildAuthLoginHrefFromFullPath, getBrowserReturnLocation } from '@/lib/auth-redirect';
import { useLoginRedirectHref } from '@/lib/use-login-redirect-href';
import { navigateProductTextSearch } from '@/lib/navigate-product-text-search';
import LazyDesktopImageSearchPopover from '@/components/LazyDesktopImageSearchPopover';
import NanoAiProductPageContext from '@/components/NanoAiProductPageContext';

interface ProductDetailClientProps {
  initialProduct: Product;
  slug: string;
}

export default function ProductDetailClient({
  initialProduct,
  slug,
}: ProductDetailClientProps) {
  const router = useRouter();
  const [product, setProduct] = useState<Product>(initialProduct);
  const [isFavorited, setIsFavorited] = useState(false);
  const [qaModalOpen, setQaModalOpen] = useState(false);
  const [reviewsModalOpen, setReviewsModalOpen] = useState(false);
  const [selectedColorImage, setSelectedColorImage] = useState<string | null>(null);
  const [categoryTree, setCategoryTree] = useState<CategoryLevel1[]>([]);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [openLevel1, setOpenLevel1] = useState<string | null>(null);
  const [isStickyPinned, setIsStickyPinned] = useState(false);
  const [stickySearchTerm, setStickySearchTerm] = useState('');
  const stickyBarRef = useRef<HTMLDivElement>(null);
  const menuCloseTimerRef = useRef<number | null>(null);
  const { addToCart, isLoading: cartLoading, getCartItemCount } = useCart();
  const { isAuthenticated, user } = useAuth();
  const { refreshFavorites, favoriteCount } = useFavorites();
  const loginHref = useLoginRedirectHref();
  const { pushToast } = useToast();

  /** Đã xem: lưu theo phiên khách (header X-Guest-Session-Id) hoặc tài khoản — merge khi đăng nhập */
  useEffect(() => {
    if (!product?.id) return;
    apiClient.trackProductView(product.id, {
      id: product.id,
      product_id: product.product_id,
      name: product.name,
      price: product.price,
      main_image: product.main_image,
      brand_name: product.brand_name,
      slug: product.slug,
    }).catch(() => {});
  }, [product?.id, product?.name, product?.price, product?.main_image, product?.brand_name, product?.slug, product?.product_id]);

  useEffect(() => {
    setSelectedColorImage(null);
  }, [product?.id]);

  useEffect(() => {
    persistRelatedFiltersFromProduct(product);
  }, [product]);

  useEffect(() => {
    let active = true;
    let idleHandle: number | undefined;
    let timeoutId: ReturnType<typeof setTimeout> | undefined;
    const load = () => {
      apiClient.getCategoryTreeFromProducts()
        .then((data) => {
          if (!active) return;
          const tree = Array.isArray(data) ? data : [];
          setCategoryTree(tree);
        })
        .catch(() => {
          if (active) setCategoryTree([]);
        });
    };
    if (typeof window !== 'undefined' && 'requestIdleCallback' in window) {
      idleHandle = window.requestIdleCallback(load, { timeout: 2800 });
    } else {
      timeoutId = setTimeout(load, 0);
    }
    return () => {
      active = false;
      if (idleHandle !== undefined && typeof window !== 'undefined' && 'cancelIdleCallback' in window) {
        window.cancelIdleCallback(idleHandle);
      }
      if (timeoutId !== undefined) clearTimeout(timeoutId);
    };
  }, []);

  useEffect(() => {
    if (categoryTree.length && !openLevel1) setOpenLevel1(categoryTree[0].name);
  }, [categoryTree, openLevel1]);

  useEffect(() => {
    const handleScroll = () => {
      if (!stickyBarRef.current) return;
      const rect = stickyBarRef.current.getBoundingClientRect();
      setIsStickyPinned(rect.top <= 0);
    };
    handleScroll();
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  useEffect(() => {
    if (!product?.id) return;
    apiClient.isProductFavorited(product.id).then((r) => setIsFavorited(r.is_favorited)).catch(() => setIsFavorited(false));
  }, [product?.id]);

  const handleAddToCart = async (p: Product, quantity: number, selectedSize?: string, selectedColor?: string) => {
    try {
      const lineImg = cartLineMainImage(p, selectedColor);
      await addToCart({
        product_id: p.id,
        quantity,
        selected_size: selectedSize,
        selected_color: selectedColor,
        line_image_url: lineImg,
        product_data: {
          id: p.id,
          product_id: p.product_id,
          name: p.name,
          price: p.price,
          main_image: lineImg,
          brand_name: p.brand_name,
          available: p.available,
          original_price: p.original_price,
          slug: p.slug,
        },
      });
      pushToast({ title: 'Đã thêm vào giỏ hàng', variant: 'success', durationMs: 2000 });
      trackEvent('add_to_cart_click', { product_id: p.id, quantity });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      if (message.includes('Authentication required') || message.includes('401')) {
        pushToast({ title: 'Vui lòng đăng nhập lại', description: 'Phiên đăng nhập đã hết hạn.', variant: 'info', durationMs: 2500 });
        router.push(buildAuthLoginHrefFromFullPath(getBrowserReturnLocation()));
      } else {
        pushToast({ title: 'Không thể thêm vào giỏ hàng', description: message, variant: 'error', durationMs: 3000 });
      }
    }
  };

  const handleToggleFavorite = async (p: Product) => {
    try {
      if (isFavorited) {
        await apiClient.removeFromFavorites(p.id);
        setIsFavorited(false);
        setProduct((prev) => (prev && prev.id === p.id ? { ...prev, likes: Math.max(0, (prev.likes ?? 0) - 1) } : prev));
        trackEvent('favorite_remove', { product_id: p.id });
        pushToast({ title: 'Đã bỏ yêu thích', variant: 'success', durationMs: 2000 });
      } else {
        await apiClient.addToFavorites(p.id, {
          id: p.id,
          product_id: p.product_id,
          name: p.name,
          price: p.price,
          main_image: p.main_image,
          brand_name: p.brand_name,
          slug: p.slug,
        });
        setIsFavorited(true);
        setProduct((prev) => (prev && prev.id === p.id ? { ...prev, likes: (prev.likes ?? 0) + 1 } : prev));
        trackEvent('favorite_add', { product_id: p.id });
        pushToast({ title: 'Đã thêm vào yêu thích', variant: 'success', durationMs: 2000 });
      }
      await refreshFavorites();
    } catch (err: unknown) {
      if (err instanceof Error && (err.message.includes('Authentication') || err.message.includes('401'))) {
        pushToast({ title: 'Vui lòng đăng nhập lại', variant: 'info', durationMs: 2500 });
        router.push(buildAuthLoginHrefFromFullPath(getBrowserReturnLocation()));
      } else {
        pushToast({ title: 'Không thể cập nhật yêu thích', description: err instanceof Error ? err.message : 'Vui lòng thử lại', variant: 'error', durationMs: 3000 });
      }
    }
  };

  const handleStickySearch = (e: React.FormEvent) => {
    e.preventDefault();
    const term = stickySearchTerm.trim();
    if (!term) {
      router.push('/');
      return;
    }
    navigateProductTextSearch(router, term, categoryTree);
  };

  const handleMenuEnter = () => {
    if (menuCloseTimerRef.current) {
      window.clearTimeout(menuCloseTimerRef.current);
      menuCloseTimerRef.current = null;
    }
    setIsMenuOpen(true);
    if (!openLevel1 && categoryTree.length) setOpenLevel1(categoryTree[0].name);
  };

  const handleMenuLeave = () => {
    if (menuCloseTimerRef.current) window.clearTimeout(menuCloseTimerRef.current);
    menuCloseTimerRef.current = window.setTimeout(() => setIsMenuOpen(false), 150);
  };

  const openCategory = categoryTree.find((c) => c.name === openLevel1);
  const displayCartCount = getCartItemCount();

  const handleBuyNow = async (p: Product, quantity: number, selectedSize?: string, selectedColor?: string) => {
    try {
      const lineImg = cartLineMainImage(p, selectedColor);
      await addToCart(
        {
          product_id: p.id,
          quantity,
          selected_size: selectedSize,
          selected_color: selectedColor,
          line_image_url: lineImg,
          product_data: {
            id: p.id,
            product_id: p.product_id,
            name: p.name,
            price: p.price,
            main_image: lineImg,
            brand_name: p.brand_name,
            available: p.available,
            original_price: p.original_price,
            slug: p.slug,
          },
        },
        { skipAddedPopup: true }
      );
      trackEvent('buy_now', { product_id: p.id, quantity });
      router.push('/checkout');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      if (message.includes('Authentication required') || message.includes('401')) {
        pushToast({ title: 'Vui lòng đăng nhập lại', description: 'Phiên đăng nhập đã hết hạn.', variant: 'info', durationMs: 2500 });
        router.push(buildAuthLoginHrefFromFullPath(getBrowserReturnLocation()));
      } else {
        pushToast({ title: 'Không thể mua hàng', description: message, variant: 'error', durationMs: 3000 });
      }
    }
  };

  const normalizePriceValue = (value?: string | number | null, mode: 'min' | 'max' = 'min'): number | null => {
    if (value === undefined || value === null) return null;
    if (typeof value === 'number') return Number.isFinite(value) ? value : null;
    const matches = value.match(/\d[\d.,]*/g) || [];
    if (matches.length === 0) return null;
    const pick = mode === 'max' ? matches[matches.length - 1] : matches[0];
    if (!pick) return null;
    const cleaned = pick.replace(/[^\d]/g, '');
    if (!cleaned) return null;
    const parsed = Number(cleaned);
    return Number.isFinite(parsed) ? parsed : null;
  };

  const buildFilterLink = (
    params: Record<string, string | number | undefined | null>,
    fallbackQuery?: string
  ) => {
    const query: Record<string, string> = {};
    Object.entries(params).forEach(([key, val]) => {
      if (val === undefined || val === null || val === '') return;
      query[key] = String(val);
    });
    if (Object.keys(query).length === 0 && fallbackQuery) {
      query.q = fallbackQuery;
    }
    return { pathname: '/', query };
  };

  const sameCategoryParams = {
    category: product.category || undefined,
    subcategory: product.subcategory || undefined,
    sub_subcategory: product.sub_subcategory || undefined,
  };
  const normalizeGroupValue = (value?: string | null) => {
    if (!value) return null;
    const trimmed = value.trim();
    if (!trimmed) return null;
    if (trimmed.toLowerCase() === 'nan') return null;
    return trimmed;
  };
  const lowerGroup = normalizeGroupValue(product.pro_lower_price ?? null);
  const higherGroup = normalizeGroupValue(product.pro_high_price ?? null);
  const shopIdGroup = normalizeGroupValue(product.shop_id ?? null);
  const shopNameGroup = normalizeGroupValue(product.shop_name ?? null);

  const nanoImageList = useMemo(() => {
    const ordered = [product.main_image, ...(product.images || [])].filter(Boolean) as string[];
    return [...new Set(ordered)];
  }, [product.main_image, product.images]);

  const nanoPrimaryImage =
    (selectedColorImage && selectedColorImage.trim()) || nanoImageList[0] || '';
  const nanoSecondaryImage =
    nanoImageList.find((u) => u !== nanoPrimaryImage) || null;
  const nanoSku = (product.code?.trim() || product.product_id || String(product.id)).trim();
  const nanoProductPath = `/products/${product.slug || slug}`;

  return (
    <div className="min-h-screen bg-gray-50">
      <NanoAiProductPageContext
        sku={nanoSku}
        primaryImageUrl={nanoPrimaryImage}
        secondaryImageUrl={nanoSecondaryImage}
        productPath={nanoProductPath}
        inventoryId={product.inventory_id ?? null}
      />
      {/* Mobile: giao diện chi tiết sản phẩm theo bản mobile (chỉ trang này) */}
      <div className="md:hidden">
        <ProductDetailMobile
          product={product}
          isFavorited={isFavorited}
          isCartLoading={cartLoading}
          onAddToCart={handleAddToCart}
          onBuyNow={handleBuyNow}
          onToggleFavorite={handleToggleFavorite}
        />
      </div>

      {/* Desktop: layout cũ */}
      <div className="hidden md:block">
        <ProductHeader product={product} />
        <div
          ref={stickyBarRef}
          className={`sticky top-0 left-0 right-0 z-[30] backdrop-blur border-b border-gray-100 ${isStickyPinned ? 'bg-[#ea580c]' : 'bg-white/95'}`}
        >
          <div className="max-w-7xl mx-auto px-4 py-0">
            <div className="grid grid-cols-[minmax(12rem,17.33rem)_minmax(0,1fr)_9.33rem] items-center gap-2 md:gap-3 xl:grid-cols-[minmax(13.33rem,21.33rem)_minmax(0,1fr)_9.33rem]">
              <div className={`min-w-0 ${isStickyPinned ? '' : 'pointer-events-none opacity-0'}`}>
                <div className="flex min-w-0 items-center gap-2">
                  <Link
                    href="/"
                    className="flex shrink-0 items-center rounded-md py-0.5 hover:bg-white/10 transition-colors"
                    aria-label="Về trang chủ 188.com.vn"
                  >
                    <Image
                      src="https://188comvn.b-cdn.net/logo%20head%20188.png"
                      alt="188.com.vn"
                      width={140}
                      height={35}
                      className="h-7 w-auto max-w-[6.5rem] md:max-w-[8rem] object-contain object-left"
                    />
                  </Link>
                  <div
                    className="relative"
                    onMouseEnter={handleMenuEnter}
                    onMouseLeave={handleMenuLeave}
                  >
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-[11px] font-medium bg-white/20 text-white hover:bg-white/30 shadow-sm whitespace-nowrap"
                    >
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                      </svg>
                      Danh mục
                    </button>

                    {isStickyPinned && isMenuOpen && (
                      <div
                        className="absolute left-0 top-full mt-0 w-[720px] bg-white border border-gray-200 shadow-lg rounded-xl overflow-hidden z-[40] py-2"
                        onMouseEnter={handleMenuEnter}
                        onMouseLeave={handleMenuLeave}
                      >
                        <div className="grid grid-cols-[220px_1fr]">
                          <div className="bg-gray-50/80 border-r border-gray-100 p-3">
                            <div className="grid grid-cols-1 gap-1">
                              {categoryTree.length === 0 && (
                                <div className="text-xs text-gray-500">Chưa có danh mục.</div>
                              )}
                              {categoryTree.map((level1) => {
                                const slug1 = level1.slug || level1.name;
                                const isActive = openLevel1 === level1.name;
                                return (
                                  <Link
                                    key={level1.name}
                                    href={`/danh-muc/${encodeURIComponent(slug1)}`}
                                    onMouseEnter={() => setOpenLevel1(level1.name)}
                                    className={`px-2.5 py-2 rounded-md text-xs font-medium truncate ${
                                      isActive ? 'bg-orange-50 text-orange-700' : 'text-gray-700 hover:bg-white'
                                    }`}
                                  >
                                    {level1.name}
                                  </Link>
                                );
                              })}
                            </div>
                          </div>
                          <div className="p-3">
                            {!openCategory && (
                              <div className="text-xs text-gray-500">Di chuột vào danh mục để xem cấp 2, cấp 3.</div>
                            )}
                            {openCategory && (
                              <div className="grid grid-cols-2 gap-3">
                                {openCategory.children.map((level2) => {
                                  const slug1 = openCategory.slug || openCategory.name;
                                  const slug2 = level2.slug || level2.name;
                                  return (
                                    <div key={level2.name} className="min-w-0">
                                      <Link
                                        href={`/danh-muc/${encodeURIComponent(slug1)}/${encodeURIComponent(slug2)}`}
                                        className="block text-xs font-semibold text-gray-800 hover:text-[#ea580c]"
                                      >
                                        {level2.name}
                                      </Link>
                                      {level2.children && level2.children.length > 0 && (
                                        <div className="mt-1 flex flex-col gap-1">
                                          {level2.children.map((level3) => {
                                            const name3 = level3.name;
                                            const slug3 = level3.slug || level3.name;
                                            return (
                                              <Link
                                                key={name3}
                                                href={`/danh-muc/${encodeURIComponent(slug1)}/${encodeURIComponent(slug2)}/${encodeURIComponent(slug3)}`}
                                                className="text-[11px] text-gray-600 hover:text-[#ea580c] truncate"
                                              >
                                                {name3}
                                              </Link>
                                            );
                                          })}
                                        </div>
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                  <form
                    onSubmit={handleStickySearch}
                    className="relative ml-2 flex w-full min-w-[8rem] flex-1 items-stretch overflow-hidden rounded-lg bg-white focus-within:ring-2 focus-within:ring-orange-200 lg:ml-3"
                  >
                    <input
                      type="text"
                      value={stickySearchTerm}
                      onChange={(e) => setStickySearchTerm(e.target.value)}
                      placeholder="Tìm kiếm..."
                      autoComplete="off"
                      className="min-w-0 flex-1 border-0 bg-transparent py-1.5 pl-2.5 pr-1.5 text-xs text-gray-800 placeholder:text-gray-500 focus:outline-none focus:ring-0"
                    />
                    <div className="flex shrink-0 items-center gap-0.5 border-l border-gray-100/80 bg-white px-1">
                      <LazyDesktopImageSearchPopover
                        panelZClass="z-[110]"
                        triggerPosition="inline-end"
                        triggerButtonClassName="text-gray-500 hover:text-[#ea580c] p-0.5 rounded-md focus:outline-none focus:ring-2 focus:ring-[#ea580c]/40 [&_svg]:h-4 [&_svg]:w-4"
                      />
                      <button
                        type="submit"
                        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-gray-500 hover:text-[#ea580c]"
                        aria-label="Tìm kiếm"
                      >
                        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                          />
                        </svg>
                      </button>
                    </div>
                  </form>
                </div>
              </div>

              <div className={`flex flex-wrap items-center justify-center gap-2 ${isStickyPinned ? 'bg-transparent px-2 py-1.5' : 'bg-[#ea580c] rounded-lg px-2 py-1.5'}`}>
                {shopIdGroup && (
                  <Link
                    href={buildFilterLink({ shop_id: shopIdGroup })}
                    className="px-2.5 py-1.5 rounded-md text-xs font-semibold text-white bg-white/20 hover:bg-white/30 transition-colors"
                  >
                    Sản phẩm bán chạy
                  </Link>
                )}
                {lowerGroup && (
                  <Link
                    href={buildFilterLink({ pro_lower_price: lowerGroup }, lowerGroup)}
                    className="px-2.5 py-1.5 rounded-md text-xs font-semibold text-white bg-white/20 hover:bg-white/30 transition-colors"
                  >
                    Cùng loại giá thấp hơn
                  </Link>
                )}
                {shopNameGroup && (
                  <Link
                    href={buildFilterLink({ shop_name: shopNameGroup })}
                    className="px-2.5 py-1.5 rounded-md text-xs font-semibold text-white bg-white/20 hover:bg-white/30 transition-colors"
                  >
                    Cùng loại cùng tầm giá
                  </Link>
                )}
                {higherGroup && (
                  <Link
                    href={buildFilterLink({ pro_high_price: higherGroup }, higherGroup)}
                    className="px-2.5 py-1.5 rounded-md text-xs font-semibold text-white bg-white/20 hover:bg-white/30 transition-colors"
                  >
                    Cùng loại giá cao hơn
                  </Link>
                )}
              </div>

              <div className={`justify-self-end ${isStickyPinned ? '' : 'pointer-events-none opacity-0'}`}>
                <div className="flex h-5 items-center gap-4 px-2">
                  <Link href="/da-xem" className="flex items-center text-white/90 hover:text-white transition-colors group">
                    <div className="w-5 h-5 bg-white/20 rounded-full flex items-center justify-center group-hover:bg-white/30 transition-colors">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                      </svg>
                    </div>
                  </Link>

                  {isAuthenticated ? (
                    <Link href="/account" className="flex items-center text-white/90 hover:text-white transition-colors group">
                      <div className="w-5 h-5 bg-white/20 rounded-full flex items-center justify-center group-hover:bg-white/30 transition-colors">
                        <span className="text-white font-semibold text-[11px]">
                          {user?.full_name?.charAt(0) || 'U'}
                        </span>
                      </div>
                    </Link>
                  ) : (
                    <Link href={loginHref} className="flex items-center text-white/90 hover:text-white transition-colors group">
                      <div className="w-5 h-5 bg-white/20 rounded-full flex items-center justify-center group-hover:bg-white/30 transition-colors">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                        </svg>
                      </div>
                    </Link>
                  )}

                  <Link href="/favorites" className="flex items-center text-white/90 hover:text-white transition-colors group relative">
                    <div className="w-5 h-5 bg-white/20 rounded-full flex items-center justify-center group-hover:bg-white/30 transition-colors relative">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
                      </svg>
                      {favoriteCount > 0 && (
                        <span className="absolute -right-px -top-px bg-white text-[#ea580c] rounded-full min-w-[11px] h-3 px-0.5 text-[7px] sm:text-[8px] flex items-center justify-center font-semibold leading-none shadow-sm ring-1 ring-black/5">
                          {favoriteCount}
                        </span>
                      )}
                    </div>
                  </Link>

                  <Link href="/cart" className="flex items-center text-white/90 hover:text-white transition-colors group relative">
                    <div className="w-5 h-5 bg-white/20 rounded-full flex items-center justify-center group-hover:bg-white/30 transition-colors relative">
                      <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" />
                      </svg>
                      {displayCartCount > 0 && (
                        <span className="absolute -right-px -top-px bg-white text-[#ea580c] rounded-full min-w-[11px] h-3 px-0.5 text-[7px] sm:text-[8px] flex items-center justify-center font-semibold leading-none shadow-sm ring-1 ring-black/5">
                          {displayCartCount}
                        </span>
                      )}
                    </div>
                  </Link>
                </div>
              </div>
            </div>
          </div>
        </div>
        <main
          id="main-content"
          className="max-w-7xl mx-auto px-4 py-5 md:pt-0 md:pb-20"
          role="main"
          aria-label="Nội dung chính - Chi tiết sản phẩm"
        >
          <article className="bg-white rounded-xl shadow-lg overflow-visible" aria-label={product.name}>
            <div className="p-4">
              <div className="grid grid-cols-1 lg:grid-cols-[1fr_1fr] gap-6">
              <div className="self-start">
                <ProductGallery
                  product={product}
                  selectedImageUrl={selectedColorImage}
                  onSelectImage={setSelectedColorImage}
                />
              </div>
              <ProductInfo
                product={product}
                onAddToCart={handleAddToCart}
                onToggleFavorite={handleToggleFavorite}
                onBuyNow={handleBuyNow}
                onOpenQA={() => setQaModalOpen(true)}
                onOpenReviews={() => setReviewsModalOpen(true)}
                isCartLoading={cartLoading}
                isFavorited={isFavorited}
                onColorImageChange={setSelectedColorImage}
              />
            </div>
            </div>
            <div className="border-t">
              <ProductTabs product={product} />
            </div>
            <ProductQASection product={product} modalOnly modalOpen={qaModalOpen} onModalClose={() => setQaModalOpen(false)} onModalOpen={() => setQaModalOpen(true)} />
            <ProductReviewSection product={product} modalOnly modalOpen={reviewsModalOpen} onModalClose={() => setReviewsModalOpen(false)} onModalOpen={() => setReviewsModalOpen(true)} />
          </article>
          <RelatedProducts currentProduct={product} />
        </main>
      </div>
    </div>
  );
}
