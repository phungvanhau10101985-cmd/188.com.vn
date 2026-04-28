import InfoPageLayout from '@/components/info/InfoPageLayout';
import Link from 'next/link';

export const metadata = {
  title: 'Giới thiệu về chúng tôi – 188.COM.VN',
  description:
    'Giới thiệu 188.COM.VN: tầm nhìn, sứ mệnh, nguồn gốc sản phẩm, chính sách khách hàng và thông tin pháp lý.',
};

export default function GioiThieuPage() {
  return (
    <InfoPageLayout title="Giới thiệu về chúng tôi – 188.com.vn">
      <p className="text-sm font-semibold uppercase tracking-wide text-zinc-500 mb-6">
        Giới thiệu về chúng tôi – 188.COM.VN
      </p>

      <div className="space-y-10 text-zinc-600">
        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">1. Giới thiệu chung</h2>
          <p className="mb-4">
            <strong className="text-zinc-800">188.COM.VN</strong> là website thương mại điện tử chuyên cung cấp các sản phẩm thời trang, giày dép, túi ví, phụ kiện và đồ dùng công nghệ, được chọn lọc từ nhiều nhà sản xuất và đối tác uy tín trong và ngoài nước.
          </p>
          <p className="mb-4">
            Chúng tôi hoạt động dưới hình thức Hộ Kinh Doanh có đăng ký hợp pháp, chịu trách nhiệm hoàn toàn về chất lượng sản phẩm và dịch vụ bán hàng.
          </p>
          <p>
            Mục tiêu của chúng tôi là mang đến cho khách hàng trải nghiệm mua sắm trực tuyến <strong className="text-zinc-800">an toàn, minh bạch, tiện lợi và giá hợp lý</strong>.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">2. Tầm nhìn và Sứ mệnh</h2>
          <p className="mb-4">
            <strong className="text-zinc-800">Tầm nhìn:</strong> Trở thành một trong những địa chỉ mua sắm thời trang trực tuyến đáng tin cậy nhất tại Việt Nam, với cam kết minh bạch, chất lượng và phục vụ tận tâm.
          </p>
          <p className="mb-4">
            <strong className="text-zinc-800">Sứ mệnh:</strong> Mang đến những sản phẩm tốt nhất với giá trị thực, dịch vụ chăm sóc chuyên nghiệp, và luôn lắng nghe phản hồi để hoàn thiện mỗi ngày.
          </p>
          <blockquote className="border-l-4 border-orange-200 pl-4 italic text-zinc-700">
            Uy tín không đến từ lời nói – mà từ trải nghiệm thực tế của khách hàng.
          </blockquote>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">3. Nguồn gốc và Thương hiệu sản phẩm</h2>
          <p className="mb-4">
            Sản phẩm tại 188.COM.VN được nhập từ các nhà máy, xưởng sản xuất hoặc kho thương mại quốc tế tại: Trung Quốc, Việt Nam, Thái Lan, Hàn Quốc, Singapore, Mỹ.
          </p>
          <p className="mb-4">Mỗi sản phẩm đều có mã SKU riêng để quản lý minh bạch và đối chiếu khi cần thiết.</p>
          <p className="mb-4">Chúng tôi không tuyên bố sở hữu bất kỳ thương hiệu quốc tế nào.</p>
          <p className="mb-4">
            <strong className="text-zinc-800">188.COM.VN</strong> đóng vai trò đơn vị phân phối hoặc bán lẻ, hoạt động theo hợp đồng và nguồn cung hợp pháp.
          </p>
          <p className="font-semibold text-zinc-800 mb-2">Cam kết:</p>
          <ul className="list-disc pl-5 space-y-2">
            <li>Không kinh doanh hàng giả, hàng nhái, hàng kém chất lượng.</li>
            <li>Hình ảnh và mô tả sản phẩm phản ánh đúng thực tế.</li>
            <li>
              Nếu sản phẩm không đúng mô tả, khách hàng được đổi trả theo{' '}
              <Link href="/info/doi-tra-hoan-tien" className="text-orange-600 underline hover:text-orange-700 font-medium">
                chính sách đổi trả &amp; hoàn tiền
              </Link>
              .
            </li>
            <li>Xuất xứ hàng hóa minh bạch: hiển thị hoặc cung cấp khi khách hàng yêu cầu.</li>
          </ul>
          <p className="mt-4">
            Xem thêm{' '}
            <Link href="/info/nguon-goc-thuong-hieu" className="text-orange-600 underline hover:text-orange-700 font-medium">
              Nguồn gốc và Thương hiệu sản phẩm
            </Link>
            .
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">4. Chính sách và Dịch vụ khách hàng</h2>
          <ul className="list-disc pl-5 space-y-3">
            <li>
              <strong className="text-zinc-800">Đổi trả linh hoạt:</strong> Trong vòng 7 ngày kể từ khi nhận hàng nếu sản phẩm bị lỗi hoặc không đúng mô tả. Chi tiết:{' '}
              <Link href="/info/doi-tra-hoan-tien" className="text-orange-600 underline hover:text-orange-700">
                Đổi trả &amp; Hoàn tiền
              </Link>
              .
            </li>
            <li>
              <strong className="text-zinc-800">Giao hàng nhanh toàn quốc:</strong> Miễn phí vận chuyển cho đơn hàng từ 500.000 đồng. Chi tiết:{' '}
              <Link href="/info/chinh-sach-giao-hang" className="text-orange-600 underline hover:text-orange-700">
                Chính sách giao hàng
              </Link>
              .
            </li>
            <li>
              <strong className="text-zinc-800">Hỗ trợ tư vấn và chăm sóc khách hàng:</strong>
              <ul className="mt-2 list-none pl-0 space-y-1">
                <li>
                  Hotline:{' '}
                  <a href="tel:0968659836" className="text-orange-600 underline hover:text-orange-700">
                    0968 659 836
                  </a>{' '}
                  (8h00 – 16h30, Thứ 2 – Thứ 7)
                </li>
                <li>
                  Email:{' '}
                  <a href="mailto:phungvanhau10101985@gmail.com" className="text-orange-600 underline hover:text-orange-700">
                    phungvanhau10101985@gmail.com
                  </a>
                </li>
              </ul>
            </li>
          </ul>
          <p className="mt-4">
            Chúng tôi luôn nỗ lực phản hồi mọi yêu cầu và khiếu nại trong vòng <strong className="text-zinc-800">24 giờ làm việc</strong>, đảm bảo quyền lợi cao nhất cho khách hàng.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">5. Minh bạch thương hiệu và tuân thủ pháp luật</h2>
          <p className="mb-4">188.COM.VN tuân thủ nghiêm túc các quy định sau:</p>
          <ul className="list-disc pl-5 space-y-2">
            <li>Luật Bảo Vệ Quyền Lợi Người Tiêu Dùng (2023), có hiệu lực từ 01/07/2024.</li>
            <li>Chính sách minh bạch thông tin thương mại của Bộ Công Thương.</li>
            <li>Chính sách quảng cáo và trình bày sản phẩm của Google Merchant và Meta Commerce.</li>
            <li>
              Sử dụng giao thức bảo mật SSL (<strong className="text-zinc-800">https://</strong>) và các tiêu chuẩn kỹ thuật nhằm bảo vệ dữ liệu khách hàng.
            </li>
          </ul>
          <p className="mt-4">
            Chúng tôi cam kết không sử dụng hình ảnh, thương hiệu hoặc mô tả có thể gây hiểu lầm cho người tiêu dùng. Xem{' '}
            <Link href="/info/chinh-sach-bao-mat" className="text-orange-600 underline hover:text-orange-700 font-medium">
              Chính sách bảo mật
            </Link>
            .
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">6. Đánh giá và Uy tín thương hiệu</h2>
          <ul className="list-disc pl-5 space-y-2 mb-4">
            <li>188.COM.VN đã phục vụ hơn 20.000 khách hàng trên toàn quốc.</li>
            <li>Nhận được hàng chục nghìn phản hồi tích cực trên website, Facebook, Zalo và các kênh đối tác.</li>
            <li>Được đánh giá cao về tốc độ giao hàng, độ chính xác mô tả và thái độ phục vụ.</li>
          </ul>
          <blockquote className="border-l-4 border-orange-200 pl-4 italic text-zinc-700">
            Sự hài lòng của khách hàng là thước đo thành công của chúng tôi.
          </blockquote>
          <p className="mt-4">
            Tham khảo thêm{' '}
            <Link href="/info/uy-tin" className="text-orange-600 underline hover:text-orange-700 font-medium">
              188.COM.VN có uy tín không?
            </Link>{' '}
            và{' '}
            <Link href="/info/chinh-sach-danh-gia" className="text-orange-600 underline hover:text-orange-700 font-medium">
              Chính sách quản lý đánh giá
            </Link>
            .
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">7. Thông tin pháp lý và liên hệ chính thức</h2>
          <p className="font-semibold text-zinc-800 mb-3">Đơn vị sở hữu website: Hộ Kinh Doanh Phùng Văn Hậu</p>
          <ul className="list-none pl-0 space-y-2">
            <li>
              <strong className="text-zinc-800">Giấy chứng nhận đăng ký Hộ Kinh Doanh số:</strong> 01Q8011025
            </li>
            <li>
              <strong className="text-zinc-800">Địa chỉ:</strong> Xóm Buối, Thôn Vật Lại 3, Xã Vật Lại, Huyện Ba Vì, Thành phố Hà Nội
            </li>
            <li>
              <strong className="text-zinc-800">Điện thoại:</strong>{' '}
              <a href="tel:0968659836" className="text-orange-600 underline hover:text-orange-700">
                0968 659 836
              </a>
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
            <li>
              <strong className="text-zinc-800">Người đại diện:</strong> Phùng Văn Hậu
            </li>
            <li>
              <strong className="text-zinc-800">Thời gian làm việc:</strong> 8h00 – 16h30 (Thứ 2 – Thứ 7)
            </li>
          </ul>
          <p className="mt-4">
            Website 188.COM.VN thuộc quyền sở hữu và quản lý hợp pháp của Hộ Kinh Doanh Phùng Văn Hậu, đã đăng ký hoạt động thương mại điện tử theo quy định của Bộ Công Thương Việt Nam.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">8. Kết nối và đồng hành</h2>
          <p className="mb-4">
            Hãy theo dõi <strong className="text-zinc-800">188.COM.VN</strong> trên các kênh chính thức để cập nhật sản phẩm mới và ưu đãi:
          </p>
          <ul className="list-none pl-0 space-y-2">
            <li>
              <strong className="text-zinc-800">Facebook:</strong>{' '}
              <a
                href="https://www.facebook.com/188.com.vn"
                className="text-orange-600 underline hover:text-orange-700"
                rel="noopener noreferrer"
              >
                facebook.com/188.com.vn
              </a>
            </li>
            <li>
              <strong className="text-zinc-800">Zalo Official Account:</strong>{' '}
              <a
                href="https://zalo.me/1714121106420519241"
                className="text-orange-600 underline hover:text-orange-700"
                rel="noopener noreferrer"
              >
                https://zalo.me/1714121106420519241
              </a>
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
          <Link href="/info/lien-he" className="text-orange-700 underline font-medium hover:text-orange-800">
            Thông tin liên hệ
          </Link>
          ,{' '}
          <Link href="/info/thong-tin-don-vi" className="text-orange-700 underline font-medium hover:text-orange-800">
            Thông tin đơn vị sở hữu website
          </Link>
          ,{' '}
          <Link href="/info/huong-dan-mua-hang" className="text-orange-700 underline font-medium hover:text-orange-800">
            Hướng dẫn mua hàng
          </Link>
          .
        </p>
      </div>
    </InfoPageLayout>
  );
}
