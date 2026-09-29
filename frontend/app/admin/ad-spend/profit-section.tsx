'use client';

import { FormEvent, useEffect, useMemo, useState } from 'react';
import {
  adminAdSpendAPI,
  type AdSpendProfitOrder,
  type AdSpendProfitSheet,
} from '@/lib/admin-api';
import { listingVndToCny } from '@/lib/taobao-cards-html-parse';

type AdSpendState = 'loading' | 'ready' | 'unavailable';

type ProfitLine = {
  quantity: number;
  unitPriceVnd: number;
  lineTotalVnd: number;
  catalogCny: number | null;
};

type ProfitRow = {
  orderId: number;
  orderCode: string;
  depositedOn: string | null;
  revenueVnd: number;
  merchandiseVnd: number;
  lines: ProfitLine[];
  catalogGoodsCny: number | null;
  goodsTouched: boolean;
  goods: string;
  shipChina: string;
  shipBorder: string;
  shipHanoi: string;
  hadGoodsOverride: boolean;
  hadShipChina: boolean;
  hadShipBorder: boolean;
  hadShipHanoi: boolean;
};

function formatVnd(amount: number): string {
  return new Intl.NumberFormat('vi-VN', {
    style: 'currency',
    currency: 'VND',
    maximumFractionDigits: 0,
  }).format(Math.round(amount));
}

function formatCny(amount: number): string {
  return `${new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 2 }).format(amount)} ¥`;
}

function amountOrNull(raw: string): number | null {
  const text = raw.trim();
  if (!text) return null;
  const n = Number(text);
  if (!Number.isFinite(n) || n < 0) return null;
  return n;
}

function sameAmount(raw: string, expected: number): boolean {
  const n = amountOrNull(raw);
  return n != null && Math.abs(n - expected) < 0.0001;
}

function goodsOverridden(raw: string, catalog: number | null): boolean {
  const n = amountOrNull(raw);
  if (catalog == null) return n != null;
  if (n == null) return false;
  return Math.abs(n - catalog) > 0.0001;
}

function numText(value: number | null | undefined): string {
  if (value == null) return '';
  return String(value);
}

function goodsFromLines(lines: ProfitLine[], rate: number | null, merchandiseVnd: number): number | null {
  if (rate == null || rate <= 0) return null;
  const fromMerchandise = () => {
    if (!(merchandiseVnd > 0)) return null;
    const cny = listingVndToCny(merchandiseVnd, rate);
    return cny == null ? null : Math.round(cny * 100) / 100;
  };
  if (!lines.length) return fromMerchandise();
  let total = 0;
  for (const line of lines) {
    if (line.catalogCny != null && line.catalogCny > 0 && line.quantity > 0) {
      total += line.catalogCny * line.quantity;
      continue;
    }
    if (line.unitPriceVnd > 0 && line.quantity > 0) {
      const cny = listingVndToCny(line.unitPriceVnd, rate);
      if (cny == null) return fromMerchandise();
      total += cny * line.quantity;
      continue;
    }
    if (line.lineTotalVnd > 0) {
      const cny = listingVndToCny(line.lineTotalVnd, rate);
      if (cny == null) return fromMerchandise();
      total += cny;
      continue;
    }
    return fromMerchandise();
  }
  return Math.round(total * 100) / 100;
}

function rowsFromSheet(sheet: AdSpendProfitSheet): ProfitRow[] {
  return sheet.orders.map((order: AdSpendProfitOrder) => ({
    orderId: order.order_id,
    orderCode: order.order_code,
    depositedOn: order.deposited_on,
    revenueVnd: order.revenue_vnd,
    merchandiseVnd: order.merchandise_vnd || 0,
    lines: (order.lines || []).map((line) => ({
      quantity: line.quantity,
      unitPriceVnd: line.unit_price_vnd,
      lineTotalVnd: line.line_total_vnd || 0,
      catalogCny: line.catalog_cny,
    })),
    catalogGoodsCny: order.catalog_goods_cny,
    goodsTouched: false,
    goods: numText(order.goods_cny_override ?? order.catalog_goods_cny),
    shipChina: numText(order.ship_china_domestic_cny_override ?? sheet.ship_china_domestic_cny),
    shipBorder: numText(order.ship_border_to_hanoi_cny_override ?? sheet.ship_border_to_hanoi_cny),
    shipHanoi: numText(order.ship_hanoi_to_customer_vnd_override ?? sheet.ship_hanoi_to_customer_vnd),
    hadGoodsOverride: order.goods_cny_override != null,
    hadShipChina: order.ship_china_domestic_cny_override != null,
    hadShipBorder: order.ship_border_to_hanoi_cny_override != null,
    hadShipHanoi: order.ship_hanoi_to_customer_vnd_override != null,
  }));
}

