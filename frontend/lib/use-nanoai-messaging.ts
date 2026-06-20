'use client';

import { useCallback } from 'react';
import { useToast } from '@/components/ToastProvider';
import { trackEvent } from '@/lib/analytics';
import { apiClient } from '@/lib/api-client';
import { useAuth } from '@/features/auth/hooks/useAuth';
import {
  buildNanoAiGatewayPayloadFrom188Product,
  buildNanoAiTryOnCtxFrom188Product,
  clearNanoAiPartnerCustomer,
  openNanoAiConsultEmbed,
  openNanoAiTryOnEmbed,
  setNanoAiPartnerCustomerToken,
  type NanoAiGatewayPayload,
  type NanoAiTryOnCtx,
} from '@/lib/nanoai-hosted-chat';

export function useNanoAiMessaging() {
  const { pushToast } = useToast();
  const { isAuthReady, isAuthenticated } = useAuth();

  const openConsult = useCallback(
    async (
      payload: NanoAiGatewayPayload,
      analytics?: { source: string; productId?: number },
    ) => {
      let customerToken = '';
      if (isAuthReady && isAuthenticated) {
        try {
          const resp = await apiClient.nanoaiCustomerToken();
          customerToken = (resp.token || '').trim();
          if (customerToken) {
            setNanoAiPartnerCustomerToken(customerToken);
          } else {
            clearNanoAiPartnerCustomer();
          }
        } catch {
          clearNanoAiPartnerCustomer();
        }
      }

      const result = openNanoAiConsultEmbed({
        ...payload,
        customerToken: customerToken || payload.customerToken,
      });
      if (!result.ok) {
        if (result.reason === 'missing_sku' || result.reason === 'missing_image') {
          pushToast({
            title: 'Thiếu thông tin sản phẩm',
            description:
              'Không mở được tư vấn — cần mã SP và ảnh (HTTPS, không video). Bấm lại hoặc mở chat góc màn hình.',
            variant: 'error',
            durationMs: 4200,
          });
        }
        return result;
      }
      trackEvent('nanoai_consult_open', {
        product_id: analytics?.productId,
        source: analytics?.source,
      });
      return result;
    },
    [isAuthReady, isAuthenticated, pushToast],
  );

  const openConsultForProduct = useCallback(
    (
      product: Parameters<typeof buildNanoAiGatewayPayloadFrom188Product>[0],
      opts: { imageUrl?: string | null; source: string },
    ) => {
      const payload = buildNanoAiGatewayPayloadFrom188Product(product, {
        imageUrl: opts.imageUrl,
      });
      return openConsult(payload, { source: opts.source, productId: product.id });
    },
    [openConsult],
  );

  const openTryOn = useCallback(
    async (
      ctx: NanoAiTryOnCtx,
      ctxSource: string,
      analytics: { source: string; productId?: number },
    ) => {
      const result = await openNanoAiTryOnEmbed(ctx, ctxSource);
      if (!result.ok) {
        if (result.reason === 'missing_image') {
          pushToast({
            title: 'Thiếu ảnh sản phẩm',
            description: 'Chọn ảnh sản phẩm (JPG/PNG/WebP) trước khi thử đồ.',
            variant: 'error',
            durationMs: 4200,
          });
        } else if (result.reason === 'no_chat_config') {
          pushToast({
            title: 'Chưa mở được thử đồ',
            description:
              'Kiểm tra mã nhúng NanoAI (data-chat-url trên script) hoặc biến NEXT_PUBLIC_NANOAI_CHAT_URL trong frontend.',
            variant: 'info',
            durationMs: 4200,
          });
        } else {
          pushToast({
            title: 'Chưa mở được khung chat',
            description: 'Bấm biểu tượng chat NanoAI góc màn hình — ngữ cảnh sản phẩm đã được gửi kèm.',
            variant: 'info',
            durationMs: 4200,
          });
        }
        return result;
      }
      trackEvent('nanoai_try_on_open', {
        product_id: analytics.productId,
        source: analytics.source,
        mode: result.mode,
      });
      return result;
    },
    [pushToast],
  );

  const openTryOnForProduct = useCallback(
    (
      product: Parameters<typeof buildNanoAiTryOnCtxFrom188Product>[0],
      opts: { imageUrl?: string | null; ctxSource: string; source: string },
    ) => {
      const ctx = buildNanoAiTryOnCtxFrom188Product(product, { imageUrl: opts.imageUrl });
      return openTryOn(ctx, opts.ctxSource, { source: opts.source, productId: product.id });
    },
    [openTryOn],
  );

  return {
    openConsult,
    openConsultForProduct,
    openTryOn,
    openTryOnForProduct,
  };
}
