import InfoPageLayout from '@/components/info/InfoPageLayout';
import Link from 'next/link';

export const metadata = {
  title: 'Vì sao cần ngày sinh và giới tính? | 188.com.vn',
  description:
    '188.com.vn dùng ngày sinh và giới tính để gửi ưu đãi sinh nhật và gợi ý sản phẩm hợp tuổi, hợp gu cho bạn.',
};

export default function GoiYTuoiGioiPage() {
  return (
    <InfoPageLayout title="Vì sao cần ngày sinh và giới tính?">
      <p className="text-sm text-zinc-600 mb-6">
        188.com.vn hỏi hai thông tin này để <strong className="text-zinc-800">chăm sóc bạn tốt hơn</strong> — không
        phải để thu thập cho mục đích khác.
      </p>

      <h2 className="text-lg font-semibold text-zinc-900 mt-2 mb-3">Mục đích chính</h2>
      <ul className="list-disc pl-5 space-y-3 text-zinc-600">
        <li>
          <strong className="text-zinc-800">Ưu đãi & quà tặng dịp sinh nhật</strong> — khi bạn có ngày sinh trong
          Hồ sơ, shop có thể gửi chương trình giảm giá và ưu đãi riêng vào dịp sinh nhật của bạn.
        </li>
        <li>
          <strong className="text-zinc-800">Gợi ý sản phẩm hợp tuổi, hợp gu</strong> — giúp bạn thấy những mẫu phù
          hợp với độ tuổi và sở thích, dễ chọn hơn thay vì lướt quá nhiều mặt hàng không liên quan.
        </li>
        <li>
          <strong className="text-zinc-800">Trải nghiệm mua sắm cá nhân hóa</strong> — trang chủ và gợi ý sẽ thiên về
          những gì có thể phù hợp với bạn, bên cạnh các sản phẩm bạn đang quan tâm.
        </li>
      </ul>

      <h2 className="text-lg font-semibold text-zinc-900 mt-8 mb-3">Quyền riêng tư của bạn</h2>
      <ul className="list-disc pl-5 space-y-2 text-zinc-600">
        <li>Ngày sinh và giới tính <strong className="text-zinc-800">không hiển thị công khai</strong> trên shop.</li>
        <li>Chỉ dùng cho <strong className="text-zinc-800">ưu đãi và gợi ý</strong> trên tài khoản của bạn.</li>
        <li>Bạn có thể <strong className="text-zinc-800">cập nhật hoặc chỉnh sửa</strong> bất cứ lúc nào trong Hồ sơ.</li>
      </ul>

      <h2 className="text-lg font-semibold text-zinc-900 mt-8 mb-3">Nếu chưa điền hồ sơ</h2>
      <p className="text-zinc-600">
        Bạn vẫn mua sắm bình thường. Khi bổ sung ngày sinh và giới tính, shop mới có thể gửi{' '}
        <strong className="text-zinc-800">ưu đãi sinh nhật</strong> và{' '}
        <strong className="text-zinc-800">gợi ý phù hợp hơn</strong> dành riêng cho bạn.
      </p>

      <div className="mt-8 flex flex-wrap gap-3">
        <Link
          href="/account/profile"
          className="inline-flex items-center justify-center rounded-xl bg-[#ea580c] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#c2410c] transition-colors"
        >
          Cập nhật Hồ sơ
        </Link>
        <Link
          href="/"
          className="inline-flex items-center justify-center rounded-xl border border-zinc-200 bg-white px-4 py-2.5 text-sm font-medium text-zinc-700 hover:bg-zinc-50 transition-colors"
        >
          Về trang chủ
        </Link>
      </div>
    </InfoPageLayout>
  );
}
