'use client';

import EditableText from './EditableText';
import type { TrustCtaSectionData } from './types';

interface TrustCtaSectionProps {
  data: TrustCtaSectionData;
  editable?: boolean;
  isBusy?: boolean;
  onSaveField?: (field: keyof TrustCtaSectionData, value: string) => void | Promise<void>;
  onRegenerate?: (instruction: string) => void | Promise<void>;
  onCtaClick?: () => void;
}

export default function TrustCtaSection({
  data,
  editable = false,
  isBusy = false,
  onSaveField,
  onRegenerate,
  onCtaClick,
}: TrustCtaSectionProps) {
  return (
    <section className="relative my-8 overflow-hidden rounded-[1.75rem] bg-gradient-to-br from-gray-950 via-gray-900 to-orange-950 px-6 py-11 text-center text-white shadow-xl shadow-orange-900/15 md:my-12 md:px-10 md:py-14">
      <div aria-hidden="true" className="absolute -left-12 -top-16 h-48 w-48 rounded-full bg-orange-500/20 blur-3xl" />
      <div aria-hidden="true" className="absolute -bottom-20 -right-8 h-56 w-56 rounded-full bg-amber-400/15 blur-3xl" />
      <div className="relative">
      <p className="mb-3 text-xs font-bold uppercase tracking-[0.18em] text-orange-200">Sẵn sàng chọn sản phẩm phù hợp?</p>
      <EditableText
        as="p"
        value={data.body || ''}
        placeholder="Chưa có nội dung kêu gọi hành động"
        className="mx-auto max-w-2xl text-lg font-medium leading-relaxed text-white md:text-xl"
        multiline
        editable={editable}
        isBusy={isBusy}
        onSave={onSaveField ? (v) => onSaveField('body', v) : undefined}
        onRegenerate={onRegenerate}
        regenerateLabel="Yêu cầu thêm (có thể để trống)"
      />
      <button
        type="button"
        onClick={onCtaClick}
        className="mt-7 inline-flex items-center justify-center rounded-full bg-white px-8 py-3.5 text-sm font-bold text-gray-950 shadow-lg transition hover:-translate-y-0.5 hover:bg-orange-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
      >
        {data.cta_label || 'Mua ngay'}
        <span aria-hidden="true" className="ml-2 text-base leading-none">→</span>
      </button>
      <p className="mt-4 text-xs text-gray-300">Xem chi tiết sản phẩm trước khi đưa ra lựa chọn.</p>
      </div>
    </section>
  );
}
