import InfoPageLayout from '@/components/info/InfoPageLayout';
import Link from 'next/link';

export const metadata = {
  title: 'Thông tin liên hệ',
  description: 'Liên hệ chính thức 188.COM.VN - Địa chỉ, hotline, email, kênh mạng xã hội.',
};

export default function LienHePage() {
  return (
    <InfoPageLayout title="Thông tin liên hệ">
      <p className="text-sm font-semibold uppercase tracking-wide text-zinc-500 mb-6">Thông tin liên hệ – 188.COM.VN</p>

      <section className="space-y-8 text-zinc-600">
        <div>
          <h2 className="text-lg font-semibold text-zinc-900">1. Thông tin đơn vị sở hữu website</h2>
          <ul className="mt-4 space-y-2 list-none pl-0">
            <li>
              <strong className="text-zinc-800">Tên đơn vị:</strong> Hộ Kinh Doanh Phùng Văn Hậu
            </li>
            <li>
              <strong className="text-zinc-800">Tên website:</strong> 188.COM.VN
            </li>
            <li>
              <strong className="text-zinc-800">Giấy chứng nhận đăng ký Hộ Kinh Doanh số:</strong> 01Q8011025 – do UBND Huyện Ba Vì, Thành phố Hà Nội cấp.
            </li>
            <li>
              <strong className="text-zinc-800">Người đại diện:</strong> Ông Phùng Văn Hậu – Chủ hộ kinh doanh.
            </li>
            <li>
              <strong className="text-zinc-800">Lĩnh vực hoạt động:</strong> Bán lẻ sản phẩm thời trang, giày dép, phụ kiện và hàng tiêu dùng qua mạng Internet.
            </li>
          </ul>
        </div>

        <div>
          <h2 className="text-lg font-semibold text-zinc-900">2. Thông tin liên hệ chính thức</h2>
          <div className="mt-4 space-y-3">
            <p>
              <strong className="text-zinc-800">Địa chỉ trụ sở:</strong>
              <br />
              Xóm Buối, Thôn Vật Lại 3, Xã Vật Lại, Huyện Ba Vì, Thành phố Hà Nội, Việt Nam.
            </p>
            <p>
              <strong className="text-zinc-800">Hotline:</strong>{' '}
              <a href="tel:0968659836" className="text-orange-600 underline hover:text-orange-700">
                0968 659 836
              </a>
            </p>
            <p>
              <strong className="text-zinc-800">Email:</strong>{' '}
              <a href="mailto:hotro@188.com.vn" className="text-orange-600 underline hover:text-orange-700">
                hotro@188.com.vn
              </a>
            </p>
            <p>
              <strong className="text-zinc-800">Website:</strong>{' '}
              <a href="https://188.com.vn/" className="text-orange-600 underline hover:text-orange-700 break-all" rel="noopener noreferrer">
                https://188.com.vn
              </a>
            </p>
            <p>
              <strong className="text-zinc-800">Thời gian làm việc:</strong>
              <br />
              Từ 8h00 – 16h30, Thứ Hai đến Thứ Bảy (nghỉ Chủ Nhật và ngày lễ).
            </p>
          </div>
        </div>

        <div>
          <h2 className="text-lg font-semibold text-zinc-900">3. Hỗ trợ khách hàng</h2>
          <p className="mt-4">Đội ngũ chăm sóc khách hàng của chúng tôi luôn sẵn sàng hỗ trợ:</p>
          <ul className="mt-3 list-disc pl-6 space-y-2">
            <li>Giải đáp thắc mắc về sản phẩm, đơn hàng, giao hàng và đổi trả.</li>
            <li>
              Tiếp nhận và xử lý phản hồi, khiếu nại trong vòng <strong className="text-zinc-800">24 giờ làm việc</strong>.
            </li>
            <li>Hướng dẫn các thủ tục bảo hành, đổi trả hoặc hoàn tiền (nếu có).</li>
          </ul>
          <p className="mt-4">
            Khách hàng vui lòng <strong className="text-zinc-800">liên hệ trước khi đến trực tiếp</strong> để được phục vụ nhanh và đúng bộ phận.
          </p>
        </div>

        <div>
          <h2 className="text-lg font-semibold text-zinc-900">4. Kênh kết nối chính thức</h2>
          <ul className="mt-4 list-disc pl-6 space-y-2">
            <li>
              <strong className="text-zinc-800">Fanpage Facebook:</strong>{' '}
              <a
                href="https://facebook.com/188.com.vn"
                className="text-orange-600 underline hover:text-orange-700 break-all"
                rel="noopener noreferrer"
              >
                facebook.com/188.com.vn
              </a>
            </li>
            <li>
              <strong className="text-zinc-800">Zalo Official Account:</strong>{' '}
              <a
                href="https://zalo.me/1714121106420519241"
                className="text-orange-600 underline hover:text-orange-700 break-all"
                rel="noopener noreferrer"
              >
                https://zalo.me/1714121106420519241
              </a>
            </li>
            <li>
              <strong className="text-zinc-800">Email CSKH:</strong>{' '}
              <a href="mailto:hotro@188.com.vn" className="text-orange-600 underline hover:text-orange-700">
                hotro@188.com.vn
              </a>
            </li>
          </ul>
        </div>

        <div>
          <h2 className="text-lg font-semibold text-zinc-900">5. Cam kết minh bạch</h2>
          <p className="mt-4">188.COM.VN cam kết:</p>
          <ul className="mt-3 list-disc pl-6 space-y-2">
            <li>Cung cấp thông tin liên hệ rõ ràng, minh bạch và có thể xác minh.</li>
            <li>Mọi giao dịch, khiếu nại và hỗ trợ được thực hiện qua các kênh chính thức nêu trên.</li>
            <li>Không sử dụng số điện thoại, email hoặc trang mạng xã hội giả mạo dưới danh nghĩa 188.COM.VN.</li>
          </ul>
        </div>
      </section>

      <div className="mt-10 pt-6 border-t border-zinc-200 text-zinc-600 text-sm space-y-2">
        <p className="font-semibold text-zinc-900">Trân trọng,</p>
        <p className="font-medium text-zinc-800">Hộ Kinh Doanh Phùng Văn Hậu</p>
        <p>
          <strong className="text-zinc-800">Website:</strong>{' '}
          <a href="https://188.com.vn/" className="text-orange-600 underline hover:text-orange-700" rel="noopener noreferrer">
            https://188.com.vn
          </a>
        </p>
        <p className="text-zinc-500">© 2018 – 2025 188.COM.VN. All rights reserved.</p>
      </div>

      <div className="mt-8 p-4 bg-orange-50 border border-orange-100 rounded-xl text-zinc-700 text-sm">
        <p>
          Xem thêm{' '}
          <Link href="/info/thong-tin-don-vi" className="text-orange-700 underline font-medium hover:text-orange-800">
            Thông tin đơn vị sở hữu website
          </Link>
          .
        </p>
        <p className="mt-2 italic text-zinc-600">
          Quý khách vui lòng liên hệ trước khi đến làm việc để được hỗ trợ và phục vụ tốt nhất.
        </p>
      </div>
    </InfoPageLayout>
  );
}
