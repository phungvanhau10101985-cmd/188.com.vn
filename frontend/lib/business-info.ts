/** Thông tin pháp lý doanh nghiệp — dùng chung cho JSON-LD, footer, trang info. */
export const BUSINESS_LEGAL_NAME = "Hộ Kinh Doanh Phùng Văn Hậu";
export const BUSINESS_REGISTRATION = "01Q8011025";
export const BUSINESS_REPRESENTATIVE = "Phùng Văn Hậu";
export const BUSINESS_PHONE = "0968659836";
export const BUSINESS_PHONE_DISPLAY = "0968 659 836";
export const BUSINESS_EMAIL = "hotro@188.com.vn";
export const BUSINESS_ADDRESS = {
  streetAddress: "Xóm Buối, Thôn Vật Lại 3, Xã Vật Lại",
  addressLocality: "Ba Vì",
  addressRegion: "Hà Nội",
  postalCode: "",
  addressCountry: "VN",
};
export const BUSINESS_HOURS = "Mo-Sa 08:00-16:30";
export const BUSINESS_FACEBOOK = "https://facebook.com/188.com.vn";
export const BUSINESS_ZALO = "https://zalo.me/1714121106420519241";
export const BOCT_REGISTRATION_URL =
  "http://online.gov.vn/Home/WebDetails/137314?AspxAutoDetectCookieSupport=1";

export const SHIPPING_FREE_THRESHOLD_VND = 500_000;
export const SHIPPING_FEE_VND = 30_000;
export const DEPOSIT_PERCENT = 30;

export const RETURN_POLICY_URL = "/info/doi-tra-hoan-tien";
export const SHIPPING_POLICY_URL = "/info/chinh-sach-giao-hang";
export const PURCHASE_GUIDE_URL = "/info/huong-dan-mua-hang";
export const TERMS_URL = "/info/dieu-khoan-su-dung";

/** Tính phí vận chuyển — khớp backend orders.py */
export function computeShippingFee(subtotalAfterDiscounts: number): number {
  if (subtotalAfterDiscounts <= 0) return 0;
  return subtotalAfterDiscounts < SHIPPING_FREE_THRESHOLD_VND ? SHIPPING_FEE_VND : 0;
}
