'use client';

import { useState } from 'react';
import EditableText from './EditableText';
import type { FaqSectionData } from './types';

interface FaqSectionProps {
  data: FaqSectionData;
  editable?: boolean;
  isBusy?: boolean;
  onSaveItem?: (index: number, field: 'q' | 'a', value: string) => void | Promise<void>;
  onRegenerate?: (instruction: string) => void | Promise<void>;
}

export default function FaqSection({ data, editable = false, isBusy = false, onSaveItem, onRegenerate }: FaqSectionProps) {
  const items = data.items || [];
  const [openIndex, setOpenIndex] = useState<number | null>(0);

  return (
    <section className="py-8 md:py-12">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-orange-600">Giải đáp nhanh</p>
          <h2 className="mt-1 text-2xl font-extrabold tracking-tight text-gray-950 md:text-3xl">Câu hỏi thường gặp</h2>
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
        <p className="italic text-gray-400">Chưa có câu hỏi thường gặp.</p>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-gray-100 bg-white shadow-sm">
          {items.map((item, idx) => (
            <div key={idx} className="border-b border-gray-100 p-5 last:border-b-0">
              <button
                type="button"
                onClick={() => setOpenIndex(openIndex === idx ? null : idx)}
                className="flex w-full items-center justify-between text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-orange-600"
              >
                <EditableText
                  as="span"
                  value={item.q}
                  className="pr-3 font-bold text-gray-900"
                  editable={editable}
                  isBusy={isBusy}
                  onSave={onSaveItem ? (v) => onSaveItem(idx, 'q', v) : undefined}
                />
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-orange-50 text-lg font-medium text-orange-600">{openIndex === idx ? '−' : '+'}</span>
              </button>
              {openIndex === idx && (
                <EditableText
                  as="p"
                  value={item.a}
                  className="mt-3 max-w-3xl text-sm leading-relaxed text-gray-600"
                  multiline
                  editable={editable}
                  isBusy={isBusy}
                  onSave={onSaveItem ? (v) => onSaveItem(idx, 'a', v) : undefined}
                />
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
