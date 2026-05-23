'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { apiClient } from '@/lib/api-client';

type ShipmentEvent = {
  step_key: string;
  title: string;
  status: string;
  scheduled_at?: string | null;
  completed_at?: string | null;
  note?: string | null;
};

type Timeline = {
  order_id: number;
  order_code: string;
  order_status: string;
  tracking_number?: string | null;
  shipping_provider?: string | null;
  footer_note: string;
  current_step_key?: string | null;
  waiting_admin_at_customs: boolean;
  events: ShipmentEvent[];
};

function formatWhen(iso?: string | null) {
  if (!iso) return null;
  return new Date(iso).toLocaleString('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function stepIcon(status: string) {
  if (status === 'completed') {
    return (
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-green-500 text-white text-sm font-bold">
        ✓
      </span>
    );
  }
  if (status === 'active') {
    return (
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#ea580c] text-white text-xs font-bold ring-4 ring-orange-100">
        ●
      </span>
    );
  }
  return <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gray-200 text-gray-400 text-xs">○</span>;
}

export default function OrderTrackingPage() {
  const params = useParams();
  const orderId = Number(params?.id);
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    if (!orderId) return;
    setLoading(true);
    setError(null);
    apiClient
      .getOrderShipmentTimeline(orderId)
      .then(setTimeline)
      .catch((e) => {
        setTimeline(null);
        setError((e as Error)?.message || 'Không tải được lịch trình đơn hàng');
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, [orderId]);

  if (loading) {
    return (
      <div className="py-12 text-center text-gray-500">
        <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-4 border-[#ea580c] border-t-transparent" />
        Đang tải lịch trình…
      </div>
    );
  }

  if (error || !timeline) {
    return (
      <div className="rounded-xl border border-red-100 bg-red-50 p-6 text-center">
        <p className="text-sm text-red-700">{error || 'Không có dữ liệu lịch trình.'}</p>
        <button type="button" onClick={load} className="mt-3 text-sm font-medium text-[#ea580c] underline">
          Thử lại
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Link href={`/account/orders/${orderId}`} className="text-sm text-gray-500 hover:text-gray-800">
          ← Chi tiết đơn hàng
        </Link>
        <h1 className="text-xl font-bold text-gray-900">Lịch trình đơn hàng</h1>
        <span className="rounded-full bg-orange-100 px-3 py-1 text-sm font-medium text-orange-800">
          #{timeline.order_code}
        </span>
      </div>

      {(timeline.tracking_number || timeline.shipping_provider) && (
        <div className="rounded-xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-900">
          {timeline.shipping_provider ? <p>Đơn vị giao: <strong>{timeline.shipping_provider}</strong></p> : null}
          {timeline.tracking_number ? (
            <p className="mt-1">
              Mã vận đơn nội địa: <strong className="font-mono">{timeline.tracking_number}</strong>
            </p>
          ) : null}
        </div>
      )}

      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <ol className="relative space-y-0">
          {timeline.events.map((ev, idx) => {
            const when = formatWhen(ev.completed_at) || (ev.status === 'active' ? 'Đang xử lý' : null);
            const isLast = idx === timeline.events.length - 1;
            return (
              <li key={ev.step_key} className="relative flex gap-4 pb-8 last:pb-0">
                {!isLast ? (
                  <span
                    className={`absolute left-[13px] top-8 h-[calc(100%-1.25rem)] w-0.5 ${
                      ev.status === 'completed' ? 'bg-green-300' : 'bg-gray-200'
                    }`}
                    aria-hidden
                  />
                ) : null}
                {stepIcon(ev.status)}
                <div className="min-w-0 flex-1 pt-0.5">
                  <p
                    className={`text-sm font-medium leading-snug ${
                      ev.status === 'active'
                        ? 'text-[#ea580c]'
                        : ev.status === 'completed'
                          ? 'text-gray-900'
                          : 'text-gray-400'
                    }`}
                  >
                    {ev.title}
                  </p>
                  {when ? <p className="mt-1 text-xs text-gray-500">{when}</p> : null}
                  {ev.note ? (
                    <p
                      className={`mt-1.5 text-xs leading-relaxed ${
                        ev.status === 'active' && ev.step_key === 'at_customs'
                          ? 'text-gray-500'
                          : 'text-gray-400'
                      }`}
                    >
                      {ev.note}
                    </p>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ol>
      </div>

      <p className="text-xs leading-relaxed text-gray-400 px-1">
        {timeline.footer_note}
      </p>
    </div>
  );
}
