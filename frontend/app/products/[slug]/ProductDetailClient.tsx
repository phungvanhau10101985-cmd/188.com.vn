'use client';

import { useState, useEffect, useMemo, useLayoutEffect } from 'react';
import { useRouter } from 'next/navigation';
import { apiClient } from '@/lib/api-client';
import { useCart } from '@/features/cart/hooks/useCart';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { useFavorites } from '@/features/favorites/hooks/useFavorites';
import type { Product } from '@/types/api';
import { ProductReviewsProvider } from '@/lib/product-reviews-context';
import ProductDetailDesktopChrome from './components/ProductDetailDesktopChrome';
import ProductGallery from './components/ProductGallery/ProductGallery';
import ProductInfo from './components/ProductInfo/ProductInfo';
import ProductTabs from '@/components/product-detail/ProductTabs';
import ProductQASection from './components/ProductQASection/ProductQASection';
import ProductReviewSection from './components/ProductReviewSection/ProductReviewSection';
import ProductDetailMobile from './ProductDetailMobile';
import SectionErrorBoundary from '@/components/ui/SectionErrorBoundary';
import { useToast } from '@/components/ToastProvider';
import { trackEvent } from '@/lib/analytics';
import {
  buildAddToCartRequestFromProduct,
  trackMarketingAddToCartIntent,
} from '@/lib/marketing-add-to-cart';
import { useProductMarketingView } from '@/lib/use-product-marketing-view';
import { parseRelatedTabFromSearch } from '@/lib/product-related-tabs';
import { prefetchRelatedProductsForPdp } from '@/lib/related-products-pdp-fetch';
import OutfitSuggestions, { prefetchOutfitSuggestionsForPdp } from '@/components/product-detail/OutfitSuggestions';
import { cartLineMainImage } from '@/lib/product-color-variant';
import { warehouseCartProductDataExtras } from '@/lib/warehouse-clearance';
import { filterVisibleWebImageUrls } from '@/lib/image-utils';
import { buildAuthLoginHrefFromFullPath, getBrowserReturnLocation } from '@/lib/auth-redirect';
import { queuePendingCartAfterLogin } from '@/features/cart/pending-cart-session';
import {
  getActiveGoogleAutomatedDiscountToken,
  markGoogleAutomatedDiscountCartLock,
  type GoogleAutomatedDiscountSsrPayload,
} from '@/lib/google-automated-discount';
import { productPathSlugFromApi } from '@/lib/product-path-slug';
import NanoAiProductPageContext from '@/components/NanoAiProductPageContext';
import NanoAiLauncherGatewaySync from '@/components/NanoAiLauncherGatewaySync';
import { buildNanoAiGatewayPayloadFrom188Product } from '@/lib/nanoai-hosted-chat';
import { resolveProductGroupListingPath } from '@/lib/product-oos-redirect';
import AgeGenderRecommendationSection from '@/components/AgeGenderRecommendationSection';

interface ProductDetailClientProps {
  initialProduct: Product;
  slug: string;
  /** Giá chiết khấu Google đã verify trên RSC khi URL có ?pv2= */
  initialGoogleDiscount?: GoogleAutomatedDiscountSsrPayload | null;
}

