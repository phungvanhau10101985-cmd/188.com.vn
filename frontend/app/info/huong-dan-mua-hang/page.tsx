import InfoPageLayout from '@/components/info/InfoPageLayout';
import Link from 'next/link';

export const metadata = {
  title: 'Hướng dẫn mua hàng - Điều kiện thanh toán',
  description: 'Hướng dẫn mua hàng, đặt cọc 30% và chuyển khoản tại 188.COM.VN.',
};

export default function HuongDanMuaHangPage() {
  return (
    <InfoPageLayout title="Hướng dẫn mua hàng - Điều kiện thanh toán">
      <p className="text-sm font-semibold uppercase tracking-wide text-zinc-500 mb-6">
        Hướng dẫn mua hàng và điều kiện thanh toán
      </p>

      <div className="space-y-4 text-zinc-600">
        <p>
          <strong className="text-zinc-800">188.COM.VN</strong> cam kết cung cấp sản phẩm{' '}
          <strong className="text-zinc-800">đúng mẫu, đúng size và đúng chất lượng</strong> theo thông tin mô tả, đảm bảo tương xứng với giá trị mà nhà sản xuất cung cấp.
        </p>
        <p>
          Trong trường hợp <strong className="text-zinc-800">sản phẩm giao không đúng cam kết hoặc có lỗi sản xuất</strong>, 188.COM.VN sẽ{' '}
          <strong className="text-zinc-800">gửi lại mẫu khác đúng mô tả</strong> hoặc <strong className="text-zinc-800">hoàn trả tiền đặt cọc</strong> cho khách hàng.
        </p>
        <p>
          Nếu <strong className="text-zinc-800">sản phẩm không vừa</strong>, chúng tôi <strong className="text-zinc-800">hỗ trợ đổi size 1 lần</strong> (không đổi mẫu).
        </p>
        <p>
          Do hàng hóa được <strong className="text-zinc-800">nhập khẩu từ nước ngoài</strong>, chi phí nhập hàng và vận chuyển cao, nên để đảm bảo quyền lợi hai bên và tránh việc hủy đơn khi hàng đang vận chuyển,{' '}
          <strong className="text-zinc-800">khách hàng cần thanh toán trước 30% giá trị đơn hàng</strong>. Phần <strong className="text-zinc-800">70% còn lại</strong> sẽ được{' '}
          <strong className="text-zinc-800">thanh toán khi nhận hàng</strong>.
        </p>
        <p>
          Khi chuyển khoản đặt cọc, <strong className="text-zinc-800">vui lòng ghi rõ số điện thoại của quý khách</strong> trong nội dung chuyển tiền để thuận tiện cho việc xác minh. 188.COM.VN sẽ{' '}
          <strong className="text-zinc-800">xác nhận đơn hàng thông qua số điện thoại</strong> ghi trong nội dung chuyển khoản.
        </p>
        <p>
          Sau khi nhận hàng, <strong className="text-zinc-800">rất mong quý khách đánh giá sản phẩm</strong> để chúng tôi không ngừng cải thiện chất lượng dịch vụ.
        </p>
        <p>
          188.COM.VN cam kết <strong className="text-zinc-800">loại bỏ những sản phẩm từ nhà cung cấp có điểm đánh giá trung bình dưới 4 sao</strong>, nhằm đảm bảo chất lượng tốt nhất cho khách hàng.
        </p>
        <p>
          Với <strong className="text-zinc-800">hơn 8 năm kinh nghiệm và uy tín trong lĩnh vực</strong>, cùng tinh thần cầu thị, lắng nghe ý kiến khách hàng, chúng tôi tin rằng sẽ mang lại sự hài lòng ngay cả với những khách hàng khó tính nhất.
        </p>
        <p>
          Sau khi đặt hàng trên website và được xác nhận, quý khách có thể <strong className="text-zinc-800">đặt cọc hoặc thanh toán bằng bất kỳ tài khoản ngân hàng nào</strong> thông qua{' '}
          <strong className="text-zinc-800">dịch vụ Internet Banking</strong>.
        </p>
      </div>

      <h2 className="text-lg font-semibold text-zinc-900 mt-10 mb-4">Các phương thức thanh toán</h2>
      <div className="grid gap-4 sm:grid-cols-1 md:grid-cols-3">
        <div className="p-4 bg-zinc-50 rounded-xl border border-zinc-100 text-zinc-600 text-sm space-y-1">
          <p className="font-semibold text-zinc-900">Vietcombank</p>
          <p>
            <strong className="text-zinc-800">Tên TK:</strong> PHÙNG VĂN HẬU
          </p>
          <p>
            <strong className="text-zinc-800">STK:</strong> 0451000289239
          </p>
          <p>Ngân hàng Vietcombank Chi nhánh Hà Nội</p>
        </div>
        <div className="p-4 bg-zinc-50 rounded-xl border border-zinc-100 text-zinc-600 text-sm space-y-1">
          <p className="font-semibold text-zinc-900">Viettinbank</p>
          <p>
            <strong className="text-zinc-800">Tên TK:</strong> PHÙNG VĂN HẬU
          </p>
          <p>
            <strong className="text-zinc-800">STK:</strong> 107000958284
          </p>
          <p>Ngân hàng Viettinbank Chi nhánh CN TAY HA NOI - HOI SO</p>
        </div>
        <div className="p-4 bg-zinc-50 rounded-xl border border-zinc-100 text-zinc-600 text-sm space-y-1">
          <p className="font-semibold text-zinc-900">Agribank</p>
          <p>
            <strong className="text-zinc-800">Tên TK:</strong> PHÙNG VĂN HẬU
          </p>
          <p>
            <strong className="text-zinc-800">STK:</strong> 3100205578049
          </p>
          <p>Agribank chi nhánh Từ Liêm</p>
        </div>
      </div>

      <div className="mt-8">
        <h3 className="text-base font-semibold text-zinc-900 mb-2">Thông tin cá nhân chủ tài khoản</h3>
        <p className="text-zinc-600 text-sm">
          Chủ tài khoản thu hộ đặt cọc là <strong className="text-zinc-800">PHÙNG VĂN HẬU</strong>, trùng với đại diện pháp lý đơn vị. Khi cần xác minh giao dịch hoặc đối chiếu thông tin, vui lòng liên hệ{' '}
          <a href="tel:0968659836" className="text-orange-600 underline hover:text-orange-700">
            0968 659 836
          </a>{' '}
          hoặc{' '}
          <a href="mailto:hotro@188.com.vn" className="text-orange-600 underline hover:text-orange-700">
            hotro@188.com.vn
          </a>
          .
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
          <Link href="/info/lien-he" className="text-orange-700 underline font-medium hover:text-orange-800">
            Thông tin liên hệ
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
