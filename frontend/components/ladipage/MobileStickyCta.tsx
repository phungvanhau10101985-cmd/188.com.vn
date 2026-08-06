'use client';

interface MobileStickyCtaProps {
  label: string;
  onClick: () => void;
}

/** CTA chỉ hiển thị trên mobile để luôn giữ bước tiếp theo trong tầm tay. */
export default function MobileStickyCta({ label, onClick }: MobileStickyCtaProps) {
  return (
    <div className="fixed inset-x-0 bottom-0 z-30 border-t border-orange-100 bg-white/95 px-4 py-3 shadow-[0_-8px_24px_rgba(31,41,55,0.10)] backdrop-blur md:hidden">
      <button
        type="button"
        onClick={onClick}
        className="flex w-full items-center justify-center rounded-full bg-gray-950 px-5 py-3.5 text-sm font-bold text-white transition hover:bg-orange-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-600"
      >
        {label}
        <span aria-hidden="true" className="ml-2 text-base leading-none">→</span>
      </button>
    </div>
  );
}
