function ConfirmMark() {
  return (
    <span
      aria-hidden
      className="mt-px flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full bg-orange-600 text-white"
    >
      <svg viewBox="0 0 16 16" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3.5 8.5 6.5 11.5 12.5 4.5" />
      </svg>
    </span>
  );
}

type TrustConfirmListProps = {
  items: readonly string[];
  /** two: 2 cột (popup). stack: 1 cột trên mobile, 2 cột từ sm (trang cọc). */
  layout?: 'two' | 'stack';
  label: string;
};

/** Dòng cam kết có dấu xác nhận — không phải nút. */
export default function TrustConfirmList({ items, layout = 'stack', label }: TrustConfirmListProps) {
  const cols = layout === 'two' ? 'grid-cols-2' : 'grid-cols-1 sm:grid-cols-2';

  return (
    <ul aria-label={label} className={`grid ${cols} gap-x-3 gap-y-1.5`}>
      {items.map((text) => (
        <li key={text} className="flex min-w-0 items-start gap-1.5">
          <ConfirmMark />
          <span className="text-[11px] font-medium leading-snug text-gray-800 md:text-xs">{text}</span>
        </li>
      ))}
    </ul>
  );
}
