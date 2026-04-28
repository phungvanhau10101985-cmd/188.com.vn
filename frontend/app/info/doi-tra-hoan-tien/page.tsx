import InfoPageLayout from '@/components/info/InfoPageLayout';

export const metadata = {
  title: 'Đổi trả & Hoàn tiền',
  description: 'Chính sách đổi trả và hoàn tiền tại 188.com.vn.',
};

export default function DoiTraHoanTienPage() {
  return (
    <InfoPageLayout title="Đổi trả & Hoàn tiền">
      <p className="text-sm font-semibold uppercase tracking-wide text-zinc-500 mb-2">Chính sách đổi trả và hoàn tiền</p>
      <p className="lead text-zinc-600 mb-6 text-base">
        Cảm ơn quý khách đã tin tưởng và mua hàng tại <strong className="text-zinc-800">188.COM.VN</strong>. Khi quý khách mua hàng trên website hoặc các kênh chính thức (Facebook, Zalo…), quý khách được xem là đã đọc và đồng ý với các quy định về đổi trả – hoàn tiền dưới đây.
      </p>

      <section className="space-y-6">
        <div>
          <h2 className="text-lg font-semibold text-zinc-900">1. Chính sách trả hàng – Hoàn tiền</h2>
          <div className="mt-4 space-y-4 text-zinc-600">
            <div>
              <h3 className="text-base font-semibold text-zinc-800 mb-2">1.1. Các trường hợp được trả hàng hoàn tiền</h3>
              <ul className="list-disc pl-6 space-y-2">
                <li>
                  Sản phẩm bị lỗi kỹ thuật, hư hỏng hoặc không đúng mô tả, sai mẫu, sai màu, sai size so với thông tin trên website.
                </li>
                <li>
                  Trường hợp khách hàng đã nhận hàng đúng mô tả nhưng muốn đổi mẫu hoặc không còn nhu cầu, vui lòng áp dụng theo chính sách đổi hàng (Mục 2).
                </li>
              </ul>
            </div>
            <div>
              <h3 className="text-base font-semibold text-zinc-800 mb-2">1.2. Quy trình và thời gian xử lý hoàn tiền</h3>
              <ul className="list-disc pl-6 space-y-2">
                <li>
                  Sau khi 188.COM.VN nhận và kiểm tra sản phẩm đủ điều kiện hoàn tiền, khoản hoàn sẽ được xử lý trong vòng <strong className="text-zinc-800">03 – 07 ngày làm việc</strong>.
                </li>
                <li>
                  Tiền hoàn được chuyển qua phương thức thanh toán ban đầu (chuyển khoản, ví điện tử hoặc tiền mặt).
                </li>
              </ul>
            </div>
            <div>
              <h3 className="text-base font-semibold text-zinc-800 mb-2">1.3. Chi phí khi trả hàng</h3>
              <ul className="list-disc pl-6 space-y-2">
                <li>Nếu sản phẩm lỗi hoặc giao nhầm, 188.COM.VN chịu toàn bộ chi phí vận chuyển.</li>
                <li>Nếu khách hàng trả hàng vì lý do cá nhân hoặc ngoài quy định, không áp dụng hoàn tiền.</li>
              </ul>
            </div>
          </div>
        </div>

        <div>
          <h2 className="text-lg font-semibold text-zinc-900">2. Chính sách đổi hàng</h2>
          <div className="mt-4 space-y-4 text-zinc-600">
            <div>
              <h3 className="text-base font-semibold text-zinc-800 mb-2">2.1. Các trường hợp được đổi hàng</h3>
              <ul className="list-disc pl-6 space-y-2">
                <li>Sản phẩm mặc không vừa: Hỗ trợ đổi 01 lần sang size khác.</li>
                <li>
                  <strong className="text-zinc-800">Trường hợp sản phẩm đã là size nhỏ nhất hoặc lớn nhất:</strong> Nếu khách hàng muốn đổi vì lý do không vừa nhưng sản phẩm không có lỗi và đã giao đúng mô tả, quý khách có thể đổi sang mẫu khác có giá trị cao hơn. Khi đó, 188.COM.VN sẽ hỗ trợ đổi và khấu trừ <strong className="text-zinc-800">40%</strong> giá trị sản phẩm ban đầu để bù chi phí xử lý và giảm giá trị hàng đã mở. Chính sách này nhằm đảm bảo công bằng và chất lượng phục vụ ổn định.
                </li>
                <li>Sản phẩm bị lỗi do nhà sản xuất hoặc giao nhầm hàng: Được đổi miễn phí.</li>
                <li>
                  Không áp dụng đổi trong các trường hợp lỗi do người sử dụng gây ra (rách, thủng, rút sợi, giặt máy, phai màu hoặc hư hỏng vật lý khác).
                </li>
              </ul>
            </div>
            <div>
              <h3 className="text-base font-semibold text-zinc-800 mb-2">2.2. Điều kiện đổi hàng</h3>
              <ul className="list-disc pl-6 space-y-2">
                <li>Sản phẩm còn nguyên nhãn mác, chưa qua sử dụng, chưa giặt tẩy, không bị bẩn hoặc hư hại.</li>
                <li>Bao bì, hộp, phụ kiện (nếu có) được giữ nguyên vẹn.</li>
                <li>Trường hợp đặc biệt ngoài quy định cần được 188.COM.VN xác nhận trước khi gửi đổi.</li>
              </ul>
            </div>
            <div>
              <h3 className="text-base font-semibold text-zinc-800 mb-2">2.3. Thời gian đổi hàng</h3>
              <ul className="list-disc pl-6 space-y-2">
                <li>Đổi hàng trong vòng <strong className="text-zinc-800">07 ngày</strong> kể từ ngày nhận hàng (theo dữ liệu của đơn vị vận chuyển).</li>
                <li>Nếu khách có lý do khách quan (đi công tác, bận việc…), vui lòng liên hệ trước để được hỗ trợ.</li>
              </ul>
            </div>
            <div>
              <h3 className="text-base font-semibold text-zinc-800 mb-2">2.4. Phí / cước đổi hàng</h3>
              <ul className="list-disc pl-6 space-y-2">
                <li>Trường hợp không vừa: khách hàng thanh toán phí vận chuyển hai chiều (khoảng 60.000đ).</li>
                <li>Trường hợp sản phẩm lỗi hoặc giao nhầm: 188.COM.VN chịu toàn bộ chi phí vận chuyển.</li>
              </ul>
            </div>
          </div>
        </div>

        <div>
          <h2 className="text-lg font-semibold text-zinc-900">3. Hướng dẫn liên hệ đổi / trả hàng</h2>
          <ul className="mt-4 list-disc pl-6 space-y-2 text-zinc-600">
            <li>
              <strong className="text-zinc-800">Hotline / Zalo:</strong>{' '}
              <a href="tel:0968659836" className="text-orange-600 underline hover:text-orange-700">
                0968 659 836
              </a>
            </li>
            <li>
              <strong className="text-zinc-800">Email:</strong>{' '}
              <a href="mailto:Phungvanhau10101985@gmail.com" className="text-orange-600 underline hover:text-orange-700 break-all">
                Phungvanhau10101985@gmail.com
              </a>
            </li>
            <li>
              <strong className="text-zinc-800">Địa chỉ nhận hàng đổi/trả:</strong> Xóm Buối, Thôn Vật Lại 3, Xã Vật Lại, Huyện Ba Vì, Hà Nội
            </li>
            <li>
              <strong className="text-zinc-800">Thời gian làm việc:</strong> 8:00 – 16:00 (Thứ 2 – Thứ 7)
            </li>
          </ul>
        </div>

        <div>
          <h2 className="text-lg font-semibold text-zinc-900">4. Lưu ý chung</h2>
          <ul className="mt-4 list-disc pl-6 space-y-2 text-zinc-600">
            <li>Sản phẩm đổi hoặc trả phải đáp ứng điều kiện nêu tại Mục 2.2.</li>
            <li>188.COM.VN có quyền từ chối đổi hoặc trả nếu sản phẩm không còn nguyên vẹn hoặc vi phạm điều kiện bảo hành.</li>
            <li>Chính sách có thể được cập nhật mà không cần thông báo trước, áp dụng cho đơn hàng phát sinh kể từ ngày đăng tải mới nhất.</li>
          </ul>
        </div>

        <div>
          <h2 className="text-lg font-semibold text-zinc-900">5. Cam kết</h2>
          <p className="mt-4 text-zinc-600">
            188.COM.VN cam kết mang đến trải nghiệm mua sắm an toàn – minh bạch – chuyên nghiệp, bảo đảm quyền lợi rõ ràng cho khách hàng. Chúng tôi luôn sẵn sàng hỗ trợ nhanh chóng và tận tâm trong mọi trường hợp phát sinh.
          </p>
          <p className="mt-4 text-zinc-600 font-medium">Quy định này có hiệu lực từ ngày 10/10/2025.</p>
        </div>
      </section>

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
          <span className="block sm:inline sm:ml-0">
            <strong>Email:</strong>{' '}
            <a href="mailto:hotro@188.com.vn" className="text-orange-600 underline hover:text-orange-700">
              hotro@188.com.vn
            </a>
          </span>
        </p>
        <p className="text-zinc-600 italic">Quý khách vui lòng liên hệ trước khi đến làm việc để được hỗ trợ và phục vụ tốt nhất.</p>
      </div>
    </InfoPageLayout>
  );
}
