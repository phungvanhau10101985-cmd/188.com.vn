export const HOLIDAY_THEME_IDS = [
  'duong-lich',
  'tao-quan',
  'tet',
  'valentine',
  'nguyen-tieu',
  'phu-nu-83',
  'gio-to',
  'dai-le',
  'thieu-nhi',
  'doan-ngo',
  'vu-lan',
  'quoc-khanh',
  'trung-thu',
  'phu-nu-2010',
  'nha-giao',
  'giang-sinh',
] as const;

export type HolidayThemeId = (typeof HOLIDAY_THEME_IDS)[number];

export type HolidayLook = {
  id: HolidayThemeId;
  ribbonTitle: string;
  ribbonBody: string;
  kicker: string;
  welcomeTitle: string;
  welcomeBody: string;
  productTitle: string;
  productBody: string;
  cartTitle: string;
  cartBody: string;
  checkoutTitle: string;
  checkoutBody: string;
  thanks: string;
  preview: string;
  strong: string;
  deep: string;
  mid: string;
  gold: string;
  goldSoft: string;
  paper: string;
  ink: string;
  dark: string;
  themeColor: string;
};

const looks: HolidayLook[] = [
  look('duong-lich', 'Năm mới', 'Chúc một năm mới bình an', 'Tết Dương lịch', 'Năm mới', 'Đón năm mới, chọn đồ mới.', 'Năm mới', 'Món đồ đầu năm dương lịch.', 'Giỏ năm mới', 'Chốt đơn để giao trong dịp đầu năm.', 'Đặt hàng năm mới', 'Thanh toán như bình thường', 'Chúc năm mới vui vẻ', 'Đang xem trước Tết Dương lịch.', '#1e3a5f', '#0f2744', '#3d6b99', '#e7c36a', '#f6d589', '#f4f7fb', '#1e3a5f', '#0b1c33', '#0f2744'),
  look('tao-quan', 'Đưa Táo về trời', '23 tháng Chạp', 'Ông Công Ông Táo', 'Ông Táo', 'Dọn nhà, sắm đồ mới trước Tết.', 'Ngày Ông Táo', 'Chọn món mới cho bữa tiễn Táo.', 'Giỏ ngày Táo', 'Giao trước khi Tết vào.', 'Đặt hàng ngày Ông Táo', 'Hết ngày này, cửa hàng trở lại giao diện Tết nếu Tết đang mở', 'Tạm biệt Ông Táo', 'Đang xem trước Ông Công Ông Táo.', '#c2410c', '#9a3412', '#ea580c', '#f6d589', '#ffedd5', '#fff7ed', '#9a3412', '#7c2d12', '#9a3412'),
  look('tet', 'Tết đang về', 'Mai đào khoe sắc, sắm Tết an khang cùng 188', 'Mùa Tết Nguyên Đán', 'Tết đang về', 'Hoa mai, hoa đào và lì xì may mắn — chọn đồ mới, giao tận nhà.', 'Tết đang về', 'Món đồ đầu năm — xem mẫu, chọn size, giao trước Tết.', 'Tết đang về — giỏ quà của bạn', 'Sắm Tết an khang. Đặt hàng để giao tận nhà trước mùa hoa đào.', 'Đặt hàng mùa Tết', 'Giao an khang — thanh toán như bình thường', 'Chúc một năm mới an khang', 'Đang xem trước giao diện Tết.', '#b4233a', '#8e1530', '#c44758', '#e7c36a', '#f6d589', '#fff6ee', '#9f1239', '#7a1228', '#8e1530'),
  look('valentine', 'Mùa yêu', '14/2 — chọn quà, giao tận nơi', 'Valentine', 'Mùa yêu', 'Một món đồ cho người mình thương.', 'Quà 14/2', 'Xem mẫu, chọn size, giao trước ngày lễ.', 'Giỏ quà Valentine', 'Chốt đơn để kịp 14/2.', 'Đặt hàng Valentine', 'Thanh toán như bình thường', 'Cảm ơn bạn đã gửi yêu thương', 'Đang xem trước Valentine.', '#9f1239', '#881337', '#be123c', '#fecdd3', '#ffe4e6', '#fff1f2', '#9f1239', '#4c0519', '#881337'),
  look('nguyen-tieu', 'Rằm tháng Giêng', 'Tết Nguyên Tiêu', 'Nguyên Tiêu', 'Rằm tháng Giêng', 'Đèn sáng, chọn đồ mới.', 'Rằm tháng Giêng', 'Xem mẫu và giao trong dịp rằm.', 'Giỏ Nguyên Tiêu', 'Đặt hàng để kịp rằm.', 'Đặt hàng Nguyên Tiêu', 'Thanh toán như bình thường', 'Chúc rằm an lành', 'Đang xem trước Tết Nguyên Tiêu.', '#b45309', '#92400e', '#d97706', '#fde68a', '#fef3c7', '#fffbeb', '#92400e', '#78350f', '#92400e'),
  look('phu-nu-83', '8/3', 'Chúc mừng phụ nữ', 'Quốc tế Phụ nữ', '8/3', 'Món quà cho người phụ nữ bạn quý.', 'Quà 8/3', 'Chọn size, giao trước ngày 8/3.', 'Giỏ quà 8/3', 'Chốt đơn để kịp ngày lễ.', 'Đặt hàng 8/3', 'Thanh toán như bình thường', 'Cảm ơn bạn', 'Đang xem trước 8/3.', '#be185d', '#9d174d', '#db2777', '#fbcfe8', '#fce7f3', '#fdf2f8', '#9d174d', '#831843', '#9d174d'),
  look('gio-to', 'Giỗ Tổ', 'Nhớ nguồn, sắm đồ mới', 'Giỗ Tổ Hùng Vương', 'Giỗ Tổ', '10 tháng 3 âm lịch.', 'Ngày Giỗ Tổ', 'Xem mẫu, giao trong dịp Giỗ Tổ.', 'Giỏ Giỗ Tổ', 'Đặt hàng để kịp ngày lễ.', 'Đặt hàng Giỗ Tổ', 'Thanh toán như bình thường', 'Nhớ về nguồn cội', 'Đang xem trước Giỗ Tổ.', '#a16207', '#854d0e', '#ca8a04', '#fde68a', '#fef9c3', '#fefce8', '#854d0e', '#713f12', '#854d0e'),
  look('dai-le', 'Đại lễ', '30/4 và 1/5', '30/4 – 1/5', 'Đại lễ', 'Nghỉ lễ, sắm đồ mới.', 'Đại lễ 30/4', 'Xem mẫu, giao trong kỳ nghỉ.', 'Giỏ đại lễ', 'Đặt hàng để giao trong dịp lễ.', 'Đặt hàng đại lễ', 'Thanh toán như bình thường', 'Chúc kỳ nghỉ vui', 'Đang xem trước 30/4 và 1/5.', '#b91c1c', '#991b1b', '#dc2626', '#fde047', '#fef9c3', '#fef2f2', '#991b1b', '#7f1d1d', '#991b1b'),
  look('thieu-nhi', '1/6', 'Quốc tế Thiếu nhi', 'Thiếu nhi', '1/6', 'Món quà cho bé.', 'Quà 1/6', 'Chọn size, giao trước ngày 1/6.', 'Giỏ quà 1/6', 'Chốt đơn để kịp ngày lễ.', 'Đặt hàng 1/6', 'Thanh toán như bình thường', 'Chúc các bé vui', 'Đang xem trước 1/6.', '#0369a1', '#075985', '#0284c7', '#fde68a', '#e0f2fe', '#f0f9ff', '#075985', '#0c4a6e', '#075985'),
  look('doan-ngo', 'Đoan Ngọ', '5 tháng 5 âm lịch', 'Tết Đoan Ngọ', 'Đoan Ngọ', 'Giữa năm, chọn đồ mới.', 'Tết Đoan Ngọ', 'Xem mẫu, giao trong dịp lễ.', 'Giỏ Đoan Ngọ', 'Đặt hàng để kịp ngày lễ.', 'Đặt hàng Đoan Ngọ', 'Thanh toán như bình thường', 'Chúc giữa năm bình an', 'Đang xem trước Đoan Ngọ.', '#15803d', '#166534', '#16a34a', '#fde68a', '#dcfce7', '#f0fdf4', '#166534', '#14532d', '#166534'),
  look('vu-lan', 'Vu Lan', 'Báo hiếu mùa rằm tháng Bảy', 'Lễ Vu Lan', 'Vu Lan', 'Món quà báo hiếu.', 'Mùa Vu Lan', 'Xem mẫu, giao trong dịp rằm.', 'Giỏ Vu Lan', 'Đặt hàng để kịp rằm tháng Bảy.', 'Đặt hàng Vu Lan', 'Thanh toán như bình thường', 'Chúc gia đình an lành', 'Đang xem trước Vu Lan.', '#7c3aed', '#6d28d9', '#8b5cf6', '#fbcfe8', '#ede9fe', '#f5f3ff', '#6d28d9', '#4c1d95', '#6d28d9'),
  look('quoc-khanh', 'Quốc khánh', '2/9', 'Quốc khánh', 'Quốc khánh', 'Đón lễ, chọn đồ mới.', 'Quốc khánh', 'Xem mẫu, giao trong dịp 2/9.', 'Giỏ Quốc khánh', 'Đặt hàng để giao trong kỳ lễ.', 'Đặt hàng Quốc khánh', 'Thanh toán như bình thường', 'Chúc lễ vui', 'Đang xem trước Quốc khánh.', '#b91c1c', '#7f1d1d', '#dc2626', '#facc15', '#fef9c3', '#fef2f2', '#7f1d1d', '#450a0a', '#7f1d1d'),
  look('trung-thu', 'Trung thu', 'Rằm tháng Tám', 'Tết Trung thu', 'Trung thu', 'Đèn lồng, áo mới, quà trung thu.', 'Mùa trăng', 'Xem mẫu, giao trước rằm.', 'Giỏ Trung thu', 'Đặt hàng để kịp đêm rằm.', 'Đặt hàng Trung thu', 'Thanh toán như bình thường', 'Chúc trung thu vui', 'Đang xem trước Trung thu.', '#b45309', '#1e3a5f', '#d97706', '#fde68a', '#fef3c7', '#fffbeb', '#92400e', '#172554', '#1e3a5f'),
  look('phu-nu-2010', '20/10', 'Phụ nữ Việt Nam', '20/10', '20/10', 'Món quà cho phụ nữ Việt Nam.', 'Quà 20/10', 'Chọn size, giao trước 20/10.', 'Giỏ quà 20/10', 'Chốt đơn để kịp ngày lễ.', 'Đặt hàng 20/10', 'Thanh toán như bình thường', 'Cảm ơn bạn', 'Đang xem trước 20/10.', '#be123c', '#9f1239', '#e11d48', '#fecdd3', '#ffe4e6', '#fff1f2', '#9f1239', '#881337', '#9f1239'),
  look('nha-giao', '20/11', 'Tri ân nhà giáo', 'Nhà giáo Việt Nam', '20/11', 'Món quà cho thầy cô.', 'Quà 20/11', 'Xem mẫu, giao trước 20/11.', 'Giỏ 20/11', 'Chốt đơn để kịp ngày nhà giáo.', 'Đặt hàng 20/11', 'Thanh toán như bình thường', 'Cảm ơn thầy cô', 'Đang xem trước 20/11.', '#1d4ed8', '#1e3a8a', '#2563eb', '#fde68a', '#dbeafe', '#eff6ff', '#1e3a8a', '#172554', '#1e3a8a'),
  look('giang-sinh', 'Mùa Giáng sinh', '24 và 25/12', 'Giáng sinh', 'Giáng sinh', 'Đèn ấm, chọn quà cuối năm.', 'Quà Giáng sinh', 'Xem mẫu, giao trước đêm 24.', 'Giỏ Giáng sinh', 'Đặt hàng để kịp đêm Noel.', 'Đặt hàng Giáng sinh', 'Thanh toán như bình thường', 'Chúc mùa lễ an lành', 'Đang xem trước Giáng sinh.', '#166534', '#14532d', '#15803d', '#fecaca', '#dcfce7', '#f0fdf4', '#14532d', '#052e16', '#14532d'),
];

