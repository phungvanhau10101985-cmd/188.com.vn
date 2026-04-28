import InfoPageLayout from '@/components/info/InfoPageLayout';
import Link from 'next/link';

export const metadata = {
  title: 'Điều khoản sử dụng',
  description: 'Điều khoản sử dụng website 188.COM.VN – quyền, trách nhiệm và chính sách liên quan.',
};

export default function DieuKhoanSuDungPage() {
  return (
    <InfoPageLayout title="Điều khoản sử dụng">
      <p className="text-sm font-semibold uppercase tracking-wide text-zinc-500 mb-6">
        Điều khoản sử dụng – 188.COM.VN
      </p>

      <div className="space-y-10 text-zinc-600">
        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">1. Giới thiệu</h2>
          <p className="mb-4">
            Chào mừng quý khách đến với website <strong className="text-zinc-800">188.com.vn</strong>, thuộc quyền sở hữu và quản lý của Hộ Kinh Doanh Phùng Văn Hậu.
          </p>
          <p>
            Khi truy cập và sử dụng website này, quý khách đồng ý tuân thủ các Điều khoản sử dụng dưới đây. Vui lòng đọc kỹ trước khi mua hàng hoặc sử dụng dịch vụ.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">2. Quyền và trách nhiệm của khách hàng</h2>
          <ul className="list-disc pl-5 space-y-2">
            <li>Khách hàng có quyền truy cập, tham khảo và đặt mua sản phẩm được đăng bán trên website.</li>
            <li>Mọi thông tin cá nhân cung cấp khi mua hàng phải chính xác, trung thực và đầy đủ.</li>
            <li>
              Không được sử dụng website vào các mục đích gian lận, gây rối, phá hoại hệ thống hoặc vi phạm pháp luật Việt Nam.
            </li>
            <li>Khách hàng có trách nhiệm bảo mật thông tin tài khoản, mật khẩu (nếu có).</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">3. Quyền và trách nhiệm của 188.com.vn</h2>
          <ul className="list-disc pl-5 space-y-2">
            <li>
              188.com.vn có quyền thay đổi, cập nhật hoặc ngừng cung cấp dịch vụ mà không cần thông báo trước trong một số trường hợp cần thiết.
            </li>
            <li>Cam kết cung cấp thông tin sản phẩm, giá bán, chương trình khuyến mãi chính xác và minh bạch.</li>
            <li>
              Bảo mật thông tin khách hàng theo{' '}
              <Link href="/info/chinh-sach-bao-mat" className="text-orange-600 underline hover:text-orange-700 font-medium">
                Chính sách bảo mật
              </Link>{' '}
              được công bố trên website.
            </li>
            <li>Không chịu trách nhiệm với các thiệt hại phát sinh do lỗi khách quan (sự cố đường truyền, lỗi bên thứ ba...).</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">4. Chính sách giá và thanh toán</h2>
          <ul className="list-disc pl-5 space-y-2">
            <li>Giá niêm yết trên website là giá bán lẻ đã bao gồm thuế (nếu có).</li>
            <li>
              Phương thức thanh toán: Đặt cọc, Tiền mặt khi nhận hàng (COD), chuyển khoản ngân hàng, hoặc thanh toán qua các cổng thanh toán được hỗ trợ.
            </li>
            <li>Trong trường hợp có sai sót hiển thị giá, 188.com.vn sẽ liên hệ khách hàng để xác nhận lại trước khi giao hàng.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">5. Chính sách giao hàng và đổi trả</h2>
          <ul className="list-disc pl-5 space-y-2">
            <li>
              Thời gian và phương thức giao hàng được mô tả chi tiết trong{' '}
              <Link href="/info/chinh-sach-giao-hang" className="text-orange-600 underline hover:text-orange-700 font-medium">
                Chính sách giao hàng
              </Link>
              .
            </li>
            <li>
              Việc đổi trả hoặc hoàn tiền được thực hiện theo{' '}
              <Link href="/info/doi-tra-hoan-tien" className="text-orange-600 underline hover:text-orange-700 font-medium">
                Chính sách đổi trả &amp; hoàn tiền
              </Link>{' '}
              đăng tải công khai trên website.
            </li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">6. Quyền sở hữu trí tuệ</h2>
          <ul className="list-disc pl-5 space-y-2">
            <li>Mọi nội dung, hình ảnh, thiết kế, logo và dữ liệu trên 188.com.vn đều thuộc quyền sở hữu của Hộ Kinh Doanh Phùng Văn Hậu.</li>
            <li>
              Nghiêm cấm sao chép, chỉnh sửa, phân phối hoặc sử dụng trái phép dưới bất kỳ hình thức nào nếu chưa được sự đồng ý bằng văn bản.
            </li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">7. Giới hạn trách nhiệm</h2>
          <p>
            188.com.vn không chịu trách nhiệm cho bất kỳ thiệt hại trực tiếp hoặc gián tiếp nào phát sinh từ việc sử dụng, truy cập hoặc không thể truy cập vào website, trừ khi pháp luật có quy định khác.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">8. Luật áp dụng và giải quyết tranh chấp</h2>
          <p className="mb-4">Các điều khoản này được điều chỉnh theo pháp luật nước Cộng hòa Xã hội Chủ nghĩa Việt Nam.</p>
          <p>
            Mọi tranh chấp sẽ được ưu tiên giải quyết thông qua thương lượng. Nếu không đạt được thỏa thuận, tranh chấp sẽ được đưa ra Tòa án có thẩm quyền tại Hà Nội.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">9. Thông tin liên hệ</h2>
          <p className="font-semibold text-zinc-800 mb-3">Hộ Kinh Doanh Phùng Văn Hậu</p>
          <ul className="list-none pl-0 space-y-2">
            <li>
              <strong className="text-zinc-800">Địa chỉ:</strong> Xóm Buối, Thôn Vật Lại 3, Xã Vật Lại, Huyện Ba Vì, Hà Nội
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
          <Link href="/info/huong-dan-mua-hang" className="text-orange-700 underline font-medium hover:text-orange-800">
            Hướng dẫn mua hàng
          </Link>
          .
        </p>
      </div>
    </InfoPageLayout>
  );
}
