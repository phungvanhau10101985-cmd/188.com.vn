import InfoPageLayout from '@/components/info/InfoPageLayout';
import Link from 'next/link';

export const metadata = {
  title: 'Chính sách quản lý đánh giá và quản lý chất lượng sản phẩm',
  description:
    'Chính sách quản lý đánh giá và chất lượng sản phẩm – 188.COM.VN: đánh giá thật, kiểm soát chất lượng, liên hệ.',
};

export default function ChinhSachDanhGiaPage() {
  return (
    <InfoPageLayout title="Chính sách quản lý đánh giá và quản lý chất lượng sản phẩm">
      <p className="text-sm font-semibold uppercase tracking-wide text-zinc-500 mb-6">
        Chính sách quản lý đánh giá và quản lý chất lượng sản phẩm – 188.COM.VN
      </p>

      <div className="space-y-10 text-zinc-600">
        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">1. Quản lý đánh giá sản phẩm</h2>
          <ul className="list-disc pl-5 space-y-3">
            <li>Chỉ khách hàng đã mua hàng mới có quyền đánh giá sản phẩm. Tất cả đánh giá trên website đều là phản hồi thật từ khách hàng.</li>
            <li>Chúng tôi không chỉnh sửa nội dung đánh giá của khách hàng.</li>
            <li>
              Các đánh giá sai sự thật, spam hoặc không liên quan đến sản phẩm có thể bị hệ thống ẩn hoặc xóa để bảo đảm tính trung thực.
            </li>
            <li>
              Những phản hồi đúng thực tế – dù tích cực hay tiêu cực – đều được giữ lại để giúp khách hàng khác có góc nhìn khách quan hơn khi mua sắm.
            </li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">2. Quản lý chất lượng sản phẩm</h2>
          <ul className="list-disc pl-5 space-y-3">
            <li>
              <strong className="text-zinc-800">188.COM.VN</strong> chỉ kinh doanh sản phẩm chính hãng, đúng hình – đúng mẫu – đúng mô tả.
            </li>
            <li>Những sản phẩm kém chất lượng hoặc nhận nhiều đánh giá không tích cực sẽ được gỡ bỏ khỏi hệ thống.</li>
            <li>
              Chúng tôi thường xuyên rà soát chất lượng sản phẩm, loại bỏ các mặt hàng không đạt chuẩn để mang đến trải nghiệm mua hàng tốt nhất cho khách hàng.
            </li>
          </ul>
          <p className="mt-4">
            Xem thêm{' '}
            <Link href="/info/doi-tra-hoan-tien" className="text-orange-600 underline hover:text-orange-700 font-medium">
              Đổi trả &amp; Hoàn tiền
            </Link>
            ,{' '}
            <Link href="/info/nguon-goc-thuong-hieu" className="text-orange-600 underline hover:text-orange-700 font-medium">
              Nguồn gốc và Thương hiệu sản phẩm
            </Link>
            .
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">3. Cập nhật và liên hệ</h2>
          <p className="mb-4">
            Chính sách này được cập nhật định kỳ để phù hợp với quy định pháp luật và tiêu chuẩn thương mại điện tử.
          </p>
          <p>
            Nếu có thắc mắc hoặc phản ánh về nội dung đánh giá, vui lòng liên hệ qua email{' '}
            <a href="mailto:phungvanhau10101985@gmail.com" className="text-orange-600 underline hover:text-orange-700">
              phungvanhau10101985@gmail.com
            </a>{' '}
            hoặc số điện thoại{' '}
            <a href="tel:0968659836" className="text-orange-600 underline hover:text-orange-700">
              0968 659 836
            </a>
            .
          </p>
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
          <Link href="/info/uy-tin" className="text-orange-700 underline font-medium hover:text-orange-800">
            188.COM.VN có uy tín không?
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