function look(
  id: HolidayThemeId,
  ribbonTitle: string,
  ribbonBody: string,
  kicker: string,
  welcomeTitle: string,
  welcomeBody: string,
  productTitle: string,
  productBody: string,
  cartTitle: string,
  cartBody: string,
  checkoutTitle: string,
  checkoutBody: string,
  thanks: string,
  preview: string,
  strong: string,
  deep: string,
  mid: string,
  gold: string,
  goldSoft: string,
  paper: string,
  ink: string,
  dark: string,
  themeColor: string,
): HolidayLook {
  return {
    id,
    ribbonTitle,
    ribbonBody,
    kicker,
    welcomeTitle,
    welcomeBody,
    productTitle,
    productBody,
    cartTitle,
    cartBody,
    checkoutTitle,
    checkoutBody,
    thanks,
    preview,
    strong,
    deep,
    mid,
    gold,
    goldSoft,
    paper,
    ink,
    dark,
    themeColor,
  };
}

export const HOLIDAY_LOOKS: Record<HolidayThemeId, HolidayLook> = Object.fromEntries(
  looks.map((item) => [item.id, item]),
) as Record<HolidayThemeId, HolidayLook>;

export function isHolidayThemeId(value: string | null | undefined): value is HolidayThemeId {
  return Boolean(value && value in HOLIDAY_LOOKS);
}

export function holidayCssVars(look: HolidayLook): Record<string, string> {
  return {
    '--h-strong': look.strong,
    '--h-deep': look.deep,
    '--h-mid': look.mid,
    '--h-gold': look.gold,
    '--h-gold-soft': look.goldSoft,
    '--h-paper': look.paper,
    '--h-ink': look.ink,
    '--h-dark': look.dark,
  };
}
