'use client';

type ActionCooldownToastProps = {
  visible: boolean;
  remainingSec: number;
  /** Mặc định: Thao tác quá nhanh */
  title?: string;
  /** Mô tả ngắn — vd. "Lưu lịch backup", "Chạy backup ngay" */
  actionLabel?: string;
};

export function ActionCooldownToast({
  visible,
  remainingSec,
  title = 'Thao tác quá nhanh',
  actionLabel,
}: ActionCooldownToastProps) {
  if (!visible || remainingSec <= 0) return null;

  const actionHint = actionLabel ? ` (${actionLabel})` : '';

  return (
    <div
      className="mb-4 flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950"
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      <span className="text-2xl leading-none select-none animate-pulse" aria-hidden>
        ⏳
      </span>
      <div className="min-w-0">
        <p className="font-semibold">{title}</p>
        <p className="mt-0.5 text-amber-900">
          Vui lòng chờ{' '}
          <span className="inline-flex min-w-[2ch] font-bold tabular-nums text-amber-950">
            {remainingSec}s
          </span>{' '}
          rồi thử lại{actionHint}.
        </p>
      </div>
    </div>
  );
}
