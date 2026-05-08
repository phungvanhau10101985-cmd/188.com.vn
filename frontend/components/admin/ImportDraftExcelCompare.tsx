'use client';

import { useMemo, useState } from 'react';
import {
  DRAFT_IMPORT_EXCEL_COLUMNS,
  draftExcelColumnLetter,
  productDataToDraftExcelRow,
  shortenPreview,
} from '@/lib/excel-import-draft-preview';
import { getBackendOriginUrl } from '@/lib/api-base';

type Props = {
  productData: Record<string, unknown> | undefined;
};

export function ImportDraftExcelCompare({ productData }: Props) {
  const [open, setOpen] = useState(true);
  const row = useMemo(() => productDataToDraftExcelRow(productData), [productData]);
  const sampleFileUrl = `${getBackendOriginUrl()}/static/templates/sample_import_template.xlsx`;

  return (
    <div className="mt-4 rounded-lg border border-gray-200 bg-gray-50/80">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left text-sm font-medium text-gray-800 hover:bg-gray-100/80 rounded-t-lg"
        aria-expanded={open}
      >
        <span>
          Đối chiếu 37 cột file mẫu import (Excel A–AK)
          <span className="ml-2 font-normal text-xs text-gray-500">
            Cùng thứ tự với Export Excel draft và sample_import_template.xlsx
          </span>
        </span>
        <span className="text-gray-500 shrink-0" aria-hidden>
          {open ? '▼' : '▶'}
        </span>
      </button>
      {open ? (
        <div className="border-t border-gray-200 px-3 pb-3 pt-1">
          <p className="mb-2 text-xs text-gray-600 leading-snug">
            Cột &quot;Giá trị draft&quot; là dữ liệu map sang đúng key Excel (hàng 1 file mẫu). Cột &quot;Ví dụ file
            mẫu&quot; là nội dung minh hoạ —{' '}
            <a
              href={sampleFileUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="font-medium text-blue-700 hover:underline"
            >
              Tải sample_import_template.xlsx
            </a>
            .
          </p>
          <div className="max-h-[min(70vh,520px)] overflow-auto rounded border border-gray-200 bg-white">
            <table className="min-w-[720px] w-full text-left text-xs">
              <thead className="sticky top-0 z-10 bg-gray-100 text-[11px] uppercase tracking-wide text-gray-600">
                <tr>
                  <th className="px-2 py-2 border-b border-gray-200 w-10">#</th>
                  <th className="px-2 py-2 border-b border-gray-200 w-14">Cột</th>
                  <th className="px-2 py-2 border-b border-gray-200 min-w-[140px]">Tên cột (VI)</th>
                  <th className="px-2 py-2 border-b border-gray-200 min-w-[100px]">Key (EN)</th>
                  <th className="px-2 py-2 border-b border-gray-200 min-w-[220px]">Giá trị draft</th>
                  <th className="px-2 py-2 border-b border-gray-200 min-w-[180px]">Ví dụ file mẫu</th>
                </tr>
              </thead>
              <tbody className="text-gray-800">
                {DRAFT_IMPORT_EXCEL_COLUMNS.map((col, idx) => {
                  const val = row[col.key as keyof typeof row] ?? '';
                  const hasVal = String(val).trim().length > 0;
                  return (
                    <tr
                      key={col.key}
                      className={`border-b border-gray-100 ${hasVal ? '' : 'bg-amber-50/40'}`}
                    >
                      <td className="px-2 py-1.5 text-gray-500 tabular-nums">{idx + 1}</td>
                      <td className="px-2 py-1.5 font-mono text-[11px] text-gray-600">
                        {draftExcelColumnLetter(idx)}
                      </td>
                      <td className="px-2 py-1.5 text-gray-700">{col.labelVi}</td>
                      <td className="px-2 py-1.5 font-mono text-[11px] text-gray-600 break-all">
                        {col.key}
                      </td>
                      <td className="px-2 py-1.5 align-top">
                        <span
                          className="block font-mono text-[11px] break-all whitespace-pre-wrap max-h-24 overflow-y-auto"
                          title={val.length > 200 ? val : undefined}
                        >
                          {val ? shortenPreview(val, 400) : '—'}
                        </span>
                      </td>
                      <td className="px-2 py-1.5 align-top text-gray-500" title={col.sampleHint}>
                        {shortenPreview(col.sampleHint, 120)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-[11px] text-gray-500">
            Ô vàng nhạt: giá trị draft đang trống (có thể bổ sung trước khi Export / Đăng). Sửa nhanh ở khối phía
            trên hoặc Lưu nháp rồi chỉnh thêm khi cần.
          </p>
        </div>
      ) : null}
    </div>
  );
}
