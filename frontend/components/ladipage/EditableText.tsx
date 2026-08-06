'use client';

import { useEffect, useRef, useState } from 'react';

interface EditableTextProps {
  value: string;
  placeholder?: string;
  className?: string;
  as?: 'div' | 'h1' | 'h2' | 'h3' | 'p' | 'span';
  multiline?: boolean;
  /** Khi false: chỉ hiển thị, không cho sửa (dùng cho trang public). */
  editable?: boolean;
  isBusy?: boolean;
  onSave?: (next: string) => void | Promise<void>;
  onRegenerate?: (instruction: string) => void | Promise<void>;
  regenerateLabel?: string;
}

/**
 * Text hiển thị bình thường ở chế độ public; ở chế độ editable (admin) cho phép:
 * - Bấm vào để sửa trực tiếp tại chỗ (lưu khi rời khỏi ô).
 * - Bấm nút "✨ AI" để mở popover nhập yêu cầu và viết lại bằng DeepSeek.
 */
export default function EditableText({
  value,
  placeholder = 'Chưa có nội dung — bấm Tạo nội dung AI',
  className = '',
  as = 'div',
  multiline = false,
  editable = false,
  isBusy = false,
  onSave,
  onRegenerate,
  regenerateLabel = 'Yêu cầu thêm cho AI (có thể để trống)',
}: EditableTextProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [showAiPopover, setShowAiPopover] = useState(false);
  const [instruction, setInstruction] = useState('');
  const inputRef = useRef<HTMLTextAreaElement & HTMLInputElement>(null);

  useEffect(() => {
    setDraft(value);
  }, [value]);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  if (!editable) {
    const Tag = as;
    return (
      <Tag className={className}>
        {value || (placeholder ? <span className="italic opacity-50">{placeholder}</span> : null)}
      </Tag>
    );
  }

  const commit = async () => {
    setEditing(false);
    const next = draft.trim();
    if (next !== value && onSave) await onSave(next);
  };

  const cancel = () => {
    setDraft(value);
    setEditing(false);
  };

  return (
    <div className={`group/editable relative ${isBusy ? 'pointer-events-none opacity-60' : ''}`}>
      {editing ? (
        multiline ? (
          <textarea
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === 'Escape') cancel();
            }}
            className={`w-full rounded-md border-2 border-orange-400 bg-white p-2 outline-none ${className}`}
            rows={4}
          />
        ) : (
          <input
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commit();
              if (e.key === 'Escape') cancel();
            }}
            className={`w-full rounded-md border-2 border-orange-400 bg-white p-1.5 outline-none ${className}`}
          />
        )
      ) : (
        <div
          className={`cursor-text rounded-md ring-1 ring-transparent transition hover:bg-orange-50/40 hover:ring-orange-300 ${className}`}
          onClick={() => onSave && setEditing(true)}
          title={onSave ? 'Bấm để sửa nội dung' : undefined}
        >
          {value || <span className="italic opacity-50">{placeholder}</span>}
        </div>
      )}

      {onRegenerate && !editing && (
        <div className="absolute -top-3 right-0 hidden gap-1 group-hover/editable:flex">
          <button
            type="button"
            onClick={() => setShowAiPopover((v) => !v)}
            disabled={isBusy}
            className="rounded-full bg-orange-600 px-2 py-0.5 text-[11px] font-medium text-white shadow hover:bg-orange-700 disabled:opacity-50"
          >
            {isBusy ? 'Đang tạo…' : '✨ AI viết lại'}
          </button>
        </div>
      )}

      {showAiPopover && onRegenerate && (
        <div className="absolute right-0 top-4 z-20 w-72 rounded-lg border border-gray-200 bg-white p-3 shadow-xl">
          <label className="mb-1 block text-xs font-medium text-gray-600">{regenerateLabel}</label>
          <textarea
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            placeholder="VD: nhấn mạnh khuyến mãi, giọng vui tươi hơn…"
            className="mb-2 w-full rounded-md border border-gray-300 p-2 text-xs outline-none focus:border-orange-400"
            rows={3}
          />
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setShowAiPopover(false)}
              className="rounded-md px-2 py-1 text-xs text-gray-500 hover:bg-gray-100"
            >
              Hủy
            </button>
            <button
              type="button"
              onClick={async () => {
                setShowAiPopover(false);
                const val = instruction.trim();
                setInstruction('');
                await onRegenerate(val);
              }}
              className="rounded-md bg-orange-600 px-3 py-1 text-xs font-medium text-white hover:bg-orange-700"
            >
              Tạo lại
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
