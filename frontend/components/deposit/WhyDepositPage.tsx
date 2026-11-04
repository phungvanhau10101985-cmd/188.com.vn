'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useToast } from '@/components/ToastProvider';
import { depositPolicyFromApi, type DepositPolicy } from '@/lib/deposit-policy';
import { formatDepositMinVnd } from '@/lib/order-deposit';
import { apiClient } from '@/lib/api-client';
import { trackEvent } from '@/lib/analytics';

type Props = {
  orderId: number | null;
  orderCode: string;
  zaloUrl: string;
  deposit: DepositPolicy;
};

function zaloMessage(orderCode: string): string {
  if (orderCode) {
    return `Em cần hỏi về đặt cọc đơn #${orderCode}. Em đang xem trang thanh toán cọc trên 188.com.vn.`;
  }
  return 'Em cần hỏi về chính sách đặt cọc trên 188.com.vn.';
}

export default function WhyDepositPage({ orderId, orderCode, zaloUrl, deposit }: Props) {
  const { pushToast } = useToast();
  const [policy, setPolicy] = useState(deposit);
  const { percent, minAmount, highOrderAmount, highOrderPercent } = policy;

  useEffect(() => {
    let cancelled = false;
    apiClient
      .getDepositPolicy()
      .then((data) => {
        if (!cancelled) setPolicy(depositPolicyFromApi(data));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);
  const backHref = orderId ? `/account/orders/${orderId}/deposit` : '/account/orders';
  const backLabel = orderId ? 'Quay lại thanh toán cọc' : 'Xem đơn hàng của tôi';

  const contactZalo = () => {
    const message = zaloMessage(orderCode);
    trackEvent('deposit_why_zalo_click', {
      order_id: orderId ?? undefined,
      has_order_code: Boolean(orderCode),
    });
    window.open(zaloUrl, '_blank', 'noopener,noreferrer');
    const clipboard = typeof navigator !== 'undefined' ? navigator.clipboard : undefined;
    if (!clipboard?.writeText) {
      pushToast({
        title: 'Đã mở Zalo',
        description: message,
        variant: 'info',
        durationMs: 6000,
      });
      return;
    }
    void clipboard.writeText(message).then(
      () => {
        pushToast({
          title: 'Đã chép tin nhắn',
          description: orderCode
            ? 'Dán vào ô chat Zalo rồi gửi. Tin đã kèm mã đơn.'
            : 'Dán vào ô chat Zalo rồi gửi.',
          variant: 'success',
          durationMs: 4000,
        });
      },
      () => {
        pushToast({
          title: 'Đã mở Zalo',
          description: message,
          variant: 'info',
          durationMs: 6000,
        });
      },
    );
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="mx-auto max-w-2xl px-3 py-4 sm:px-4 sm:py-8">
        <article className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-md">
          <header className="bg-gradient-to-r from-orange-600 to-amber-500 px-4 py-4 text-white md:px-6">
            <h1 className="text-lg font-bold leading-tight md:text-xl">Tại sao phải đặt cọc?</h1>
            <p className="mt-1 text-sm text-orange-50">
              {orderCode ? `Đơn #${orderCode}. ` : null}
              188 có kho ở nước ngoài. Hàng xuất từ kho của shop, không mua hộ chỗ khác. Đưa về Việt Nam tốn nhiều loại phí nên cần cọc trước.
            </p>
          </header>

          <div className="space-y-4 px-4 py-4 text-sm leading-relaxed text-gray-700 md:px-6 md:py-5">
            <section>
              <h2 className="font-semibold text-gray-900">Hàng lấy từ kho của shop ở nước ngoài</h2>
              <p className="mt-1">
                188 nhập và giữ hàng tại kho riêng ở nước ngoài. Khi quý khách đặt, shop xuất đúng mẫu, đúng size từ kho của mình rồi chuyển về Việt Nam. Đơn không bị chuyển sang một shop khác để mua hộ.
              </p>
              <p className="mt-1">
                Kho ở nước ngoài nên hàng chưa nằm sẵn tại Việt Nam để giao trong ngày. Shop chủ động nguồn hàng, quý khách vẫn nhận được mẫu shop đang bán.
              </p>
            </section>

            <section>
              <h2 className="font-semibold text-gray-900">Đưa về Việt Nam tốn nhiều loại phí</h2>
              <p className="mt-1">
                Từ kho đến tay quý khách còn cước vận chuyển quốc tế, phí thông quan, thuế và phí chuyển tiếp trong nước. Mỗi loại phí đều lớn, và shop phải chi trước khi hàng về tới Việt Nam.
              </p>
              <p className="mt-1">
                Cọc là phần quý khách cùng chịu chi phí đường về. Phần còn lại trả khi nhận hàng, sau khi đã kiểm tra được hàng.
              </p>
            </section>

            <section>
              <h2 className="font-semibold text-gray-900">Cọc để giữ đơn, tránh hủy ngang</h2>
              <p className="mt-1">
                Hàng đã xuất kho và lên chuyến thì cước quốc tế cùng các loại phí không thu lại được. Mẫu đã tách theo size cũng khó bán lại cho người khác.
              </p>
              <p className="mt-1">
                Cọc xác nhận quý khách giữ đơn. Shop chỉ chi phí vận chuyển cho đơn đã có chuyển khoản, nên đơn được xử lý thật, không bị hủy giữa chừng.
              </p>
            </section>

            <section className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-3">
              <h2 className="font-semibold text-gray-900">Quý khách chỉ cọc một phần</h2>
              <p className="mt-1">
                Mức mặc định là <strong>{percent}% giá trị hàng</strong>, tối thiểu{' '}
                <strong>{formatDepositMinVnd(minAmount)}</strong>. Phần còn lại và phí giao hàng trong nước, nếu có, trả khi nhận hàng.
              </p>
              <p className="mt-1">
                Muốn trả hết thì chọn <strong>cọc 100%</strong> trên trang QR. Khoản đó gồm cả phí ship, không còn số phải trả lúc nhận.
              </p>
              <p className="mt-1">
                Đơn từ <strong>{formatDepositMinVnd(highOrderAmount)}</strong> cọc{' '}
                <strong>{highOrderPercent}%</strong>, vì cước và các loại phí của đơn càng lớn.
              </p>
            </section>

            <section>
              <h2 className="font-semibold text-gray-900">Cọc vẫn được giữ đúng</h2>
              <p className="mt-1">
                Shop giao hàng có kiểm tra. Hàng không đúng mô tả hoặc lỗi sản xuất: gửi mẫu khác đúng mô tả hoặc hoàn tiền đặt cọc. Không vừa size: hỗ trợ đổi size 1 lần, không đổi mẫu.
              </p>
            </section>

            <section>
              <h2 className="font-semibold text-gray-900">Cọc xong shop xuất kho và chuyển về</h2>
              <p className="mt-1">
                Quét mã QR và ghi đúng nội dung chuyển khoản. Đúng nội dung thì shop xác nhận cọc tự động, xuất hàng từ kho nước ngoài và chuyển về Việt Nam.
              </p>
            </section>
          </div>

          <div className="space-y-2 border-t border-gray-100 bg-gray-50 px-4 py-4 md:px-6">
            <Link
              href={backHref}
              onClick={() =>
                trackEvent('deposit_why_back_to_pay', { order_id: orderId ?? undefined })
              }
              className="inline-flex w-full items-center justify-center rounded-xl bg-orange-600 px-4 py-3 text-sm font-semibold text-white shadow-sm hover:bg-orange-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-600"
            >
              {backLabel}
            </Link>
            <button
              type="button"
              onClick={contactZalo}
              className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[#0068FF] px-4 py-3 text-sm font-semibold text-white shadow-sm hover:bg-[#0057d6] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0068FF]"
            >
              Nhắn Zalo cho shop
            </button>
            <p className="text-center text-xs leading-snug text-gray-500">
              Giờ trả lời Zalo: 8h00–16h30, thứ Hai đến thứ Bảy.
              {orderCode ? ' Bấm nút sẽ chép sẵn câu hỏi kèm mã đơn để dán vào chat.' : null}
            </p>
            <p className="text-center text-xs text-gray-500">
              <Link href="/info/huong-dan-mua-hang" className="font-medium text-orange-700 underline hover:text-orange-800">
                Xem hướng dẫn mua hàng
              </Link>
            </p>
          </div>
        </article>
      </div>
    </div>
  );
}
