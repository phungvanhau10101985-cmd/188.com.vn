'use client';

import EditableText from './EditableText';
import type { HighlightsSectionData } from './types';

interface HighlightsSectionProps {
  data: HighlightsSectionData;
  editable?: boolean;
  isBusy?: boolean;
  onSaveItem?: (index: number, field: 'title' | 'desc', value: string) => void | Promise<void>;
  onRegenerate?: (instruction: string) => void | Promise<void>;
}

const ICONS = ['✨', '🎯', '💪', '🛡️', '⭐', '🔥'];

export default function HighlightsSection({
  data,
  editable = false,
  isBusy = false,
  onSaveItem,
  onRegenerate,
}: HighlightsSectionProps) {
  const items = data.items || [];

  return (
    <section className="relative py-8 md:py-12">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-orange-600">Lý do nên chọn</p>
          <h2 className="mt-1 text-2xl font-extrabold tracking-tight text-gray-950 md:text-3xl">Điểm nổi bật &amp; đáng mua</h2>
        </div>
        {editable && onRegenerate && (
          <button
            type="button"
            onClick={() => onRegenerate('')}
            disabled={isBusy}
            className="rounded-full bg-orange-600 px-3 py-1 text-xs font-medium text-white shadow hover:bg-orange-700 disabled:opacity-50"
          >
            {isBusy ? 'Đang tạo…' : '✨ AI viết lại cả mục'}
          </button>
        )}
      </div>

      {items.length === 0 ? (
        <p className="italic text-gray-400">Chưa có nội dung — AI sẽ tạo điểm mạnh sản phẩm tại đây.</p>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item, idx) => (
            <div key={idx} className="group rounded-2xl border border-gray-100 bg-white p-5 shadow-sm transition duration-200 hover:-translate-y-1 hover:border-orange-100 hover:shadow-lg hover:shadow-orange-900/5">
              <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl bg-orange-50 text-2xl transition group-hover:scale-110">{ICONS[idx % ICONS.length]}</div>
              <EditableText
                as="h3"
                value={item.title}
                className="font-bold text-gray-950"
                editable={editable}
                isBusy={isBusy}
                onSave={onSaveItem ? (v) => onSaveItem(idx, 'title', v) : undefined}
              />
              <EditableText
                as="p"
                value={item.desc}
                className="mt-2 text-sm leading-relaxed text-gray-600"
                multiline
                editable={editable}
                isBusy={isBusy}
                onSave={onSaveItem ? (v) => onSaveItem(idx, 'desc', v) : undefined}
              />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
