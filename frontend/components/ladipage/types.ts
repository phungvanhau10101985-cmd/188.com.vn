/** Kiểu dữ liệu nội dung từng section Ladipage (khớp `data` JSON phía backend). */

export interface HeroSectionData {
  headline?: string;
  subheadline?: string;
  image_url?: string;
  /** CSS object-position, vd `50% 40%` — chỉnh tiêu điểm ảnh hero trong khung crop. */
  image_object_position?: string;
}

export interface HeroImageOption {
  url: string;
  productId: number;
  productName: string;
  label: string;
}

export interface HighlightItem {
  title: string;
  desc: string;
}

export interface HighlightsSectionData {
  items?: HighlightItem[];
}

export interface MaterialSectionData {
  material?: string;
  body?: string;
  callouts?: string[];
  image_url?: string;
  /** Ladipage 1 SP: `product` = chọn ảnh SP (mặc định); `ai` = Gemini tạo ảnh. Ladipage khác luôn `ai`. */
  image_source?: 'ai' | 'product';
  image_object_position?: string;
}

export interface TrustCtaSectionData {
  body?: string;
  cta_label?: string;
}

export interface FaqItem {
  q: string;
  a: string;
}

export interface FaqSectionData {
  items?: FaqItem[];
}