export default function ProductDetailClient({
  initialProduct,
  slug,
  initialGoogleDiscount = null,
}: ProductDetailClientProps) {
  const router = useRouter();
  const [product, setProduct] = useState<Product>(initialProduct);
  const [isFavorited, setIsFavorited] = useState(false);
  const [qaModalOpen, setQaModalOpen] = useState(false);
  const [reviewsModalOpen, setReviewsModalOpen] = useState(false);
  const [selectedColorImage, setSelectedColorImage] = useState<string | null>(null);
  const { addToCart, isLoading: cartLoading } = useCart();
  const [uiCartLoading, setUiCartLoading] = useState(false);
  useLayoutEffect(() => {
    setUiCartLoading(cartLoading);
  }, [cartLoading]);
  const { isAuthenticated, user, isLoading: authLoading } = useAuth();
  const { refreshFavorites } = useFavorites();
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

  /** Đồng bộ SP khi client-nav sang slug khác (tránh state cũ). */
  useEffect(() => {
    setProduct(initialProduct);
  }, [slug, initialProduct]);

  /**
   * Meta/TikTok ViewContent + Google view_item — nguồn chính: ProductMarketingTracker ở page.tsx.
   * Giữ hook dự phòng khi ProductDetailClient được mount độc lập (optimized-page / story).
   */
  useProductMarketingView(initialProduct, slug);

  useEffect(() => {
    setSelectedColorImage(null);
  }, [product?.id]);

  useEffect(() => {
    if (authLoading || !slug) return;
    let cancelled = false;
    apiClient
      .getProductBySlug(slug)
      .then((fresh) => {
        if (!cancelled && fresh?.id) setProduct(fresh);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [slug, authLoading, isAuthenticated, user?.id]);

  /** PDP hết hàng → listing nhóm (khớp SSR page.tsx). */
  useEffect(() => {
    if ((product.available ?? 0) > 0 || !slug) return;
    const embedded = (product.group_listing_path || '').trim();
    if (embedded) {
      router.replace(embedded);
      return;
    }
    let cancelled = false;
    resolveProductGroupListingPath(slug, { allowCache: true }).then((listingPath) => {
      if (cancelled || !listingPath) return;
      router.replace(listingPath);
    });
    return () => {
      cancelled = true;
    };
  }, [product.available, product.group_listing_path, slug, router]);

  /** Làm ấm cache SP liên quan (tab mặc định + tab trên URL) trước khi scroll tới khối dưới. */
  useEffect(() => {
    if (!product?.id) return;
    if (typeof window === 'undefined') return;
    const rt = new URLSearchParams(window.location.search).get('rt');
    const tab = parseRelatedTabFromSearch(rt);
    prefetchRelatedProductsForPdp(product, tab);
    if (tab !== 'bestselling') {
      prefetchRelatedProductsForPdp(product, 'bestselling');
    }
    prefetchOutfitSuggestionsForPdp(product.id);
  }, [product]);

  useEffect(() => {
    if (!product?.id) return;
    apiClient.isProductFavorited(product.id).then((r) => setIsFavorited(r.is_favorited)).catch(() => setIsFavorited(false));
  }, [product?.id]);

  const handleAddToCart = async (p: Product, quantity: number, selectedSize?: string, selectedColor?: string) => {
    const googlePv2Token = getActiveGoogleAutomatedDiscountToken(p.product_id);
    const payload = buildAddToCartRequestFromProduct(p, quantity, selectedSize, selectedColor, {
      google_pv2_token: googlePv2Token ?? undefined,
    });
    trackMarketingAddToCartIntent(payload);
    if (!isAuthenticated) {
      queuePendingCartAfterLogin(payload);
      pushToast({
        title: 'Đăng nhập để thêm giỏ',
        description: 'Sau đăng nhập bạn sẽ được chuyển tới giỏ hàng với sản phẩm đã chọn.',
        variant: 'info',
        durationMs: 3200,
      });
      router.push(buildAuthLoginHrefFromFullPath('/cart'));
      trackEvent('add_to_cart_click', { product_id: p.id, quantity, status: 'requires_login' });
      return;
    }
    try {
      await addToCart(payload);
      if (googlePv2Token && p.product_id) {
        markGoogleAutomatedDiscountCartLock(p.product_id);
      }
      pushToast({ title: 'Đã thêm vào giỏ hàng', variant: 'success', durationMs: 2000 });
      trackEvent('add_to_cart_click', { product_id: p.id, quantity });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      if (message.includes('Authentication required') || message.includes('401')) {
        pushToast({ title: 'Vui lòng đăng nhập lại', description: 'Phiên đăng nhập đã hết hạn.', variant: 'info', durationMs: 2500 });
        router.push(buildAuthLoginHrefFromFullPath(getBrowserReturnLocation()));
      } else if (/đã có.*trong giỏ|chỉ còn \d+/i.test(message)) {
        pushToast({ title: 'Không thể tăng số lượng', description: message, variant: 'info', durationMs: 3500 });
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

  const handleBuyNow = async (p: Product, quantity: number, selectedSize?: string, selectedColor?: string) => {
    const lineImg = cartLineMainImage(p, selectedColor);
    const googlePv2Token = getActiveGoogleAutomatedDiscountToken(p.product_id);
    const payload = {
      product_id: p.id,
      quantity,
      selected_size: selectedSize,
      selected_color: selectedColor,
      line_image_url: lineImg,
      google_pv2_token: googlePv2Token ?? undefined,
      product_data: {
        id: p.id,
        code: p.code,
        product_id: p.product_id,
        name: p.name,
        price: p.price,
        list_price:
          p.original_price != null && p.original_price > (p.price ?? 0) ? p.original_price : p.price,
        main_image: lineImg,
        brand_name: p.brand_name,
        available: p.available,
        original_price: p.original_price,
        slug: p.slug,
        ...warehouseCartProductDataExtras(p),
      },
    };
    if (!isAuthenticated) {
      queuePendingCartAfterLogin(payload);
      pushToast({
        title: 'Đăng nhập để mua hàng',
        description: 'Sau đăng nhập bạn sẽ được chuyển tới giỏ hàng với sản phẩm đã chọn.',
        variant: 'info',
        durationMs: 3200,
      });
      router.push(buildAuthLoginHrefFromFullPath('/cart'));
      trackEvent('buy_now', { product_id: p.id, quantity, status: 'requires_login' });
      return;
    }
    try {
      await addToCart(payload, { skipAddedPopup: true });
      if (googlePv2Token && p.product_id) {
        markGoogleAutomatedDiscountCartLock(p.product_id);
      }
      trackEvent('buy_now', { product_id: p.id, quantity });
      router.push('/cart');
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

  const nanoImageList = useMemo(() => {
    const ordered = [product.main_image, ...(product.images || [])].filter(Boolean) as string[];
    return filterVisibleWebImageUrls([...new Set(ordered)]);
  }, [product.main_image, product.images]);

  const nanoPrimaryImage =
    (selectedColorImage && selectedColorImage.trim()) || nanoImageList[0] || '';
  const nanoSecondaryImage =
    nanoImageList.find((u) => u !== nanoPrimaryImage) || null;
  const nanoSku = (product.code?.trim() || product.product_id || String(product.id)).trim();
  const nanoSeg = productPathSlugFromApi(product.slug, product.product_id) || slug;
  const nanoProductPath = `/products/${nanoSeg}`;
  const nanoGatewayPayload = useMemo(
    () =>
      buildNanoAiGatewayPayloadFrom188Product(product, {
        imageUrl: nanoPrimaryImage,
      }),
    [product, nanoPrimaryImage],
  );

  return (
    <ProductReviewsProvider productId={product.id}>
    <div className="min-h-screen bg-gray-50">
      <NanoAiProductPageContext
        sku={nanoSku}
        primaryImageUrl={nanoPrimaryImage}
        secondaryImageUrl={nanoSecondaryImage}
        productPath={nanoProductPath}
        inventoryId={product.inventory_id ?? null}
      />
      <NanoAiLauncherGatewaySync payload={nanoGatewayPayload} />
      {/* Mobile: giao diện chi tiết sản phẩm theo bản mobile (chỉ trang này) */}
      <div className="md:hidden">
        <ProductDetailMobile
          product={product}
          isFavorited={isFavorited}
          isCartLoading={uiCartLoading}
          onAddToCart={handleAddToCart}
          onBuyNow={handleBuyNow}
          onToggleFavorite={handleToggleFavorite}
          initialGoogleDiscount={initialGoogleDiscount}
        />
      </div>

      {/* Desktop: layout cũ */}
      <div className="hidden md:block">
        <ProductDetailDesktopChrome product={product} />
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
                <SectionErrorBoundary>
                  <ProductGallery
                    product={product}
                    selectedImageUrl={selectedColorImage}
                    onSelectImage={setSelectedColorImage}
                  />
                </SectionErrorBoundary>
              </div>
              <SectionErrorBoundary>
                <ProductInfo
                  product={product}
                  viewingImageUrl={nanoPrimaryImage}
                  onAddToCart={handleAddToCart}
                  onToggleFavorite={handleToggleFavorite}
                  onBuyNow={handleBuyNow}
                  onOpenQA={() => setQaModalOpen(true)}
                  onOpenReviews={() => setReviewsModalOpen(true)}
                  isCartLoading={uiCartLoading}
                  isFavorited={isFavorited}
                  onColorImageChange={setSelectedColorImage}
                  initialGoogleDiscount={initialGoogleDiscount}
                />
              </SectionErrorBoundary>
            </div>
            </div>
            <div className="hidden md:block px-4 pb-2">
              <SectionErrorBoundary>
                <OutfitSuggestions product={product} layout="desktop" />
              </SectionErrorBoundary>
            </div>
            <div className="border-t">
              <SectionErrorBoundary>
                <ProductTabs product={product} layout="desktop" />
              </SectionErrorBoundary>
            </div>
            <ProductQASection product={product} modalOnly modalOpen={qaModalOpen} onModalClose={() => setQaModalOpen(false)} onModalOpen={() => setQaModalOpen(true)} />
            <ProductReviewSection product={product} modalOnly modalOpen={reviewsModalOpen} onModalClose={() => setReviewsModalOpen(false)} onModalOpen={() => setReviewsModalOpen(true)} />
          </article>

          <SectionErrorBoundary>
            <AgeGenderRecommendationSection excludeProductId={product.id} className="mt-6" />
          </SectionErrorBoundary>
        </main>
      </div>
    </div>
    </ProductReviewsProvider>
  );
}
