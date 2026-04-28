/** Cấu hình các trang thông tin / chính sách - dùng cho sidebar và footer */
export const INFO_PAGES = [
  { slug: 'gioi-thieu', title: 'Giới thiệu về chúng tôi – 188.com.vn' },
  { slug: 'uy-tin', title: '188.com.vn có uy tín không?' },
  { slug: 'lien-he', title: 'Thông tin liên hệ' },
  { slug: 'thong-tin-don-vi', title: 'Thông tin đơn vị sở hữu website' },
  { slug: 'huong-dan-mua-hang', title: 'Hướng dẫn mua hàng - Điều kiện thanh toán' },
  { slug: 'chinh-sach-giao-hang', title: 'Chính sách giao hàng' },
  { slug: 'doi-tra-hoan-tien', title: 'Đổi trả & Hoàn tiền' },
  { slug: 'chinh-sach-bao-mat', title: 'Chính sách bảo mật' },
  { slug: 'dieu-khoan-su-dung', title: 'Điều khoản sử dụng' },
  { slug: 'nguon-goc-thuong-hieu', title: 'Nguồn gốc và Thương hiệu sản phẩm' },
  { slug: 'chinh-sach-danh-gia', title: 'Chính sách quản lý đánh giá và chất lượng sản phẩm' },
] as const;

export type InfoSlug = (typeof INFO_PAGES)[number]['slug'];
