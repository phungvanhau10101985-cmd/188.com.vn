import InfoPageLayout from '@/components/info/InfoPageLayout';

export const metadata = {
  title: 'Thông tin đơn vị sở hữu website',
  description: 'Thông tin đơn vị sở hữu website 188.com.vn - Hộ Kinh Doanh Phùng Văn Hậu.',
};

export default function ThongTinDonViPage() {
  return (
    <InfoPageLayout title="Thông tin đơn vị sở hữu website 188.com.vn">
      <p className="lead text-zinc-600 font-medium mb-6 text-base">
        Website 188.com.vn thuộc quyền sở hữu và quản lý của <strong>Hộ Kinh Doanh Phùng Văn Hậu</strong>.
      </p>

      <div className="space-y-6">
        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-2">Giấy chứng nhận đăng ký hộ kinh doanh</h2>
          <p className="text-zinc-600">01Q8011025</p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-2">Địa chỉ</h2>
          <p className="text-zinc-600">
            Xóm Buối, Thôn Vật Lại 3, Xã Vật Lại, Huyện Ba Vì, Thành phố Hà Nội
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mb-2">Liên hệ</h2>
          <ul className="space-y-2 text-zinc-600">
            <li>
              <strong>Điện thoại:</strong> 0968 659 836
            </li>
            <li>
              <strong>Giờ làm việc:</strong> 8h00 – 16h30
            </li>
            <li>
              <strong>Email:</strong>{' '}
              <a href="mailto:hotro@188.com.vn">hotro@188.com.vn</a>
            </li>
          </ul>
        </section>

        <div className="mt-8 p-4 bg-orange-50 border border-orange-100 rounded-xl text-zinc-700 text-sm">
          Quý khách vui lòng liên hệ trước khi đến làm việc để được hỗ trợ và phục vụ tốt nhất.
        </div>
      </div>
    </InfoPageLayout>
  );
}