function lineCny(row: ProfitRow, rate: number | null): number | null {
  const goods = amountOrNull(row.goods);
  const china = amountOrNull(row.shipChina);
  const border = amountOrNull(row.shipBorder);
  const hanoi = amountOrNull(row.shipHanoi);
  if (goods == null || china == null || border == null || hanoi == null || rate == null || rate <= 0) return null;
  return goods + china + border + hanoi / rate;
}

function lineCost(row: ProfitRow, rate: number | null): number | null {
  const cny = lineCny(row, rate);
  if (cny == null || rate == null) return null;
  return cny * rate;
}

export function AdSpendProfitSection({
  dateFrom,
  dateTo,
  refreshKey,
  adSpend,
  adSpendState,
}: {
  dateFrom: string;
  dateTo: string;
  refreshKey: number;
  adSpend: number | null;
  adSpendState: AdSpendState;
}) {
  const [rate, setRate] = useState('');
  const [shipChina, setShipChina] = useState('0');
  const [shipBorder, setShipBorder] = useState('0');
  const [shipHanoi, setShipHanoi] = useState('0');
  const [rows, setRows] = useState<ProfitRow[]>([]);
  const [truncated, setTruncated] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const applySheet = (sheet: AdSpendProfitSheet) => {
    setRate(numText(sheet.vnd_per_cny));
    setShipChina(numText(sheet.ship_china_domestic_cny));
    setShipBorder(numText(sheet.ship_border_to_hanoi_cny));
    setShipHanoi(numText(sheet.ship_hanoi_to_customer_vnd));
    setRows(rowsFromSheet(sheet));
    setTruncated(sheet.truncated);
  };

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      applySheet(await adminAdSpendAPI.getProfit(dateFrom, dateTo));
    } catch (err) {
      setError((err as Error)?.message || 'Không tải được hạch toán.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // refreshKey tăng khi bấm khoảng ngày hoặc «Xem chi phí».
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey]);

  const rateNumber = amountOrNull(rate);
  const chinaDefault = amountOrNull(shipChina);
  const borderDefault = amountOrNull(shipBorder);
  const hanoiDefault = amountOrNull(shipHanoi);

  useEffect(() => {
    if (rateNumber == null || rateNumber <= 0) return;
    setRows((prev) =>
      prev.map((row) => {
        if (row.hadGoodsOverride || row.goodsTouched) return row;
        const next = goodsFromLines(row.lines, rateNumber, row.merchandiseVnd);
        if (next == null) {
          if (!row.goods && row.catalogGoodsCny == null) return row;
          return { ...row, catalogGoodsCny: null, goods: '' };
        }
        if (row.catalogGoodsCny === next && sameAmount(row.goods, next)) return row;
        return { ...row, catalogGoodsCny: next, goods: numText(next) };
      }),
    );
  }, [rateNumber]);

  const summary = useMemo(() => {
    const revenue = rows.reduce((sum, row) => sum + row.revenueVnd, 0);
    let goodsSum = 0;
    let goodsMissing = 0;
    for (const row of rows) {
      const goods = amountOrNull(row.goods);
      if (goods == null) goodsMissing += 1;
      else goodsSum += goods;
    }
    const revenueCny = goodsMissing === 0 ? goodsSum : null;
    let cost = 0;
    let missing = 0;
    for (const row of rows) {
      const line = lineCost(row, rateNumber);
      if (line == null) missing += 1;
      else cost += line;
    }
    const costReady = missing === 0;
    const gross = costReady ? revenue - cost : null;
    const profit = costReady && adSpendState === 'ready' && adSpend != null ? revenue - cost - adSpend : null;
    return { revenue, revenueCny, cost: costReady ? cost : null, missing, gross, profit };
  }, [rows, rateNumber, adSpend, adSpendState]);

  const patchRow = (orderId: number, patch: Partial<ProfitRow>) => {
    setRows((prev) => prev.map((row) => (row.orderId === orderId ? { ...row, ...patch } : row)));
  };

  const onDefault = (field: 'shipChina' | 'shipBorder' | 'shipHanoi', value: string) => {
    const previous = field === 'shipChina' ? shipChina : field === 'shipBorder' ? shipBorder : shipHanoi;
    if (field === 'shipChina') setShipChina(value);
    if (field === 'shipBorder') setShipBorder(value);
    if (field === 'shipHanoi') setShipHanoi(value);
    setRows((prev) => prev.map((row) => (row[field] === previous ? { ...row, [field]: value } : row)));
  };

  const onSave = async (event: FormEvent) => {
    event.preventDefault();
    if (rateNumber == null || rateNumber <= 0 || chinaDefault == null || borderDefault == null || hanoiDefault == null) {
      setError('Nhập tỷ giá và tiền ship mức chung. Các số không được âm.');
      return;
    }
    const invalid = rows.some((row) => {
      if (row.goods.trim() && amountOrNull(row.goods) == null) return true;
      return amountOrNull(row.shipChina) == null || amountOrNull(row.shipBorder) == null || amountOrNull(row.shipHanoi) == null;
    });
    if (invalid) {
      setError('Có ô tiền không đọc được. Nhập số không âm, dùng dấu chấm cho phần thập phân.');
      return;
    }
    const orders = rows
      .filter((row) => rowNeedsSave(row, chinaDefault, borderDefault, hanoiDefault))
      .map((row) => ({
        order_id: row.orderId,
        goods_cny: goodsOverridden(row.goods, row.catalogGoodsCny) ? amountOrNull(row.goods) : null,
        ship_china_domestic_cny: sameAmount(row.shipChina, chinaDefault) ? null : amountOrNull(row.shipChina),
        ship_border_to_hanoi_cny: sameAmount(row.shipBorder, borderDefault) ? null : amountOrNull(row.shipBorder),
        ship_hanoi_to_customer_vnd: sameAmount(row.shipHanoi, hanoiDefault) ? null : amountOrNull(row.shipHanoi),
      }));
    setSaving(true);
    setError(null);
    try {
      const saved = await adminAdSpendAPI.saveProfit({
        date_from: dateFrom,
        date_to: dateTo,
        vnd_per_cny: rateNumber,
        ship_china_domestic_cny: chinaDefault,
        ship_border_to_hanoi_cny: borderDefault,
        ship_hanoi_to_customer_vnd: hanoiDefault,
        orders,
      });
      applySheet(saved);
      setNotice('Đã lưu tỷ giá và tiền ship.');
      setTimeout(() => setNotice(null), 4000);
    } catch (err) {
      setError((err as Error)?.message || 'Không lưu được hạch toán.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="mt-8 rounded-xl border border-slate-200 bg-white shadow-sm" aria-label="Hạch toán lợi nhuận">
      <div className="border-b border-slate-100 px-4 py-3">
        <h2 className="text-sm font-semibold text-slate-900">Hạch toán lợi nhuận</h2>
        <p className="mt-1 text-xs text-slate-500">
          Chỉ đơn đã cọc trong khoảng ngày. Giá hàng ¥ là giá tệ lúc cào sản phẩm. Đơn không lưu giá tệ thì đảo từ giá
          bán theo đúng lưới cào: giá bán ≈ CN¥ × hệ số × tỷ giá, làm tròn lên 10.000đ. Lợi nhuận = giá bán − (giá hàng
          ¥ + ship Trung Quốc ¥ + ship cửa khẩu ¥) × tỷ giá − ship Hà Nội − quảng cáo.
        </p>
      </div>

      {error ? (
        <div className="mx-4 mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}{' '}
          <button type="button" className="font-medium underline" onClick={() => void load()}>
            Thử lại
          </button>
        </div>
      ) : null}
      {notice ? (
        <div className="mx-4 mt-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          {notice}
        </div>
      ) : null}

      {loading ? <p className="px-4 py-6 text-sm text-slate-500">Đang tải đơn đã cọc…</p> : null}

      {!loading ? (
        <form onSubmit={onSave} className="space-y-4 px-4 py-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <label className="text-sm text-slate-700">
              Tỷ giá (₫ / 1 ¥)
              <input
                type="number"
                min="0"
                step="0.0001"
                required
                value={rate}
                onChange={(e) => setRate(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
              />
            </label>
            <label className="text-sm text-slate-700">
              Ship TQ nội địa (¥ / đơn)
              <input
                type="number"
                min="0"
                step="0.01"
                value={shipChina}
                onChange={(e) => onDefault('shipChina', e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
              />
            </label>
            <label className="text-sm text-slate-700">
              Ship cửa khẩu về Hà Nội (¥ / đơn)
              <input
                type="number"
                min="0"
                step="0.01"
                value={shipBorder}
                onChange={(e) => onDefault('shipBorder', e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
              />
            </label>
            <label className="text-sm text-slate-700">
              Ship Hà Nội đến khách (₫ / đơn)
              <input
                type="number"
                min="0"
                step="1"
                value={shipHanoi}
                onChange={(e) => onDefault('shipHanoi', e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
              />
            </label>
          </div>
          <p className="text-xs text-slate-500">
            Mức ship chung áp cho mọi đơn. Sửa ô trong bảng nếu đơn đó khác. Đổi tỷ giá thì giá tệ đảo từ giá bán được
            tính lại; giá tệ đã lưu lúc cào giữ nguyên.
          </p>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <SummaryCard label="Doanh thu đã cọc" value={formatVnd(summary.revenue)} hint={`${rows.length} đơn`} />
            <SummaryCard
              label="Giá hàng quy ra tệ"
              value={summary.revenueCny == null ? '—' : formatCny(summary.revenueCny)}
              hint="Giá tệ lúc cào, hoặc đảo theo lưới"
            />
            <SummaryCard
              label="Giá vốn"
              value={summary.cost == null ? '—' : formatVnd(summary.cost)}
              hint="Giá tệ × tỷ giá + ship Hà Nội"
            />
            <SummaryCard
              label="Quảng cáo"
              value={adSpendState === 'loading' ? 'Đang đọc…' : adSpendState === 'ready' && adSpend != null ? formatVnd(adSpend) : '—'}
              hint={adSpendState === 'ready' ? 'Google + Facebook' : 'Chưa cộng được vào lợi nhuận'}
            />
            <SummaryCard
              label="Lợi nhuận"
              value={summary.profit == null ? '—' : formatVnd(summary.profit)}
              hint={summary.gross == null ? 'Còn đơn thiếu giá tệ' : `Lãi trước quảng cáo ${formatVnd(summary.gross)}`}
              emphasize
              negative={summary.profit != null && summary.profit < 0}
            />
          </div>

          {summary.missing > 0 ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              {summary.missing} đơn chưa có đủ giá tệ nên tổng giá vốn và lợi nhuận chưa chốt. Nhập giá hàng ¥ cho các
              đơn đó.
            </div>
          ) : null}
          {truncated ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              Kỳ này nhiều hơn 400 đơn đã cọc. Rút ngắn khoảng ngày để hạch toán đủ.
            </div>
          ) : null}

          {rows.length === 0 ? (
            <p className="text-sm text-slate-500">Không có đơn đã cọc trong khoảng này.</p>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <table className="min-w-full text-sm">
                <thead className="bg-slate-50 text-left text-slate-500">
                  <tr>
                    <th className="px-3 py-2 font-medium">Đơn</th>
                    <th className="px-3 py-2 font-medium">Ngày cọc</th>
                    <th className="px-3 py-2 font-medium">Giá bán</th>
                    <th className="px-3 py-2 font-medium">Giá hàng ¥</th>
                    <th className="px-3 py-2 font-medium">Ship TQ ¥</th>
                    <th className="px-3 py-2 font-medium">Cửa khẩu ¥</th>
                    <th className="px-3 py-2 font-medium">Hà Nội ₫</th>
                    <th className="px-3 py-2 font-medium">Giá tệ</th>
                    <th className="px-3 py-2 font-medium">Giá vốn</th>
                    <th className="px-3 py-2 font-medium">Lãi gộp</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => {
                    const cny = lineCny(row, rateNumber);
                    const cost = lineCost(row, rateNumber);
                    const gross = cost == null ? null : row.revenueVnd - cost;
                    return (
                      <tr key={row.orderId} className="border-t border-slate-100">
                        <td className="px-3 py-2 font-medium text-slate-800">{row.orderCode}</td>
                        <td className="px-3 py-2 whitespace-nowrap text-slate-600">{row.depositedOn || '—'}</td>
                        <td className="px-3 py-2 whitespace-nowrap">{formatVnd(row.revenueVnd)}</td>
                        <td className="px-3 py-2">
                          <input
                            aria-label={`Giá hàng tệ ${row.orderCode}`}
                            type="number"
                            min="0"
                            step="0.01"
                            value={row.goods}
                            placeholder={row.catalogGoodsCny == null ? 'Nhập ¥' : undefined}
                            onChange={(e) => patchRow(row.orderId, { goods: e.target.value, goodsTouched: true })}
                            className="w-24 rounded border border-slate-300 px-2 py-1"
                          />
                        </td>
                        <td className="px-3 py-2">
                          <input
                            aria-label={`Ship Trung Quốc ${row.orderCode}`}
                            type="number"
                            min="0"
                            step="0.01"
                            value={row.shipChina}
                            onChange={(e) => patchRow(row.orderId, { shipChina: e.target.value })}
                            className="w-24 rounded border border-slate-300 px-2 py-1"
                          />
                        </td>
                        <td className="px-3 py-2">
                          <input
                            aria-label={`Ship cửa khẩu ${row.orderCode}`}
                            type="number"
                            min="0"
                            step="0.01"
                            value={row.shipBorder}
                            onChange={(e) => patchRow(row.orderId, { shipBorder: e.target.value })}
                            className="w-24 rounded border border-slate-300 px-2 py-1"
                          />
                        </td>
                        <td className="px-3 py-2">
                          <input
                            aria-label={`Ship Hà Nội ${row.orderCode}`}
                            type="number"
                            min="0"
                            step="1"
                            value={row.shipHanoi}
                            onChange={(e) => patchRow(row.orderId, { shipHanoi: e.target.value })}
                            className="w-28 rounded border border-slate-300 px-2 py-1"
                          />
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap">{cny == null ? '—' : formatCny(cny)}</td>
                        <td className="px-3 py-2 whitespace-nowrap">{cost == null ? '—' : formatVnd(cost)}</td>
                        <td
                          className={`px-3 py-2 whitespace-nowrap ${gross != null && gross < 0 ? 'text-red-700' : 'text-slate-800'}`}
                        >
                          {gross == null ? '—' : formatVnd(gross)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          <button
            type="submit"
            disabled={saving}
            className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-60"
          >
            {saving ? 'Đang lưu…' : 'Lưu tỷ giá và tiền ship'}
          </button>
        </form>
      ) : null}
    </section>
  );
}

function rowNeedsSave(row: ProfitRow, china: number, border: number, hanoi: number): boolean {
  return (
    goodsOverridden(row.goods, row.catalogGoodsCny) ||
    !sameAmount(row.shipChina, china) ||
    !sameAmount(row.shipBorder, border) ||
    !sameAmount(row.shipHanoi, hanoi) ||
    row.hadGoodsOverride ||
    row.hadShipChina ||
    row.hadShipBorder ||
    row.hadShipHanoi
  );
}

function SummaryCard({
  label,
  value,
  hint,
  emphasize,
  negative,
}: {
  label: string;
  value: string;
  hint: string;
  emphasize?: boolean;
  negative?: boolean;
}) {
  return (
    <div className={`rounded-xl border p-3 ${emphasize ? 'border-slate-300 bg-slate-50' : 'border-slate-200 bg-white'}`}>
      <p className="text-xs text-slate-500">{label}</p>
      <p className={`mt-1 text-lg font-semibold ${negative ? 'text-red-700' : 'text-slate-900'}`}>{value}</p>
      <p className="mt-1 text-xs text-slate-500">{hint}</p>
    </div>
  );
}
