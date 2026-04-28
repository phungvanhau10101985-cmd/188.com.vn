import InfoPageLayout from '@/components/info/InfoPageLayout';
import Link from 'next/link';

export const metadata = {
  title: 'Chính sách bảo mật',
  description:
    'Chính sách bảo mật email và số điện thoại khách hàng tại 188.COM.VN.',
};

export default function ChinhSachBaoMatPage() {
  return (
    <InfoPageLayout title="Chính sách bảo mật">
      <p className="text-sm font-semibold uppercase tracking-wide text-zinc-500 mb-6">
        Chính sách bảo mật email và số điện thoại khách hàng
      </p>

      <div className="space-y-10 text-zinc-600">
        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">1. Mục đích thu thập thông tin</h2>
          <p className="mb-4">
            <strong className="text-zinc-800">188.COM.VN</strong> thu thập email và số điện thoại của khách hàng nhằm phục vụ cho các mục đích sau:
          </p>
          <ul className="list-disc pl-5 space-y-2">
            <li>Liên hệ xác nhận đơn hàng, tư vấn sản phẩm và hỗ trợ dịch vụ.</li>
            <li>Gửi thông tin giao hàng, mã vận đơn hoặc thông báo thay đổi trạng thái đơn hàng.</li>
            <li>
              Gửi các chương trình khuyến mãi, ưu đãi đặc biệt hoặc thông báo quan trọng (chỉ khi khách hàng đồng ý).
            </li>
            <li>Chúng tôi không thu thập thông tin vượt quá phạm vi cần thiết cho hoạt động thương mại điện tử hợp pháp.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">2. Phạm vi sử dụng thông tin</h2>
          <p className="mb-4">
            Thông tin email và số điện thoại của khách hàng được sử dụng chỉ trong nội bộ hệ thống 188.COM.VN, bao gồm:
          </p>
          <ul className="list-disc pl-5 space-y-2 mb-4">
            <li>Bộ phận bán hàng, chăm sóc khách hàng và giao vận để hoàn tất đơn hàng.</li>
            <li>
              Cung cấp cho đơn vị vận chuyển hoặc đối tác thanh toán trong phạm vi cần thiết cho việc giao nhận hàng hóa.
            </li>
          </ul>
          <p className="mb-4">
            Ngoài các trường hợp trên, chúng tôi không chia sẻ, không bán, không trao đổi hoặc tiết lộ thông tin liên hệ của khách hàng cho bất kỳ bên thứ ba nào, trừ khi có:
          </p>
          <ul className="list-disc pl-5 space-y-2">
            <li>Yêu cầu hợp pháp từ cơ quan nhà nước có thẩm quyền; hoặc</li>
            <li>Sự đồng ý bằng văn bản của khách hàng.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">3. Thời gian lưu trữ thông tin</h2>
          <p className="mb-4">Thông tin liên hệ (email và số điện thoại) sẽ được lưu trữ:</p>
          <ul className="list-disc pl-5 space-y-2">
            <li>Đến khi khách hàng yêu cầu xóa bỏ khỏi hệ thống.</li>
            <li>Sau thời hạn trên, dữ liệu sẽ được xóa hoặc ẩn danh hoàn toàn để đảm bảo an toàn thông tin.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">4. Biện pháp bảo mật</h2>
          <p className="mb-4">
            Chúng tôi áp dụng nhiều biện pháp kỹ thuật và quản lý để bảo vệ thông tin cá nhân, bao gồm:
          </p>
          <ul className="list-disc pl-5 space-y-2">
            <li>Mã hóa dữ liệu trên hệ thống lưu trữ.</li>
            <li>Giới hạn quyền truy cập nội bộ đối với nhân viên được ủy quyền.</li>
            <li>Không hiển thị toàn bộ số điện thoại/email ra bên ngoài hệ thống.</li>
            <li>Kiểm soát truy cập và sao lưu định kỳ để phòng ngừa rủi ro mất mát dữ liệu.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">5. Quyền của khách hàng</h2>
          <p className="mb-4">Khách hàng có quyền:</p>
          <ul className="list-disc pl-5 space-y-2 mb-4">
            <li>Yêu cầu chỉnh sửa, cập nhật hoặc xóa bỏ thông tin email/số điện thoại đã cung cấp.</li>
            <li>Từ chối nhận tin nhắn, email quảng cáo hoặc thông báo tự động từ 188.COM.VN.</li>
            <li>Khiếu nại nếu phát hiện thông tin bị sử dụng sai mục đích.</li>
          </ul>
          <p className="mb-2">Yêu cầu có thể gửi đến:</p>
          <ul className="list-none pl-0 space-y-2">
            <li>
              <Link href="/info/lien-he" className="text-orange-600 underline hover:text-orange-700 font-medium">
                Thông tin liên hệ
              </Link>{' '}
              — hotline{' '}
              <a href="tel:0968659836" className="text-orange-600 underline hover:text-orange-700">
                0968 659 836
              </a>
              , email{' '}
              <a href="mailto:hotro@188.com.vn" className="text-orange-600 underline hover:text-orange-700">
                hotro@188.com.vn
              </a>
              .
            </li>
          </ul>
        </section>
      </div>

      <div className="mt-10 p-4 bg-orange-50 border border-orange-100 rounded-xl text-zinc-700 text-sm space-y-2">
        <p className="font-semibold text-zinc-900">Thông tin đơn vị sở hữu website 188.COM.VN</p>
        <p>Website 188.COM.VN thuộc quyền sở hữu và quản lý của Hộ Kinh Doanh Phùng Văn Hậu.</p>
        <p>
          <strong>Giấy chứng nhận đăng ký hộ kinh doanh:</strong> 01Q8011025
        </p>
        <p>
          <strong>Địa chỉ:</strong> Xóm Buối, Thôn Vật Lại 3, Xã Vật Lại, Huyện Ba Vì, Thành phố Hà Nội
        </p>
        <p>
          <strong>Điện thoại:</strong> 0968 659 836 (Giờ làm việc: 8h00 – 16h30){' '}
          <span className="block sm:inline">
            <strong>Email:</strong>{' '}
            <a href="mailto:hotro@188.com.vn" className="text-orange-600 underline hover:text-orange-700">
              hotro@188.com.vn
            </a>
          </span>
        </p>
        <p className="italic text-zinc-600">Quý khách vui lòng liên hệ trước khi đến làm việc để được hỗ trợ và phục vụ tốt nhất.</p>
        <p className="pt-2 border-t border-orange-100 text-zinc-500">
          Xem thêm{' '}
          <Link href="/info/huong-dan-mua-hang" className="text-orange-700 underline font-medium hover:text-orange-800">
            Hướng dẫn mua hàng – Điều kiện thanh toán
          </Link>
          ,{' '}
          <Link href="/info/doi-tra-hoan-tien" className="text-orange-700 underline font-medium hover:text-orange-800">
            Đổi trả &amp; Hoàn tiền
          </Link>
          .
        </p>
      </div>
    </InfoPageLayout>
  );
}
