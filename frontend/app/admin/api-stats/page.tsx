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

function ictMonthBounds(offset: number): { from: string; to: string } {
  const [y, m] = ictYmd().split('-').map((part) => Number.parseInt(part, 10));
  const from = new Date(Date.UTC(y, m - 1 + offset, 1)).toISOString().slice(0, 10);
  const to = new Date(Date.UTC(y, m + offset, 0)).toISOString().slice(0, 10);
  return { from, to };
}

function formatNum(n: number): string {
  return n.toLocaleString('vi-VN');
}

function formatVnd(n: number): string {
  return new Intl.NumberFormat('vi-VN', {
    style: 'currency',
    currency: 'VND',
    maximumFractionDigits: 0,
  }).format(Math.round(n));
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
  return from === to ? vi(from) : `${vi(from)} → ${vi(to)}`;
}

function perCall(cost: number, calls: number): string {
  return `~${formatVnd(calls ? Math.round(cost / calls) : 0)} / lượt`;
}

export default function AdminApiStatsPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <AdminApiStatsBody />
    </Suspense>
  );
}

function AdminApiStatsBody() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const fromDate = searchParams.get('from')?.trim() || ictShiftDays(-29);
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

  const prevMonth = ictMonthBounds(-1);
  const presets = [
    { label: 'Hôm nay', from: ictYmd(), to: ictYmd() },
    { label: 'Hôm qua', from: ictShiftDays(-1), to: ictShiftDays(-1) },
    { label: '7 ngày', from: ictShiftDays(-6), to: ictYmd() },
    { label: '30 ngày', from: ictShiftDays(-29), to: ictYmd() },
    { label: '90 ngày', from: ictShiftDays(-89), to: ictYmd() },
    { label: 'Tháng này', from: `${ictYmd().slice(0, 8)}01`, to: ictYmd() },
    { label: 'Tháng trước', from: prevMonth.from, to: prevMonth.to },
    { label: 'Năm nay', from: `${ictYmd().slice(0, 4)}-01-01`, to: ictYmd() },
  ];

  const totals = report?.totals;
  const selected = report?.recentLogs.find((row) => row.id === selectedId) ?? null;
  const whole = totals?.totalCostVnd ?? 0;
  const activePreset = presets.find((preset) => preset.from === fromDate && preset.to === toDate)?.label ?? null;
  const viewingLabel = activePreset ? `${activePreset} · ${formatRange(fromDate, toDate)}` : formatRange(fromDate, toDate);
  const profitNegative = report?.profitVnd != null && report.profitVnd < 0;

  const presetClass = (active: boolean) =>
    active
      ? 'border-[#ea580c] bg-[#ea580c] font-semibold text-white shadow-sm'
      : 'border-slate-200 bg-white text-slate-700 hover:border-orange-200 hover:bg-orange-50 hover:text-[#ea580c]';

  return (
    <div className="mx-auto max-w-6xl p-4 sm:p-6">
      <h1 className="text-xl font-bold text-slate-900">Thống kê chi phí API</h1>
      <p className="mt-1 max-w-3xl text-sm text-slate-600">
        Chọn hôm nay, tuần hoặc tháng. Chi phí model AI và lợi nhuận của kỳ đó hiện ngay bên dưới. Bảng chi tiết và biểu đồ nằm phía dưới.
      </p>

      {error ? (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}{' '}
          <button type="button" className="font-medium underline" onClick={() => load()}>
            Thử lại
          </button>
        </div>
      ) : null}

      <form
        className="mt-4 rounded-2xl border border-slate-200 bg-white p-3 shadow-sm sm:p-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (draftFrom) applyRange(draftFrom, draftTo || draftFrom);
        }}
      >
        <div className="flex flex-wrap gap-2" role="group" aria-label="Chọn nhanh khoảng ngày">
          {presets.map((preset) => {
            const active = preset.from === fromDate && preset.to === toDate;
            return (
              <button
                key={preset.label}
                type="button"
                aria-pressed={active}
                onClick={() => applyRange(preset.from, preset.to)}
                className={`rounded-full border px-3 py-1.5 text-sm transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ea580c] ${presetClass(active)}`}
              >
                {preset.label}
              </button>
            );
          })}
        </div>
        <div className="mt-3 flex flex-wrap items-end gap-3 border-t border-slate-100 pt-3">
          <label className="text-sm text-slate-700">
            Từ
            <input
              type="date"
              value={draftFrom}
              onChange={(event) => setDraftFrom(event.target.value)}
              className="mt-1 block rounded-lg border border-slate-300 px-3 py-2 focus:border-[#ea580c] focus:outline-none focus:ring-2 focus:ring-[#ea580c]/30"
            />
          </label>
          <label className="text-sm text-slate-700">
            Đến
            <input
              type="date"
              value={draftTo}
              onChange={(event) => setDraftTo(event.target.value)}
              className="mt-1 block rounded-lg border border-slate-300 px-3 py-2 focus:border-[#ea580c] focus:outline-none focus:ring-2 focus:ring-[#ea580c]/30"
            />
          </label>
          <button
            type="submit"
            disabled={loading}
            className="rounded-lg bg-[#ea580c] px-4 py-2 text-sm font-semibold text-white hover:bg-[#c2410c] disabled:opacity-60"
          >
            {loading ? 'Đang đọc…' : 'Xem kỳ này'}
          </button>
        </div>
      </form>

      {loading && !report ? <PageSkeleton compact /> : null}

      {report && totals ? (
        <div className={loading ? 'opacity-70' : undefined}>
          <section className="mt-4 overflow-hidden rounded-2xl border border-orange-200 bg-white shadow-sm" aria-label="Tổng quan kỳ đang chọn">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-orange-100 bg-orange-50 px-4 py-3">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-[#ea580c]">Đang xem</p>
                <p className="text-base font-bold text-slate-900">{viewingLabel}</p>
              </div>
              <p className="text-xs text-slate-500">Giờ Việt Nam · 1 USD = {report.usdToVnd.toLocaleString('vi-VN')}₫</p>
            </div>
            <div className="grid gap-px bg-orange-100 sm:grid-cols-2">
              <HeroStat
                label="Chi phí API"
                value={formatVnd(report.apiCostVnd)}
                hint={`~${report.apiCostUsd.toFixed(4)} USD · ${formatNum(report.callCount)} lượt gọi`}
              />
              <HeroStat
                label="Lợi nhuận"
                value={formatVndOrDash(report.profitVnd)}
                hint="Doanh thu đã cọc − vốn − ship − quảng cáo − chi API"
                negative={profitNegative}
                muted={report.profitVnd == null}
              />
            </div>
            <div className="grid grid-cols-2 gap-px border-t border-orange-100 bg-orange-100 lg:grid-cols-4">
              <MiniStat
                label="Doanh thu đã cọc"
                value={formatVnd(report.revenueVnd)}
                hint={`${formatNum(report.orderCount)} đơn đã cọc`}
              />
              <MiniStat label="Giá vốn" value={formatVndOrDash(report.goodsCostVnd)} hint={report.costNote || 'Giá nhập hàng'} />
              <MiniStat label="Chi phí ship" value={formatVndOrDash(report.shipCostVnd)} hint="Trung Quốc, cửa khẩu và Hà Nội" />
              <MiniStat label="Quảng cáo" value={formatVndOrDash(report.adSpendVnd)} hint={report.adSpendNote || 'Google + Facebook'} />
            </div>
            <div className="grid grid-cols-2 gap-px border-t border-orange-100 bg-orange-100 lg:grid-cols-4">
              <MiniStat label="Tổng lượt gọi" value={formatNum(totals.calls)} hint={perCall(totals.totalCostVnd, totals.calls)} />
              <MiniStat label="Token input" value={formatNum(totals.promptTokens)} hint={formatVnd(totals.inputCostVnd)} />
              <MiniStat label="Token output" value={formatNum(totals.outputTokens)} hint={formatVnd(totals.outputCostVnd)} />
              <MiniStat label="Tổng tokens" value={formatNum(totals.totalTokens)} hint={formatVnd(totals.totalCostVnd)} />
            </div>
          </section>

          <div className="mt-4">
            <ApiUsageCharts charts={report.charts} hasAnyLog={report.callCount > 0} />
          </div>

          <div className="mt-4 space-y-4">
            <StatsTable
              title="Theo model"
              subtitle="Số lượt gọi và token theo từng model. Tỷ lệ tính trên tổng chi phí API của kỳ."
              nameHeader="Model"
              rows={report.byModel}
              whole={whole}
              nameCell={(row) => (
                <span className="inline-flex flex-wrap items-center gap-2">
                  <span className="rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 font-mono text-xs text-slate-800">{row.key}</span>
                  {row.listedPrice === false ? (
                    <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-700">Giá tạm</span>
                  ) : null}
                </span>
              )}
            />

            <StatsTable
              title="Theo chức năng"
              subtitle="Số lượt gọi và token theo từng tính năng đang dùng AI."
              nameHeader="Chức năng"
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

            <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
              <header className="border-b border-slate-100 px-4 py-3">
                <h2 className="text-sm font-semibold text-slate-800">Theo độ phân giải ảnh</h2>
                <p className="mt-0.5 text-xs text-slate-500">Lượt gọi trả ảnh 1K, 2K, 4K hoặc chỉ text.</p>
              </header>
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-slate-50 text-left text-slate-500">
                    <tr>
                      <th className="px-4 py-2 font-medium">Ảnh trả về</th>
                      <th className="px-4 py-2 text-right font-medium">Lượt gọi</th>
                      <th className="px-4 py-2 text-right font-medium">Input</th>
                      <th className="px-4 py-2 text-right font-medium">Output</th>
                      <th className="px-4 py-2 text-right font-medium">Tổng</th>
                      <th className="px-4 py-2 text-right font-medium">Chi phí</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.byImageSize.length === 0 ? (
                      <EmptyRow cols={6} />
                    ) : (
                      report.byImageSize.map((row) => (
                        <tr key={row.key} className="border-t border-slate-100 hover:bg-orange-50/40">
                          <td className="px-4 py-2.5">
                            <SizeBadge label={row.label} sizeKey={row.key} />
                          </td>
                          <td className="px-4 py-2.5 text-right tabular-nums">{formatNum(row.calls)}</td>
                          <TokenCell tokens={row.promptTokens} cost={row.inputCostVnd} />
                          <TokenCell tokens={row.outputTokens} cost={row.outputCostVnd} />
                          <td className="px-4 py-2.5 text-right font-medium tabular-nums">{formatNum(row.totalTokens)}</td>
                          <CostCell cost={row.costVnd} calls={row.calls} />
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
              <header className="border-b border-slate-100 px-4 py-3">
                <h2 className="text-sm font-semibold text-slate-800">Chi tiết gần đây</h2>
                <p className="mt-0.5 text-xs text-slate-500">100 bản ghi mới nhất. Bấm một dòng để xem chi tiết lượt gọi.</p>
              </header>
              {report.recentLogs.length === 0 ? (
                <p className="px-4 py-8 text-center text-sm text-slate-500">
                  Chưa có dữ liệu thống kê. Các lượt gọi AI sau khi bật ghi log sẽ hiện ở đây.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead className="bg-slate-50 text-left text-slate-500">
                      <tr>
                        <th className="px-4 py-2 font-medium">Thời gian</th>
                        <th className="px-4 py-2 font-medium">Model</th>
                        <th className="px-4 py-2 font-medium">Chức năng</th>
                        <th className="px-4 py-2 font-medium">Ảnh</th>
                        <th className="px-4 py-2 text-right font-medium">Input</th>
                        <th className="px-4 py-2 text-right font-medium">Output</th>
                        <th className="px-4 py-2 text-right font-medium">Tổng</th>
                        <th className="px-4 py-2 text-right font-medium">Chi phí</th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.recentLogs.map((log) => {
                        const active = selectedId === log.id;
                        return (
                          <tr
                            key={log.id}
                            role="button"
                            tabIndex={0}
                            aria-pressed={active}
                            className={`cursor-pointer border-t border-slate-100 ${active ? 'bg-orange-50' : 'hover:bg-orange-50/60'}`}
                            onClick={() => setSelectedId(log.id)}
                            onKeyDown={(event) => {
                              if (event.key === 'Enter' || event.key === ' ') {
                                event.preventDefault();
                                setSelectedId(log.id);
                              }
                            }}
                          >
                            <td className={`whitespace-nowrap px-4 py-2.5 ${active ? 'font-semibold text-[#ea580c]' : 'text-slate-600'}`}>
                              {log.createdAt ? new Date(log.createdAt).toLocaleString('vi-VN') : '—'}
                            </td>
                            <td className="px-4 py-2.5">
                              <span className="rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 font-mono text-xs text-slate-800">
                                {log.model}
                              </span>
                            </td>
                            <td className="px-4 py-2.5 text-slate-800">{log.featureLabel}</td>
                            <td className="px-4 py-2.5">
                              {log.imageSize ? <SizeBadge label={log.imageSize} sizeKey={log.imageSize} /> : <span className="text-xs text-slate-400">—</span>}
                            </td>
                            <td className="px-4 py-2.5 text-right tabular-nums">{formatNum(log.promptTokens)}</td>
                            <td className="px-4 py-2.5 text-right tabular-nums">{formatNum(log.outputTokens)}</td>
                            <td className="px-4 py-2.5 text-right font-medium tabular-nums">{formatNum(log.totalTokens)}</td>
                            <td className={`px-4 py-2.5 text-right font-semibold tabular-nums ${active ? 'text-[#ea580c]' : 'text-slate-900'}`}>
                              {formatVnd(log.costVnd)}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <details className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600 shadow-sm">
              <summary className="cursor-pointer font-medium text-slate-800">Cách tính giá model</summary>
              <p className="mt-2 text-xs leading-relaxed text-slate-500">
                Giá theo cùng bảng nanoai / Google 2025: pro-image $2/$120 input/output ảnh, flash $0.5/$3, 2.5-flash $0.3/$2.5,
                2.0-flash $0.1/$0.4, DeepSeek V4 $0.28/$0.42. GPT Image $5/$40 mỗi triệu token. Model lạ tính tạm theo Gemini 3 Flash.
              </p>
            </details>
          </div>
        </div>
      ) : null}

      {selected ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" onClick={() => setSelectedId(null)}>
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="api-log-detail-title"
            className="w-full max-w-md overflow-hidden rounded-2xl border border-orange-200 bg-white shadow-xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="border-b border-orange-100 bg-orange-50 px-5 py-3">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-[#ea580c]">Lượt gọi</p>
              <h3 id="api-log-detail-title" className="text-base font-bold text-slate-900">
                Chi tiết API
              </h3>
            </div>
            <dl className="space-y-3 px-5 py-4 text-sm">
              <div>
                <dt className="text-xs text-slate-500">Thời gian</dt>
                <dd className="font-medium text-slate-900">{selected.createdAt ? new Date(selected.createdAt).toLocaleString('vi-VN') : '—'}</dd>
              </div>
              <div>
                <dt className="text-xs text-slate-500">Model</dt>
                <dd className="mt-1 font-mono text-xs text-slate-800">{selected.model}</dd>
              </div>
              <div>
                <dt className="text-xs text-slate-500">Chức năng</dt>
                <dd className="text-slate-900">
                  {selected.featureLabel}
                  <span className="ml-2 text-xs text-slate-500">{selected.feature}</span>
                </dd>
              </div>
              <div>
                <dt className="text-xs text-slate-500">Ảnh trả về</dt>
                <dd className="mt-1">{selected.imageSize ? <SizeBadge label={selected.imageSize} sizeKey={selected.imageSize} /> : 'Không trả ảnh'}</dd>
              </div>
              <div className="grid grid-cols-3 gap-px overflow-hidden rounded-xl border border-orange-100 bg-orange-100">
                <ModalStat label="Input" tokens={selected.promptTokens} cost={selected.inputCostVnd} />
                <ModalStat label="Output" tokens={selected.outputTokens} cost={selected.outputCostVnd} />
                <ModalStat label="Tổng" tokens={selected.totalTokens} cost={selected.costVnd} strong />
              </div>
            </dl>
            <div className="px-5 pb-4">
              <button
                type="button"
                className="h-9 rounded-lg bg-[#ea580c] px-4 text-sm font-semibold text-white hover:bg-[#c2410c]"
                onClick={() => setSelectedId(null)}
              >
                Đóng
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function HeroStat({
  label,
  value,
  hint,
  negative,
  muted,
}: {
  label: string;
  value: string;
  hint: string;
  negative?: boolean;
  muted?: boolean;
}) {
  const tone = muted ? 'text-slate-400' : negative ? 'text-red-600' : 'text-[#ea580c]';
  return (
    <div className="bg-white px-4 py-4">
      <p className="text-sm text-slate-500">{label}</p>
      <p className={`mt-1 text-2xl font-bold tabular-nums sm:text-3xl ${tone}`}>{value}</p>
      <p className="mt-1 text-xs text-slate-500">{hint}</p>
    </div>
  );
}

function MiniStat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="bg-white px-4 py-3">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-1 text-base font-bold tabular-nums text-[#ea580c]">{value}</p>
      {hint ? <p className="mt-0.5 text-[11px] text-slate-400">{hint}</p> : null}
    </div>
  );
}

function SizeBadge({ label, sizeKey }: { label: string; sizeKey: string }) {
  const tone =
    sizeKey === '4K'
      ? 'border-amber-200 bg-amber-50 text-amber-700'
      : sizeKey === 'no-image'
        ? 'border-slate-200 bg-slate-100 text-slate-600'
        : 'border-sky-200 bg-sky-50 text-sky-700';
  return <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${tone}`}>{label}</span>;
}

function TokenCell({ tokens, cost }: { tokens: number; cost: number }) {
  return (
    <td className="px-4 py-2.5 text-right">
      <span className="tabular-nums text-slate-800">{formatNum(tokens)}</span>
      <br />
      <span className="text-xs tabular-nums text-[#ea580c]">{formatVnd(cost)}</span>
    </td>
  );
}

function CostCell({ cost, calls }: { cost: number; calls: number }) {
  return (
    <td className="px-4 py-2.5 text-right">
      <span className="font-semibold tabular-nums text-[#ea580c]">{formatVnd(cost)}</span>
      <br />
      <span className="text-xs text-slate-500">{perCall(cost, calls)}</span>
    </td>
  );
}

function ShareCell({ part, whole }: { part: number; whole: number }) {
  const pct = whole > 0 ? Math.min(100, (part / whole) * 100) : 0;
  return (
    <td className="min-w-[5.5rem] px-4 py-2.5 text-right">
      <span className="text-xs tabular-nums text-slate-600">{formatShare(part, whole)}</span>
      <span className="mt-1 block h-1.5 overflow-hidden rounded-full bg-orange-100">
        <span className="block h-full rounded-full bg-[#ea580c]" style={{ width: `${pct}%` }} />
      </span>
    </td>
  );
}

function EmptyRow({ cols }: { cols: number }) {
  return (
    <tr>
      <td colSpan={cols} className="px-4 py-8 text-center text-sm text-slate-500">
        Chưa có dữ liệu thống kê.
      </td>
    </tr>
  );
}

function ModalStat({ label, tokens, cost, strong }: { label: string; tokens: number; cost: number; strong?: boolean }) {
  return (
    <div className="bg-white px-3 py-2.5">
      <dt className="text-[11px] text-slate-500">{label}</dt>
      <dd className={`mt-0.5 tabular-nums ${strong ? 'font-bold text-slate-900' : 'text-slate-800'}`}>{formatNum(tokens)}</dd>
      <dd className="text-xs font-medium tabular-nums text-[#ea580c]">{formatVnd(cost)}</dd>
    </div>
  );
}

function StatsTable({
  title,
  subtitle,
  nameHeader,
  rows,
  whole,
  nameCell,
}: {
  title: string;
  subtitle: string;
  nameHeader: string;
  rows: ApiStatsBucket[];
  whole: number;
  nameCell: (row: ApiStatsBucket) => ReactNode;
}) {
  return (
    <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <header className="border-b border-slate-100 px-4 py-3">
        <h2 className="text-sm font-semibold text-slate-800">{title}</h2>
        <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>
      </header>
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50 text-left text-slate-500">
            <tr>
              <th className="px-4 py-2 font-medium">{nameHeader}</th>
              <th className="px-4 py-2 text-right font-medium">Lượt gọi</th>
              <th className="px-4 py-2 text-right font-medium">1K</th>
              <th className="px-4 py-2 text-right font-medium">2K</th>
              <th className="px-4 py-2 text-right font-medium">4K</th>
              <th className="px-4 py-2 text-right font-medium">Input</th>
              <th className="px-4 py-2 text-right font-medium">Output</th>
              <th className="px-4 py-2 text-right font-medium">Tổng</th>
              <th className="px-4 py-2 text-right font-medium">Tỷ lệ</th>
              <th className="px-4 py-2 text-right font-medium">Chi phí</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <EmptyRow cols={10} />
            ) : (
              rows.map((row) => (
                <tr key={row.key} className="border-t border-slate-100 hover:bg-orange-50/40">
                  <td className="px-4 py-2.5">{nameCell(row)}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums">{formatNum(row.calls)}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-slate-600">{formatNum(row.calls1K || 0)}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-sky-700">{formatNum(row.calls2K || 0)}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-amber-700">{formatNum(row.calls4K || 0)}</td>
                  <TokenCell tokens={row.promptTokens} cost={row.inputCostVnd} />
                  <TokenCell tokens={row.outputTokens} cost={row.outputCostVnd} />
                  <td className="px-4 py-2.5 text-right font-medium tabular-nums">{formatNum(row.totalTokens)}</td>
                  <ShareCell part={row.costVnd} whole={whole} />
                  <CostCell cost={row.costVnd} calls={row.calls} />
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function PageSkeleton({ compact = false }: { compact?: boolean }) {
  return (
    <div className={compact ? 'mt-4' : 'mx-auto max-w-6xl p-4 sm:p-6'} aria-busy="true" aria-live="polite">
      {!compact ? <p className="text-sm text-slate-500">Đang tải thống kê API…</p> : null}
      <div className="overflow-hidden rounded-2xl border border-orange-100 bg-white">
        <div className="h-14 animate-pulse bg-orange-50" />
        <div className="grid gap-px bg-orange-50 sm:grid-cols-2">
          <div className="h-24 animate-pulse bg-white" />
          <div className="h-24 animate-pulse bg-white" />
        </div>
      </div>
      {compact ? <p className="mt-3 text-sm text-slate-500">Đang tổng hợp chi phí…</p> : null}
    </div>
  );
}
