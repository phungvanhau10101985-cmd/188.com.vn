import InfoPageLayout from '@/components/info/InfoPageLayout';
import { cdnUrl } from '@/lib/cdn-url';
import Image from 'next/image';
import Link from 'next/link';

export const metadata = {
  title: '188.COM.VN có uy tín không?',
  description:
    'Góc nhìn khách quan về uy tín 188.COM.VN: kinh nghiệm, đối tác, đánh giá và cam kết chất lượng.',
};

export default function UyTinPage() {
  return (
    <InfoPageLayout title="188.COM.VN có uy tín không?">
      <div className="space-y-6 text-zinc-600">
        <p>
          Công nghệ phát triển, mua hàng qua mạng là phương thức giao dịch phổ biến hiện nay. Khi mua hàng, vấn đề{' '}
          <strong className="text-zinc-800">lo lắng</strong> nhất là bên bán có uy tín hay không, bên bán có lừa đảo khách hàng hay không. Chúng tôi viết nội dung này để khách hàng có cái nhìn khách quan và những đánh giá khách quan về dịch vụ của chúng tôi.
        </p>
        <p className="text-zinc-700 font-medium">Để khách hàng dễ đọc, chúng tôi trình bày từng ý gạch đầu dòng.</p>

        <ul className="list-none pl-0 space-y-8">
          <li>
            <p className="font-semibold text-zinc-900 mb-3">— 188.com.vn đã hoạt động 5 năm</p>
            <div className="space-y-3 pl-0 sm:pl-4 border-l-2 border-orange-100 sm:ml-1">
              <p>
                Với 5 năm kinh nghiệm và phục vụ hơn 20 ngàn khách hàng, chúng tôi đã và đang ngày một hoàn thiện dịch vụ.
              </p>
              <p>
                Chúng tôi có hệ thống đối tác và tổng kho hàng tại nhiều quốc gia, hợp tác trực tiếp với các nhà sản xuất và thương hiệu uy tín trên toàn thế giới.
              </p>
              <p>
                Thông tin và hình ảnh sản phẩm trên website đều được cung cấp trực tiếp từ nhà sản xuất chính hãng. Một số đơn vị khác có thể sao chép hình ảnh của chúng tôi để bán sản phẩm kém chất lượng với giá rẻ hơn; tuy nhiên chất lượng thực tế sẽ tương xứng với mức giá đó.{' '}
                <strong className="text-zinc-800">188.COM.VN</strong> cam kết chỉ cung cấp sản phẩm chính hãng, đúng mô tả và được kiểm duyệt kỹ trước khi giao đến khách hàng.
              </p>
              <p>
                Với hơn 5 năm kinh nghiệm hoạt động, <strong className="text-zinc-800">188.COM.VN</strong> đã nhận được hàng nghìn phản hồi tích cực và đánh giá hài lòng từ khách hàng trên nhiều nền tảng khác nhau (mạng xã hội hoặc trên web), khẳng định uy tín và chất lượng dịch vụ mà chúng tôi mang lại.
              </p>
              <figure className="mt-6 rounded-xl border border-zinc-200 bg-zinc-50 p-3 shadow-sm">
                <Image
                  src={cdnUrl('/images/info/uy-tin-social-reviews.png')}
                  alt="Ảnh chụp màn hình khu vực đánh giá trên mạng xã hội: điểm trung bình và số lượng người đánh giá, kèm một số bình luận tích cực về 188.com.vn"
                  width={853}
                  height={636}
                  className="mx-auto h-auto w-full max-w-full rounded-lg"
                  sizes="(max-width: 768px) 100vw, 42rem"
                />
                <figcaption className="mt-3 text-center text-sm text-zinc-500">
                  Minh họa đánh giá công khai trên nền tảng mạng xã hội — phản hồi thực tế từ khách hàng.
                </figcaption>
              </figure>
            </div>
          </li>
          <li>
            <p>
              <span className="font-semibold text-zinc-900">— </span>
              Sản phẩm của chúng tôi được những khách hàng đã mua hàng đánh giá trực tiếp, khách quan; những sản phẩm có điểm đánh giá thấp chúng tôi sẽ gỡ bỏ khỏi website để tránh khách hàng mua phải hàng kém chất lượng.
            </p>
            <figure className="mt-6 rounded-xl border border-zinc-200 bg-zinc-50 p-3 shadow-sm">
              <Image
                src={cdnUrl('/images/info/uy-tin-review-modal.png')}
                alt="Cửa sổ đánh giá sản phẩm trên website: chọn sao, nhận xét, tải tối đa 3 hình và nút gửi; có dòng cam kết ngừng hợp tác nhà cung cấp kém chất lượng"
                width={622}
                height={468}
                className="mx-auto h-auto w-full max-w-md rounded-lg"
                sizes="(max-width: 768px) 100vw, 28rem"
              />
              <figcaption className="mt-3 text-center text-sm text-zinc-500">
                Hệ thống đánh giá sau mua hàng trên website — khuyến khích nhận xét trung thực, gắn với chất lượng và uy tín.
              </figcaption>
            </figure>
          </li>
          <li>
            <p>
              <span className="font-semibold text-zinc-900">— </span>
              Thông tin người bán hàng, thông tin cá nhân chính chủ, hỗ trợ đổi size, thông tin đổi trả hàng{' '}
              <strong className="text-zinc-800">rõ ràng</strong>, <strong className="text-zinc-800">thông tin địa chỉ rõ ràng</strong>.
            </p>
          </li>
        </ul>

        <p className="pt-2 text-zinc-700">
          Với tất cả những yếu tố trên, chúng tôi tin khách hàng đã có câu trả lời cho mình về sự uy tín của chúng tôi.{' '}
          <strong className="text-zinc-800">Cảm ơn</strong> quý khách đã đọc và luôn đóng góp ý kiến để chúng tôi hoàn thiện hơn và mang những sản phẩm, dịch vụ tốt nhất để phục vụ khách hàng.
        </p>
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
          <Link href="/info/thong-tin-don-vi" className="text-orange-700 underline font-medium hover:text-orange-800">
            Thông tin đơn vị sở hữu website
          </Link>
          ,{' '}
          <Link href="/info/chinh-sach-danh-gia" className="text-orange-700 underline font-medium hover:text-orange-800">
            Chính sách quản lý đánh giá
          </Link>
          ,{' '}
          <Link href="/info/doi-tra-hoan-tien" className="text-orange-700 underline font-medium hover:text-orange-800">
            Đổi trả &amp; Hoàn tiền
          </Link>
          ,{' '}
          <Link href="/info/lien-he" className="text-orange-700 underline font-medium hover:text-orange-800">
            Liên hệ
          </Link>
          .
        </p>
      </div>
    </InfoPageLayout>
  );
}
