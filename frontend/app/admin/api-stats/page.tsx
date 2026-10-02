'use client';

import { Suspense, useCallback, useEffect, useState, type ReactNode } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { adminApiStatsAPI, type ApiStatsBucket, type ApiStatsReport } from '@/lib/admin-api';
import { ApiUsageCharts } from './api-usage-charts';

const TZ = 'Asia/Ho_Chi_Minh';

function ictYmd(d = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit' }).format(d);
}

function ictShiftDays(days: number): string {
  const [y, m, d] = ictYmd().split('-').map((part) => Number.parseInt(part, 10));
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10);
}

function formatNum(n: number): string {
  return n.toLocaleString('vi-VN');
}

function formatVnd(n: number): string {
  return `${Math.round(n).toLocaleString('vi-VN')}₫`;
}

function formatVndOrDash(n: number | null | undefined): string {
  return n == null ? '—' : formatVnd(n);
}

function formatShare(part: number, whole: number): string {
  if (!(whole > 0)) return '—';
  const pct = (part / whole) * 100;
  if (pct > 0 && pct < 0.1) return '<0,1%';
  return `${pct.toLocaleString('vi-VN', { maximumFractionDigits: 1, minimumFractionDigits: 1 })}%`;
}

function formatRange(from: string, to: string): string {
  const vi = (ymd: string) => {
    const [y, m, d] = ymd.split('-');
    return y && m && d ? `${d}/${m}/${y}` : ymd;
  };
  return from === to ? vi(from) : `${vi(from)} – ${vi(to)}`;
}

function perCall(cost: number, calls: number): string {
  return `~${formatVnd(calls ? Math.round(cost / calls) : 0)}/lượt`;
}

export default function AdminApiStatsPage() {
  return (
    <Suspense fallback={<p className="p-6 text-sm text-slate-500">Đang tải thống kê API…</p>}>
      <AdminApiStatsBody />
    </Suspense>
  );
}

