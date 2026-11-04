import WhyDepositPage from '@/components/deposit/WhyDepositPage';
import { getApiBaseUrl } from '@/lib/api-base';
import { BUSINESS_ZALO } from '@/lib/business-info';
import {
  DEPOSIT_POLICY_FALLBACK,
  depositPolicyFromApi,
  type DepositPolicy,
} from '@/lib/deposit-policy';
import { fetchPublicSiteEmbeds } from '@/lib/site-embeds-public';

export const metadata = {
  title: 'Tại sao phải đặt cọc?',
  description:
    'Vì sao đơn hàng gửi từ nước ngoài cần đặt cọc: phí mua hàng, vận chuyển quốc tế và rủi ro nếu hủy đơn. Quý khách chỉ cọc một phần, phần còn lại trả khi nhận.',
};

function oneParam(value: string | string[] | undefined): string {
  if (Array.isArray(value)) return value[0] ?? '';
  return value ?? '';
}

function safeOrderId(raw: string): number | null {
  if (!/^\d{1,10}$/.test(raw)) return null;
  const id = Number(raw);
  return Number.isInteger(id) && id > 0 ? id : null;
}

function safeOrderCode(raw: string): string {
  const code = raw.trim();
  return /^[A-Za-z0-9]{2,20}$/.test(code) ? code : '';
}

async function loadDepositPolicy(): Promise<DepositPolicy> {
  try {
    const res = await fetch(`${getApiBaseUrl()}/bank-accounts/deposit-percent`, {
      cache: 'no-store',
      signal: AbortSignal.timeout(8000),
    });
    if (!res.ok) return DEPOSIT_POLICY_FALLBACK;
    return depositPolicyFromApi(await res.json());
  } catch {
    return DEPOSIT_POLICY_FALLBACK;
  }
}

export default async function TaiSaoDatCocPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const [embeds, deposit] = await Promise.all([fetchPublicSiteEmbeds(), loadDepositPolicy()]);
  const zaloUrl = embeds.zaloPersonalUrl || BUSINESS_ZALO;
  return (
    <WhyDepositPage
      orderId={safeOrderId(oneParam(sp.order))}
      orderCode={safeOrderCode(oneParam(sp.code))}
      zaloUrl={zaloUrl}
      deposit={deposit}
    />
  );
}
