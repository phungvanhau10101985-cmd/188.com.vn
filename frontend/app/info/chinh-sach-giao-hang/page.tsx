import InfoPageLayout from '@/components/info/InfoPageLayout';
import Link from 'next/link';

export const metadata = {
  title: 'Chính sách giao hàng',
  description:
    'Chính sách giao hàng toàn quốc, thời gian, phí ship và kiểm tra hàng tại 188.COM.VN.',
};

export default function ChinhSachGiaoHangPage() {
  return (
    <InfoPageLayout title="Chính sách giao hàng">
      <p className="text-sm font-semibold uppercase tracking-wide text-zinc-500 mb-6">
        Chính sách giao hàng – 188.COM.VN
      </p>

      <div className="space-y-10 text-zinc-600">
        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">1. Phạm vi áp dụng</h2>
          <p className="mb-4">
            <strong className="text-zinc-800">188.COM.VN</strong> cung cấp dịch vụ giao hàng toàn quốc, bao gồm tất cả các tỉnh, thành phố trên lãnh thổ Việt Nam.
          </p>
          <p className="mb-4">
            Chúng tôi hợp tác với các đơn vị vận chuyển uy tín như Giao Hàng Nhanh (GHN), Viettel Post, J&amp;T Express, và một số đối tác khác nhằm đảm bảo hàng hóa đến tay khách hàng nhanh chóng, an toàn.
          </p>
          <p className="mb-2">Khách hàng có thể lựa chọn:</p>
          <ul className="list-disc pl-5 space-y-2">
            <li>Thanh toán khi nhận hàng (COD), hoặc</li>
            <li>Thanh toán chuyển khoản trước qua tài khoản ngân hàng được cung cấp sau khi xác nhận đơn hàng.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">2. Thời gian xử lý và giao hàng</h2>
          <p className="mb-4">
            Mọi đơn hàng sẽ được xác nhận trong vòng <strong className="text-zinc-800">24 giờ</strong> kể từ khi đặt thành công trên website.
          </p>
          <p className="mb-4">Sau khi xác nhận, đơn hàng sẽ được xử lý và bàn giao cho đơn vị vận chuyển tương ứng.</p>
          <p className="font-semibold text-zinc-800 mb-2">Nguồn gốc &amp; kho hàng:</p>
          <p className="mb-4">
            Sản phẩm được nhập khẩu và phân phối từ nhiều quốc gia như Trung Quốc, Thái Lan, Hàn Quốc, Singapore, Mỹ và Việt Nam. Tùy theo từng sản phẩm, đơn hàng có thể được xuất từ:
          </p>
          <ul className="list-disc pl-5 space-y-2 mb-4">
            <li>Kho nội địa (Việt Nam), hoặc</li>
            <li>Kho quốc tế (thông qua đối tác logistics quốc tế).</li>
          </ul>
          <p className="font-semibold text-zinc-800 mb-2">Thời gian giao hàng dự kiến:</p>
          <ul className="list-disc pl-5 space-y-2 mb-4">
            <li>
              Từ <strong className="text-zinc-800">2 – 5 ngày làm việc</strong> đối với hàng có sẵn tại kho nội địa.
            </li>
            <li>
              Từ <strong className="text-zinc-800">6 – 12 ngày làm việc</strong> đối với hàng nhập khẩu hoặc giao từ kho quốc tế.
            </li>
          </ul>
          <p className="text-zinc-600">
            <strong className="text-zinc-800">Lưu ý:</strong> Thời gian giao hàng có thể thay đổi do yếu tố khách quan như điều kiện thời tiết, ngày lễ, giãn cách xã hội hoặc sự cố vận chuyển ngoài ý muốn.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">3. Phí vận chuyển</h2>
          <ul className="list-disc pl-5 space-y-2">
            <li>Phí vận chuyển được hiển thị rõ ràng tại bước thanh toán, tùy theo khu vực giao hàng và trọng lượng đơn hàng.</li>
            <li>
              <strong className="text-zinc-800">Miễn phí giao hàng</strong> cho đơn hàng từ <strong className="text-zinc-800">500.000đ</strong> trở lên (áp dụng toàn quốc).
            </li>
            <li>
              Đối với đơn hàng dưới 500.000đ, phí vận chuyển dao động từ <strong className="text-zinc-800">20.000đ – 35.000đ</strong>.
            </li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">4. Kiểm tra và nhận hàng</h2>
          <p className="mb-4">
            Khi nhận hàng, quý khách vui lòng kiểm tra tình trạng sản phẩm, số lượng, mẫu mã trước khi ký nhận.
          </p>
          <p className="mb-2">Nếu phát hiện hàng hóa:</p>
          <ul className="list-disc pl-5 space-y-2 mb-4">
            <li>Bị hư hỏng,</li>
            <li>Không đúng mẫu mã, kích cỡ, hoặc</li>
            <li>Thiếu sản phẩm trong đơn hàng,</li>
          </ul>
          <p>
            vui lòng từ chối nhận hàng và liên hệ ngay Hotline{' '}
            <a href="tel:0968659836" className="text-orange-600 underline hover:text-orange-700">
              0968 659 836
            </a>{' '}
            hoặc Email:{' '}
            <a href="mailto:phungvanhau10101985@gmail.com" className="text-orange-600 underline hover:text-orange-700">
              phungvanhau10101985@gmail.com
            </a>{' '}
            để được hỗ trợ kịp thời.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">5. Trách nhiệm đối với hàng hóa hư hại</h2>
          <p className="mb-4">
            Trong trường hợp hàng hóa bị hư hại trong quá trình vận chuyển, 188.COM.VN sẽ phối hợp cùng đơn vị vận chuyển để xác minh và xử lý theo{' '}
            <Link href="/info/doi-tra-hoan-tien" className="text-orange-600 underline hover:text-orange-700 font-medium">
              Chính sách Đổi trả &amp; Hoàn tiền
            </Link>
            .
          </p>
          <p>
            Khách hàng cần thông báo trong vòng <strong className="text-zinc-800">24 giờ</strong> kể từ thời điểm nhận hàng để được giải quyết nhanh chóng và đúng quy định.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">6. Liên hệ hỗ trợ</h2>
          <p className="font-semibold text-zinc-800 mb-3">Hộ Kinh Doanh Phùng Văn Hậu</p>
          <ul className="list-none pl-0 space-y-2">
            <li>
              <strong className="text-zinc-800">Địa chỉ:</strong> Xóm Buối, Thôn Vật Lại 3, Xã Vật Lại, Huyện Ba Vì, Thành phố Hà Nội
            </li>
            <li>
              <strong className="text-zinc-800">Hotline:</strong>{' '}
              <a href="tel:0968659836" className="text-orange-600 underline hover:text-orange-700">
                0968 659 836
              </a>{' '}
              (Giờ làm việc: 8h00 – 16h30, Thứ 2 – Thứ 7)
            </li>
            <li>
              <strong className="text-zinc-800">Email:</strong>{' '}
              <a href="mailto:hotro@188.com.vn" className="text-orange-600 underline hover:text-orange-700">
                hotro@188.com.vn
              </a>
            </li>
            <li>
              <strong className="text-zinc-800">Website:</strong>{' '}
              <a href="https://188.com.vn" className="text-orange-600 underline hover:text-orange-700" rel="noopener noreferrer">
                https://188.com.vn
              </a>
            </li>
          </ul>
          <p className="mt-6 text-zinc-700">
            Trân trọng,
            <br />
            Đại diện Hộ Kinh Doanh Phùng Văn Hậu
          </p>
          <p className="mt-4 text-sm text-zinc-500">© 2018 – 2026 188.COM.VN. Tất cả các quyền được bảo lưu.</p>
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
          <Link href="/info/lien-he" className="text-orange-700 underline font-medium hover:text-orange-800">
            Thông tin liên hệ
          </Link>
          ,{' '}
          <Link href="/info/huong-dan-mua-hang" className="text-orange-700 underline font-medium hover:text-orange-800">
            Hướng dẫn mua hàng
          </Link>
          ,{' '}
          <Link href="/info/chinh-sach-bao-mat" className="text-orange-700 underline font-medium hover:text-orange-800">
            Chính sách bảo mật
          </Link>
          .
        </p>
      </div>
    </InfoPageLayout>
  );
}