function AdminApiStatsBody() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const fromDate = searchParams.get('from')?.trim() || ictShiftDays(-30);
  const toDate = searchParams.get('to')?.trim() || ictYmd();
  const [draftFrom, setDraftFrom] = useState(fromDate);
  const [draftTo, setDraftTo] = useState(toDate);
  const [report, setReport] = useState<ApiStatsReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  useEffect(() => {
    setDraftFrom(fromDate);
    setDraftTo(toDate);
  }, [fromDate, toDate]);

  const applyRange = useCallback(
    (from: string, to: string) => {
      const params = new URLSearchParams();
      params.set('from', from);
      params.set('to', to || from);
      router.push(`/admin/api-stats?${params.toString()}`);
    },
    [router],
  );

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    adminApiStatsAPI
      .getReport(fromDate, toDate)
      .then((data) => {
        if (!cancelled) setReport(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Không tải được thống kê API');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [fromDate, toDate]);

  useEffect(() => load(), [load]);

  useEffect(() => {
    if (selectedId == null) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setSelectedId(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selectedId]);

  const presets = [
    { label: 'Hôm nay', from: ictYmd(), to: ictYmd() },
    { label: '7 ngày', from: ictShiftDays(-6), to: ictYmd() },
    { label: '30 ngày', from: ictShiftDays(-29), to: ictYmd() },
    { label: '90 ngày', from: ictShiftDays(-89), to: ictYmd() },
    { label: 'Tháng này', from: `${ictYmd().slice(0, 8)}01`, to: ictYmd() },
    { label: 'Năm nay', from: `${ictYmd().slice(0, 4)}-01-01`, to: ictYmd() },
  ];

  const totals = report?.totals;
  const selected = report?.recentLogs.find((row) => row.id === selectedId) ?? null;
  const whole = totals?.totalCostVnd ?? 0;

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-3xl font-bold tracking-tight text-slate-900">Thống kê chi phí API các model AI</h2>
        <p className="mt-1 text-slate-500">
          Toàn bộ bản ghi api_usage_log trong khoảng ngày (giờ Việt Nam)
          {report ? ` • Tỷ giá 1 USD = ${report.usdToVnd.toLocaleString('vi-VN')}₫` : ''}
        </p>
        <p className="mt-0.5 text-xs text-slate-500">
          Giá theo cùng bảng nanoai / Google 2025: pro-image $2/$120 input/output ảnh, flash $0.5/$3, 2.5-flash $0.3/$2.5,
          2.0-flash $0.1/$0.4, DeepSeek V4 $0.28/$0.42. GPT Image $5/$40 mỗi triệu token. Model lạ tính tạm theo Gemini 3 Flash.
        </p>
      </div>

      <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="px-4 py-3 text-sm font-medium text-slate-800">Lọc theo ngày (giờ Việt Nam)</div>
        <form
          className="flex flex-wrap items-end gap-3 px-4 pb-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (draftFrom) applyRange(draftFrom, draftTo || draftFrom);
          }}
        >
          <label className="space-y-1.5 text-xs text-slate-600">
            Từ ngày
            <input
              type="date"
              value={draftFrom}
              onChange={(event) => setDraftFrom(event.target.value)}
              className="block h-8 w-[150px] rounded-md border border-slate-300 px-2 text-sm"
            />
          </label>
          <label className="space-y-1.5 text-xs text-slate-600">
            Đến ngày
            <input
              type="date"
              value={draftTo}
              onChange={(event) => setDraftTo(event.target.value)}
              className="block h-8 w-[150px] rounded-md border border-slate-300 px-2 text-sm"
            />
          </label>
          <button type="submit" className="h-8 rounded-md bg-slate-900 px-3 text-sm font-medium text-white">
            Xem
          </button>
        </form>
        <div className="flex flex-wrap gap-2 px-4 pb-4">
          {presets.map((preset) => {
            const active = preset.from === fromDate && preset.to === toDate;
            return (
              <button
                key={preset.label}
                type="button"
                onClick={() => applyRange(preset.from, preset.to)}
                className={`h-7 rounded-md border px-2 text-xs ${active ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-300 bg-white text-slate-700'}`}
              >
                {preset.label}
              </button>
            );
          })}
        </div>
      </section>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}{' '}
          <button type="button" onClick={() => load()} className="font-medium underline">
            Thử lại
          </button>
        </div>
      )}

      {loading && !report ? <p className="text-sm text-slate-500">Đang tổng hợp chi phí…</p> : null}

      {report && totals && (
        <>
          <section className="rounded-xl border border-emerald-200 bg-emerald-50/40 p-6 shadow-sm">
            <h3 className="text-lg font-semibold text-slate-900">Thu chi & lợi nhuận</h3>
            <p className="text-sm text-slate-500">{formatRange(report.from, report.to)}</p>
            <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <div>
                <p className="text-sm font-medium text-slate-500">Thu (doanh thu đã cọc)</p>
                <p className="text-2xl font-bold text-emerald-700">{formatVnd(report.revenueVnd)}</p>
                <p className="text-xs text-slate-500">{formatNum(report.orderCount)} đơn đã cọc, cùng kỳ bảng chi phí quảng cáo</p>
              </div>
              <div>
                <p className="text-sm font-medium text-slate-500">Chi phí vốn</p>
                <p className="text-2xl font-bold text-slate-800">{formatVndOrDash(report.goodsCostVnd)}</p>
                <p className="text-xs text-slate-500">{report.costNote || 'Giá nhập hàng'}</p>
              </div>
              <div>
                <p className="text-sm font-medium text-slate-500">Chi phí ship</p>
                <p className="text-2xl font-bold text-slate-800">{formatVndOrDash(report.shipCostVnd)}</p>
                <p className="text-xs text-slate-500">Ship Trung Quốc, cửa khẩu và Hà Nội</p>
              </div>
              <div>
                <p className="text-sm font-medium text-slate-500">Chi phí quảng cáo</p>
                <p className="text-2xl font-bold text-orange-700">{formatVndOrDash(report.adSpendVnd)}</p>
                <p className="text-xs text-slate-500">{report.adSpendNote || 'Google + Facebook'}</p>
              </div>
              <div>
                <p className="text-sm font-medium text-slate-500">Chi (API)</p>
                <p className="text-2xl font-bold text-amber-700">{formatVnd(report.apiCostVnd)}</p>
                <p className="text-xs text-slate-500">
                  ~{report.apiCostUsd.toFixed(4)} USD • {formatNum(report.callCount)} lượt gọi
                </p>
              </div>
              <div>
                <p className="text-sm font-medium text-slate-500">Lợi nhuận</p>
                <p className={`text-2xl font-bold ${report.profitVnd == null ? 'text-slate-400' : report.profitVnd >= 0 ? 'text-emerald-700' : 'text-red-600'}`}>
                  {formatVndOrDash(report.profitVnd)}
                </p>
                <p className="text-xs text-slate-500">Doanh thu đã cọc − vốn − ship − quảng cáo − chi API</p>
              </div>
            </div>
          </section>

          <div className="grid gap-4 md:grid-cols-4">
            <Kpi title="Tổng lượt gọi" value={formatNum(totals.calls)} hint={perCall(totals.totalCostVnd, totals.calls)} />
            <Kpi title="Token input" value={formatNum(totals.promptTokens)} hint={formatVnd(totals.inputCostVnd)} hintClass="text-amber-700" />
            <Kpi title="Token output" value={formatNum(totals.outputTokens)} hint={formatVnd(totals.outputCostVnd)} hintClass="text-amber-700" />
            <Kpi title="Tổng tokens" value={formatNum(totals.totalTokens)} hint={formatVnd(totals.totalCostVnd)} hintClass="text-amber-700" />
          </div>

          <ApiUsageCharts charts={report.charts} hasAnyLog={report.callCount > 0} />

          <StatsTable
            title="Theo model"
            subtitle="Số lượt gọi và token theo từng model"
            rows={report.byModel}
            whole={whole}
            nameCell={(row) => (
              <span>
                <span className="rounded-md border border-slate-300 px-2 py-0.5 font-mono text-xs">{row.key}</span>
                {row.listedPrice === false ? <span className="ml-2 text-[10px] text-amber-700">giá tạm</span> : null}
              </span>
            )}
          />

          <StatsTable
            title="Theo chức năng"
            subtitle="Số lượt gọi và token theo từng tính năng"
            rows={report.byFeature}
            whole={whole}
            nameCell={(row) => (
              <span>
                <span className="font-medium text-slate-900">{row.label}</span>
                <br />
                <span className="text-xs text-slate-500">{row.key}</span>
              </span>
            )}
          />

          <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
            <header className="px-6 pt-6">
              <h3 className="text-lg font-semibold text-slate-900">Theo độ phân giải ảnh</h3>
              <p className="text-sm text-slate-500">Số lượt gọi trả ảnh 1K, 2K, 4K hoặc không trả ảnh (chỉ text)</p>
            </header>
            <div className="overflow-x-auto px-2 pb-4">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="text-left text-slate-500">
                    <th className="px-4 py-3 font-medium">Ảnh trả về</th>
                    <th className="px-4 py-3 text-right font-medium">Lượt gọi</th>
                    <th className="px-4 py-3 text-right font-medium">Input</th>
                    <th className="px-4 py-3 text-right font-medium">Output</th>
                    <th className="px-4 py-3 text-right font-medium">Tổng</th>
                    <th className="px-4 py-3 text-right font-medium">Chi phí (₫)</th>
                  </tr>
                </thead>
                <tbody>
                  {report.byImageSize.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="px-4 py-8 text-center text-slate-500">
                        Chưa có dữ liệu thống kê.
                      </td>
                    </tr>
                  ) : (
                    report.byImageSize.map((row) => (
                      <tr key={row.key} className="border-t border-slate-100">
                        <td className="px-4 py-3">
                          <span
                            className={`rounded-md border px-2 py-0.5 text-xs ${
                              row.key === '4K'
                                ? 'border-amber-300 text-amber-600'
                                : row.key === 'no-image'
                                  ? 'border-slate-200 bg-slate-100 text-slate-600'
                                  : 'border-sky-300 text-sky-600'
                            }`}
                          >
                            {row.label}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right">{formatNum(row.calls)}</td>
                        <TokenCell tokens={row.promptTokens} cost={row.inputCostVnd} />
                        <TokenCell tokens={row.outputTokens} cost={row.outputCostVnd} />
                        <td className="px-4 py-3 text-right font-medium">{formatNum(row.totalTokens)}</td>
                        <td className="px-4 py-3 text-right">
                          <span className="font-medium text-amber-700">{formatVnd(row.costVnd)}</span>
                          <br />
                          <span className="text-xs text-slate-500">{perCall(row.costVnd, row.calls)}</span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
            <header className="px-6 pt-6">
              <h3 className="text-lg font-semibold text-slate-900">Chi tiết gần đây</h3>
              <p className="text-sm text-slate-500">100 bản ghi mới nhất • Bấm vào dòng để xem chi tiết lượt gọi</p>
            </header>
            <div className="overflow-x-auto px-2 pb-4">
              {report.recentLogs.length === 0 ? (
                <p className="py-8 text-center text-slate-500">Chưa có dữ liệu thống kê. Các lượt gọi AI sau khi bật ghi log sẽ hiện ở đây.</p>
              ) : (
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="text-left text-slate-500">
                      <th className="px-4 py-3 font-medium">Thời gian</th>
                      <th className="px-4 py-3 font-medium">Model</th>
                      <th className="px-4 py-3 font-medium">Chức năng</th>
                      <th className="px-4 py-3 font-medium">Ảnh</th>
                      <th className="px-4 py-3 text-right font-medium">Input</th>
                      <th className="px-4 py-3 text-right font-medium">Output</th>
                      <th className="px-4 py-3 text-right font-medium">Tổng</th>
                      <th className="px-4 py-3 text-right font-medium">Chi phí (₫)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.recentLogs.map((log) => (
                      <tr
                        key={log.id}
                        className="cursor-pointer border-t border-slate-100 hover:bg-slate-50"
                        onClick={() => setSelectedId(log.id)}
                      >
                        <td className="px-4 py-3 text-slate-500">
                          {log.createdAt ? new Date(log.createdAt).toLocaleString('vi-VN') : '—'}
                        </td>
                        <td className="px-4 py-3">
                          <span className="rounded-md border border-slate-300 px-2 py-0.5 font-mono text-xs">{log.model}</span>
                        </td>
                        <td className="px-4 py-3">{log.featureLabel}</td>
                        <td className="px-4 py-3">
                          {log.imageSize ? (
                            <span className={`rounded-md border px-2 py-0.5 text-xs ${log.imageSize === '4K' ? 'border-amber-300 text-amber-600' : 'border-sky-300 text-sky-600'}`}>
                              {log.imageSize}
                            </span>
                          ) : (
                            <span className="text-xs text-slate-400">—</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right">{formatNum(log.promptTokens)}</td>
                        <td className="px-4 py-3 text-right">{formatNum(log.outputTokens)}</td>
                        <td className="px-4 py-3 text-right font-medium">{formatNum(log.totalTokens)}</td>
                        <td className="px-4 py-3 text-right font-medium text-amber-700">{formatVnd(log.costVnd)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </section>
        </>
      )}

      {selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setSelectedId(null)}>
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="api-log-detail-title"
            className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl"
            onClick={(event) => event.stopPropagation()}
          >
            <h3 id="api-log-detail-title" className="text-lg font-semibold text-slate-900">
              Chi tiết lượt gọi API
            </h3>
            <dl className="mt-4 space-y-3 text-sm">
              <div>
                <dt className="text-xs text-slate-500">Thời gian</dt>
                <dd className="font-medium">{selected.createdAt ? new Date(selected.createdAt).toLocaleString('vi-VN') : '—'}</dd>
              </div>
              <div>
                <dt className="text-xs text-slate-500">Model</dt>
                <dd className="font-mono text-xs">{selected.model}</dd>
              </div>
              <div>
                <dt className="text-xs text-slate-500">Chức năng</dt>
                <dd>
                  {selected.featureLabel}
                  <span className="ml-2 text-xs text-slate-500">{selected.feature}</span>
                </dd>
              </div>
              <div>
                <dt className="text-xs text-slate-500">Ảnh trả về</dt>
                <dd>{selected.imageSize || 'Không trả ảnh'}</dd>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <dt className="text-xs text-slate-500">Input</dt>
                  <dd>{formatNum(selected.promptTokens)}</dd>
                  <dd className="text-xs text-amber-700">{formatVnd(selected.inputCostVnd)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-500">Output</dt>
                  <dd>{formatNum(selected.outputTokens)}</dd>
                  <dd className="text-xs text-amber-700">{formatVnd(selected.outputCostVnd)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-500">Tổng</dt>
                  <dd className="font-medium">{formatNum(selected.totalTokens)}</dd>
                  <dd className="text-xs text-amber-700">{formatVnd(selected.costVnd)}</dd>
                </div>
              </div>
            </dl>
            <button type="button" className="mt-5 h-9 rounded-md bg-slate-900 px-3 text-sm text-white" onClick={() => setSelectedId(null)}>
              Đóng
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Kpi({ title, value, hint, hintClass = 'text-slate-500' }: { title: string; value: string; hint: string; hintClass?: string }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-sm font-medium text-slate-500">{title}</p>
      <p className="mt-2 text-2xl font-bold text-slate-900">{value}</p>
      <p className={`mt-1 text-xs font-medium ${hintClass}`}>{hint}</p>
    </section>
  );
}

function TokenCell({ tokens, cost }: { tokens: number; cost: number }) {
  return (
    <td className="px-4 py-3 text-right">
      <span>{formatNum(tokens)}</span>
      <br />
      <span className="text-xs text-amber-700">{formatVnd(cost)}</span>
    </td>
  );
}

function StatsTable({
  title,
  subtitle,
  rows,
  whole,
  nameCell,
}: {
  title: string;
  subtitle: string;
  rows: ApiStatsBucket[];
  whole: number;
  nameCell: (row: ApiStatsBucket) => ReactNode;
}) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <header className="px-6 pt-6">
        <h3 className="text-lg font-semibold text-slate-900">{title}</h3>
        <p className="text-sm text-slate-500">{subtitle}</p>
      </header>
      <div className="overflow-x-auto px-2 pb-4">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500">
              <th className="px-4 py-3 font-medium">{title === 'Theo model' ? 'Model' : 'Chức năng'}</th>
              <th className="px-4 py-3 text-right font-medium">Lượt gọi</th>
              <th className="px-4 py-3 text-right font-medium">1K</th>
              <th className="px-4 py-3 text-right font-medium">2K</th>
              <th className="px-4 py-3 text-right font-medium">4K</th>
              <th className="px-4 py-3 text-right font-medium">Input</th>
              <th className="px-4 py-3 text-right font-medium">Output</th>
              <th className="px-4 py-3 text-right font-medium">Tổng</th>
              <th className="px-4 py-3 text-right font-medium">Tỷ lệ</th>
              <th className="px-4 py-3 text-right font-medium">Chi phí (₫)</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={10} className="px-4 py-8 text-center text-slate-500">
                  Chưa có dữ liệu thống kê.
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.key} className="border-t border-slate-100">
                  <td className="px-4 py-3">{nameCell(row)}</td>
                  <td className="px-4 py-3 text-right">{formatNum(row.calls)}</td>
                  <td className="px-4 py-3 text-right">{formatNum(row.calls1K || 0)}</td>
                  <td className="px-4 py-3 text-right text-sky-600">{formatNum(row.calls2K || 0)}</td>
                  <td className="px-4 py-3 text-right text-amber-600">{formatNum(row.calls4K || 0)}</td>
                  <TokenCell tokens={row.promptTokens} cost={row.inputCostVnd} />
                  <TokenCell tokens={row.outputTokens} cost={row.outputCostVnd} />
                  <td className="px-4 py-3 text-right font-medium">{formatNum(row.totalTokens)}</td>
                  <td className="px-4 py-3 text-right text-xs">{formatShare(row.costVnd, whole)}</td>
                  <td className="px-4 py-3 text-right">
                    <span className="font-medium text-amber-700">{formatVnd(row.costVnd)}</span>
                    <br />
                    <span className="text-xs text-slate-500">{perCall(row.costVnd, row.calls)}</span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
