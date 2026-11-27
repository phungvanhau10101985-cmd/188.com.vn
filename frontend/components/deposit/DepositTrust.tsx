'use client';

import { useId, useState } from 'react';
import Link from 'next/link';
import TrustConfirmList from '@/components/conversion/TrustConfirmList';
import { trackEvent } from '@/lib/analytics';

const PARTIAL_TRUST = [
  'Chỉ cọc một phần — còn lại trả khi nhận hàng',
  'Xem hàng trước khi trả phần còn lại',
  'Sai mô tả hoặc lỗi sản xuất: gửi lại hoặc hoàn tiền cọc',
  'Không vừa size: đổi size 1 lần',
] as const;

const FULL_TRUST = [
  'Cọc đủ, gồm phí ship — không trả thêm khi nhận',
  'Vẫn được xem hàng khi nhận',
  'Sai mô tả hoặc lỗi sản xuất: gửi lại hoặc hoàn tiền cọc',
  'Không vừa size: đổi size 1 lần',
] as const;

const PARTIAL_STEPS = [
  { title: 'Cọc', detail: 'Chuyển khoản' },
  { title: 'Xuất kho', detail: 'Đúng mẫu, size' },
  { title: 'Về Việt Nam', detail: 'Vận chuyển' },
  { title: 'Nhận hàng', detail: 'Xem, trả nốt' },
] as const;

const FULL_STEPS = [
  { title: 'Cọc', detail: 'Chuyển khoản' },
  { title: 'Xuất kho', detail: 'Đúng mẫu, size' },
  { title: 'Về Việt Nam', detail: 'Vận chuyển' },
  { title: 'Nhận hàng', detail: 'Xem hàng' },
] as const;

function DepositSteps({ steps }: { steps: readonly { title: string; detail: string }[] }) {
  return (
    <div className="relative">
      <span aria-hidden className="pointer-events-none absolute left-[12.5%] right-[12.5%] top-[11px] h-px bg-orange-200" />
      <ol className="relative grid grid-cols-4 gap-1">
        {steps.map((step, index) => (
          <li key={step.title} className="flex flex-col items-center text-center">
            <span
              className={`relative z-10 flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-bold ${
                index === 0
                  ? 'bg-orange-600 text-white shadow-sm'
                  : 'bg-white text-orange-700 ring-1 ring-orange-200'
              }`}
            >
              {index + 1}
            </span>
            <span className="mt-1 text-[10px] font-semibold leading-tight text-gray-900 md:text-xs">{step.title}</span>
            <span className="mt-0.5 hidden text-[10px] leading-tight text-gray-500 sm:block">{step.detail}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

export function DepositReassure({ mode }: { mode: 'partial' | 'full' }) {
  const items = mode === 'full' ? FULL_TRUST : PARTIAL_TRUST;
  const steps = mode === 'full' ? FULL_STEPS : PARTIAL_STEPS;

  return (
    <section aria-label="Cam kết khi đặt cọc" className="border-b border-gray-100 bg-white px-3 py-3 md:px-5">
      <div className="rounded-xl border border-orange-100 bg-gradient-to-b from-orange-50/90 to-white px-3 py-2.5 md:px-4 md:py-3">
        <TrustConfirmList items={items} layout="stack" label="Cam kết khi đặt cọc" />
        <p className="mt-2 text-[11px] leading-snug text-gray-500 md:text-xs">
          Cọc xong shop mới xuất kho và chuyển về Việt Nam.
        </p>
        <div className="mt-3 border-t border-orange-100 pt-2.5">
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-orange-900/70">Sau khi cọc</p>
          <DepositSteps steps={steps} />
        </div>
      </div>
    </section>
  );
}

export function WhyDepositDisclosure({
  orderId,
  orderCode,
  mode,
}: {
  orderId: number;
  orderCode: string;
  mode: 'partial' | 'full';
}) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const buttonId = useId();
  const policyHref = `/info/tai-sao-dat-coc?order=${orderId}&code=${encodeURIComponent(orderCode)}`;

  return (
    <div className="mt-3 w-full max-w-[280px] overflow-hidden rounded-xl border border-gray-200 bg-white text-left shadow-sm">
      <button
        id={buttonId}
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => {
          setOpen((current) => {
            const next = !current;
            if (next) trackEvent('deposit_why_open', { order_id: orderId, inline: true });
            return next;
          });
        }}
        className="flex min-h-[44px] w-full items-center justify-between gap-2 px-3 py-2.5 text-left text-sm font-semibold text-gray-800 hover:bg-gray-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-600"
      >
        <span>Vì sao cần đặt cọc?</span>
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 20 20"
          fill="currentColor"
          aria-hidden
          className={`h-4 w-4 shrink-0 text-gray-500 transition-transform ${open ? 'rotate-180' : ''}`}
        >
          <path
            fillRule="evenodd"
            d="M5.23 7.21a.75.75 0 011.06.02L10 11.17l3.71-3.94a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
            clipRule="evenodd"
          />
        </svg>
      </button>
      <div id={panelId} role="region" aria-labelledby={buttonId} hidden={!open} className="space-y-2 border-t border-gray-100 px-3 py-2.5">
        <p className="text-xs leading-relaxed text-gray-600">
          188 giữ hàng tại kho riêng ở nước ngoài và xuất đúng mẫu, đúng size. Đơn không chuyển sang shop khác để mua hộ.
        </p>
        <p className="text-xs leading-relaxed text-gray-600">
          Đưa về Việt Nam gồm cước quốc tế, thông quan và phí trong nước. Shop phải chi các khoản này trước khi hàng tới.
        </p>
        <p className="text-xs leading-relaxed text-gray-600">
          Cọc xác nhận giữ đơn. Hàng đã xuất kho thì phí đường về không thu lại được.
        </p>
        <p className="text-xs leading-relaxed text-gray-600">
          {mode === 'full'
            ? 'Cọc đủ gồm cả phí ship, không còn khoản phải trả lúc nhận. Quý khách vẫn xem hàng khi giao.'
            : 'Phần còn lại trả khi nhận hàng, sau khi quý khách đã xem hàng.'}
        </p>
        <Link
          href={policyHref}
          className="inline-flex min-h-[44px] items-center text-xs font-medium text-orange-700 underline underline-offset-2 hover:text-orange-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-600"
        >
          Đọc chính sách đầy đủ
        </Link>
      </div>
    </div>
  );
}
