import InfoPageLayout from '@/components/info/InfoPageLayout';
import Link from 'next/link';

export const metadata = {
  title: 'Nguồn gốc và Thương hiệu sản phẩm',
  description:
    'Về chúng tôi và chính sách minh bạch thông tin – nguồn gốc hàng hóa, thương hiệu tại 188.COM.VN.',
};

export default function NguonGocThuongHieuPage() {
  return (
    <InfoPageLayout title="Nguồn gốc và Thương hiệu sản phẩm">
      <p className="text-sm font-semibold uppercase tracking-wide text-zinc-500 mb-6">
        Về chúng tôi &amp; chính sách minh bạch thông tin
      </p>

      <div className="space-y-10 text-zinc-600">
        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">1. Giới thiệu</h2>
          <p className="mb-4">
            <strong className="text-zinc-800">188.COM.VN</strong> là website thương mại điện tử chính thức của Hộ Kinh Doanh Phùng Văn Hậu (Mã số đăng ký: 01Q8011025).
          </p>
          <p>
            Chúng tôi hoạt động với tư cách là nhà bán lẻ và phân phối sản phẩm thời trang, giày dép, túi ví và phụ kiện, cam kết mang đến cho khách hàng những sản phẩm chất lượng cùng trải nghiệm mua sắm đáng tin cậy.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">2. Nguồn gốc hàng hóa</h2>
          <p className="mb-4">
            Nhằm đáp ứng nhu cầu đa dạng về mẫu mã và xu hướng của khách hàng, chúng tôi hợp tác với nhiều đối tác cung ứng trong và ngoài nước, bao gồm các nhà sản xuất, nhà phân phối uy tín có đăng ký kinh doanh rõ ràng.
          </p>
          <p className="mb-4">
            Các sản phẩm được lựa chọn từ nhiều khu vực như Việt Nam, Nhật Bản, Hàn Quốc, Trung Quốc, Thái Lan, Mỹ và Úc, tùy theo từng dòng sản phẩm và xu hướng thị trường. Bên cạnh đó, chúng tôi cũng có thể đưa vào những bộ sưu tập độc quyền được tuyển chọn từ các quốc gia khác nhau nhằm mang đến nhiều lựa chọn phong phú cho khách hàng.
          </p>
          <p className="font-semibold text-zinc-800 mb-2">Cam kết minh bạch:</p>
          <p className="mb-4">Mỗi sản phẩm đều được quản lý bằng mã SKU riêng biệt để truy xuất thông tin.</p>
          <p className="font-semibold text-zinc-800 mb-2">Quy trình kiểm soát chất lượng:</p>
          <p>
            Tất cả sản phẩm, dù có nguồn gốc từ bất kỳ quốc gia nào, đều trải qua quy trình kiểm tra nghiêm ngặt về hình thức, chất liệu và độ hoàn thiện bởi đội ngũ của chúng tôi trước khi đóng gói và giao đến tay khách hàng. Chúng tôi chịu trách nhiệm cuối cùng về chất lượng sản phẩm được phân phối trên website.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">3. Thương hiệu &amp; Bản quyền</h2>
          <ul className="list-disc pl-5 space-y-2">
            <li>Chúng tôi là nhà bán lẻ độc lập.</li>
            <li>Các sản phẩm được bán trên website là hàng có sẵn trên thị trường (marketplace inventory).</li>
            <li>
              Chúng tôi không tuyên bố là đại diện chính thức, được ủy quyền hay có liên kết đặc biệt với bất kỳ thương hiệu thời trang nào được nhắc đến, trừ khi có ghi chú cụ thể.
            </li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">4. Cam kết với khách hàng</h2>
          <ul className="list-disc pl-5 space-y-2">
            <li>
              <strong className="text-zinc-800">KHÔNG</strong> kinh doanh hàng giả, hàng nhái, hàng vi phạm bản quyền.
            </li>
            <li>Hình ảnh và mô tả sản phẩm được chúng tôi tự chụp và biên soạn, phản ánh đúng thực tế.</li>
            <li>Thông tin sản phẩm được trình bày trung thực, dễ hiểu và cập nhật thường xuyên.</li>
            <li>
              Mọi thắc mắc về nguồn gốc, chất lượng sản phẩm, chúng tôi sẵn sàng cung cấp thông tin và giải đáp rõ ràng, nhanh chóng.
            </li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">5. Minh bạch &amp; Tuân thủ</h2>
          <p className="mb-4">Chúng tôi cam kết tuân thủ:</p>
          <ul className="list-disc pl-5 space-y-2">
            <li>Luật Bảo vệ quyền lợi người tiêu dùng Việt Nam</li>
            <li>Các quy định về minh bạch thông tin thương mại của Bộ Công Thương</li>
            <li>Chính sách quảng cáo và chất lượng của Google Merchant Center cùng các nền tảng đối tác khác</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">6. Thông tin liên hệ &amp; Trách nhiệm pháp lý</h2>
          <p className="mb-4">
            Mọi giao dịch trên website này đều do Hộ Kinh Doanh Phùng Văn Hậu chịu trách nhiệm trước pháp luật và khách hàng.
          </p>
          <ul className="list-none pl-0 space-y-2">
            <li>
              <strong className="text-zinc-800">Chủ sở hữu:</strong> Hộ Kinh Doanh Phùng Văn Hậu
            </li>
            <li>
              <strong className="text-zinc-800">Mã số đăng ký:</strong> 01Q8011025
            </li>
            <li>
              <strong className="text-zinc-800">Địa chỉ:</strong> Xóm Buối, Thôn Vật Lại 3, Xã Vật Lại, Huyện Ba Vì, Thành phố Hà Nội
            </li>
            <li>
              <strong className="text-zinc-800">Điện thoại:</strong>{' '}
              <a href="tel:0968659836" className="text-orange-600 underline hover:text-orange-700">
                0968 659 836
              </a>{' '}
              (Giờ làm việc: 8h00 – 16h30)
            </li>
            <li>
              <strong className="text-zinc-800">Email:</strong>{' '}
              <a href="mailto:hotro@188.com.vn" className="text-orange-600 underline hover:text-orange-700">
                hotro@188.com.vn
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
          <Link href="/info/chinh-sach-danh-gia" className="text-orange-700 underline font-medium hover:text-orange-800">
            Chính sách quản lý đánh giá và chất lượng sản phẩm
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
