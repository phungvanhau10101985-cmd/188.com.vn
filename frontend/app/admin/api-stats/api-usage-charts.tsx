'use client';

import type { ReactNode } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { ApiStatsReport } from '@/lib/admin-api';

const MODEL_LINE_COLORS = ['#2563eb', '#06b6d4', '#db2777', '#7c3aed', '#ea580c', '#16a34a', '#ca8a04', '#64748b'];

type Charts = ApiStatsReport['charts'];

function formatTick(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(0)}k`;
  return String(n);
}

function formatVndTick(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}tr₫`;
  if (n >= 1000) return `${(n / 1000).toFixed(0)}k₫`;
  return `${n}₫`;
}

function tooltipFormatPair(value: unknown, name: unknown): [string, string] {
  const n = typeof value === 'number' ? value : Number(value);
  const formatted = Number.isFinite(n) ? n.toLocaleString('vi-VN') : String(value ?? '');
  return [formatted, String(name ?? '')];
}

function tooltipFormatVnd(value: unknown, name: unknown): [string, string] {
  const n = typeof value === 'number' ? value : Number(value);
  const formatted = Number.isFinite(n) ? `${n.toLocaleString('vi-VN')}₫` : String(value ?? '');
  return [formatted, String(name ?? '')];
}

export function ApiUsageCharts({ charts, hasAnyLog }: { charts: Charts; hasAnyLog: boolean }) {
  const { daily, modelKeys, modelLabels, tokensByModelRows, requestsByModelRows, costByModelRows, showOtherSeries, otherKey } =
    charts;
  const seriesKeys = [...modelKeys, ...(showOtherSeries ? [otherKey] : [])];
  const legendName = (key: string) => (key === otherKey ? 'Khác (các model còn lại)' : modelLabels[key] ?? key);

  if (!hasAnyLog || daily.length === 0) {
    return (
      <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <h3 className="text-lg font-semibold text-slate-900">Biểu đồ theo thời gian</h3>
        <p className="mt-1 text-sm text-slate-500">
          Theo ngày giờ Việt Nam trong khoảng đã chọn. Tối đa 8 model đắt nhất; còn lại gộp “Khác”.
        </p>
        <p className="py-8 text-center text-sm text-slate-500">
          Chưa có bản ghi api_usage_log trong khoảng này — không vẽ biểu đồ. Số liệu chỉ có từ lúc bật ghi log.
        </p>
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold tracking-tight text-slate-900">Biểu đồ theo thời gian</h3>
        <p className="mt-0.5 text-sm text-slate-500">
          Theo ngày giờ Việt Nam trong khoảng đã chọn. Tối đa 8 model đắt nhất; còn lại gộp “Khác”.
        </p>
        <p className="mt-2 max-w-3xl text-xs text-slate-500">
          Dữ liệu lấy từ bảng api_usage_log (lượt gọi đã ghi nhận). Không có mã lỗi HTTP (404/500) trong bảng này.
        </p>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard title="Lượt gọi & token input theo ngày">
          <ResponsiveContainer width="100%" height={280}>
            <ComposedChart data={daily} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="dateLabel" tick={{ fontSize: 11 }} />
              <YAxis yAxisId="left" tickFormatter={formatTick} tick={{ fontSize: 11 }} />
              <YAxis yAxisId="right" orientation="right" tickFormatter={formatTick} tick={{ fontSize: 11 }} />
              <Tooltip contentStyle={{ fontSize: 12 }} formatter={tooltipFormatPair} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar yAxisId="left" dataKey="requests" name="Lượt gọi" fill="#3b82f6" radius={[4, 4, 0, 0]} />
              <Line yAxisId="right" type="monotone" dataKey="inputTokens" name="Token input (ngày)" stroke="#22c55e" strokeWidth={2} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Token input / output xếp chồng theo ngày">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={daily} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="dateLabel" tick={{ fontSize: 11 }} />
              <YAxis tickFormatter={formatTick} tick={{ fontSize: 11 }} />
              <Tooltip contentStyle={{ fontSize: 12 }} formatter={tooltipFormatPair} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="inputTokens" stackId="tok" name="Token input" fill="#3b82f6" />
              <Bar dataKey="outputTokens" stackId="tok" name="Token output" fill="#22c55e" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Token input theo model (theo ngày)">
          <ModelLines data={tokensByModelRows} seriesKeys={seriesKeys} legendName={legendName} money={false} />
        </ChartCard>
        <ChartCard title="Lượt gọi theo model (theo ngày)">
          <ModelLines data={requestsByModelRows} seriesKeys={seriesKeys} legendName={legendName} money={false} />
        </ChartCard>
        <ChartCard title="Chi phí ₫ input / output xếp chồng theo ngày">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={daily} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="dateLabel" tick={{ fontSize: 11 }} />
              <YAxis tickFormatter={formatVndTick} tick={{ fontSize: 11 }} />
              <Tooltip contentStyle={{ fontSize: 12 }} formatter={tooltipFormatVnd} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="inputCostVnd" stackId="cost" name="Chi phí input (₫)" fill="#f59e0b" />
              <Bar dataKey="outputCostVnd" stackId="cost" name="Chi phí output (₫)" fill="#dc2626" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Chi phí ₫ theo model (theo ngày)">
          <ModelLines data={costByModelRows} seriesKeys={seriesKeys} legendName={legendName} money />
        </ChartCard>
      </div>
    </section>
  );
}

function ModelLines({
  data,
  seriesKeys,
  legendName,
  money,
}: {
  data: Array<Record<string, string | number>>;
  seriesKeys: string[];
  legendName: (key: string) => string;
  money: boolean;
}) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis dataKey="dateLabel" tick={{ fontSize: 11 }} />
        <YAxis tickFormatter={money ? formatVndTick : formatTick} tick={{ fontSize: 11 }} />
        <Tooltip contentStyle={{ fontSize: 12 }} formatter={money ? tooltipFormatVnd : tooltipFormatPair} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {seriesKeys.map((key, index) => (
          <Line
            key={key}
            type="monotone"
            dataKey={key}
            name={legendName(key)}
            stroke={MODEL_LINE_COLORS[index % MODEL_LINE_COLORS.length]}
            strokeWidth={2}
            dot={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

function ChartCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 pt-5 shadow-sm">
      <h4 className="mb-3 px-1 text-sm font-medium text-slate-800">{title}</h4>
      {children}
    </div>
  );
}
