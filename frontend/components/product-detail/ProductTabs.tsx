// frontend/components/product-detail/ProductTabs.tsx - FIXED HOÀN CHỈNH
'use client';

import { useState } from 'react';
import { cdnUrl } from '@/lib/cdn-url';
import { Product } from '@/types/api';
import RelatedProducts from '@/components/product-detail/RelatedProducts';
import ShopSidebarProducts from '@/components/product-detail/ShopSidebarProducts';
import Image from 'next/image';
import { getOptimizedImage } from '@/lib/image-utils';
import { displayableBrandOrOrigin } from '@/lib/utils';

interface ProductTabsProps {
  product: Product;
}

/** Map key (snake_case) sang nhãn tiếng Việt cho định dạng cột AK */
const SECTION_LABELS: Record<string, string> = {
  thong_tin_san_pham: '1. Thông tin sản phẩm',
  thong_so_ky_thuat: '2. Thông số kỹ thuật',
  phan_loai: '3. Phân loại',
  doi_tuong_khach_hang: '4. Đối tượng khách hàng',
  thong_tin_thi_truong: '5. Thông tin thị trường',
  product_info: '1. Thông tin sản phẩm',
  specifications: '2. Thông số kỹ thuật',
  variants: '3. Phân loại',
  target_audience: '4. Đối tượng khách hàng',
  market_info: '5. Thông tin thị trường',
};
const FIELD_LABELS: Record<string, string> = {
  ma_hang: 'Mã hàng',
  ten_san_pham: 'Tên sản phẩm',
  thuong_hieu: 'Thương hiệu',
  nguon_hang: 'Nguồn hàng',
  danh_muc: 'Danh mục',
  cap_1: 'Cấp 1',
  cap_2: 'Cấp 2',
  cap_3: 'Cấp 3',
  chat_lieu_mat_tren: 'Chất liệu mặt trên',
  chat_lieu_lot_trong: 'Chất liệu lót trong',
  chat_lieu_de_ngoai: 'Chất liệu đế ngoài',
  chat_lieu_lot_giay: 'Chất liệu lót giày',
  cong_nghe_de: 'Công nghệ đế',
  hinh_dang_mui: 'Hình dạng mũi',
  chieu_cao_got: 'Chiều cao gót',
  trong_luong_gram: 'Trọng lượng (gram)',
  cach_mac: 'Cách mặc',
  tinh_nang_noi_bat: 'Tính năng nổi bật',
  mau_sac: 'Màu sắc',
  kich_co: 'Kích cỡ',
  gioi_tinh: 'Giới tính',
  do_tuoi_phu_hop: 'Độ tuổi phù hợp',
  phong_cach: 'Phong cách',
  mua_phu_hop: 'Mùa phù hợp',
  xuat_khau_xuyen_bien_gioi: 'Xuất khẩu xuyên biên giới',
  thoi_gian_chuan_bi_hang: 'Thời gian chuẩn bị hàng',
  khu_vuc_ban_hang_chinh: 'Khu vực bán hàng chính',
};

function formatLabel(key: string, useMap: 'section' | 'field' | 'auto' = 'auto'): string {
  const k = key.trim();
  if (useMap === 'section' || (useMap === 'auto' && SECTION_LABELS[k])) return SECTION_LABELS[k] ?? k.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  if (useMap === 'field' || (useMap === 'auto' && FIELD_LABELS[k])) return FIELD_LABELS[k] ?? k.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  return k.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Hiển thị toàn bộ dữ liệu cột AK (product_info) - mọi trường trong JSON */
function ProductInfoTab({ product }: { product: Product }) {
  /** Parse product_info: có thể là object, hoặc chuỗi JSON (kể cả escape \\" và \\u...) */
  let info: Record<string, unknown> | null = null;
  const raw = product.product_info;
  if (raw != null && typeof raw === 'object' && !Array.isArray(raw)) {
    info = raw as Record<string, unknown>;
  } else if (typeof raw === 'string' && raw.trim()) {
    let s: string = raw.trim();
    for (let i = 0; i < 3; i++) {
      try {
        const parsed = JSON.parse(s) as unknown;
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          info = parsed as Record<string, unknown>;
          break;
        }
        if (typeof parsed === 'string' && parsed.trim()) {
          s = parsed.trim();
          continue;
        }
        break;
      } catch {
        break;
      }
    }
  }

  const SpecRow = ({ label, value }: { label: string; value: string | number | boolean }) => (
    <div className="grid grid-cols-[minmax(0,10rem)_minmax(0,1fr)] gap-x-3 py-1 border-b border-gray-100 text-xs items-baseline">
      <span className="text-gray-600 shrink-0">{label}</span>
      <span className="font-medium text-gray-900 break-words min-w-0">{String(value)}</span>
    </div>
  );

  const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
    <div className="mb-3">
      <h4 className="font-semibold text-gray-900 text-sm mb-1.5 pb-1 border-b border-gray-200">{title}</h4>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-0">{children}</div>
    </div>
  );

  /** Render một giá trị bất kỳ thành string hoặc React node */
  const renderValue = (val: unknown): React.ReactNode => {
    if (val === undefined || val === null) return null;
    if (typeof val === 'boolean') return val ? 'Có' : 'Không';
    if (typeof val === 'number' || typeof val === 'string') return String(val);
    if (Array.isArray(val)) return val.map((v) => (typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v))).join(', ');
    if (typeof val === 'object') {
      const entries = Object.entries(val as Record<string, unknown>);
      if (entries.length === 0) return null;
      return (
        <div className="space-y-0.5 pl-2 border-l-2 border-gray-200 text-xs">
          {entries.map(([k, v]) => {
            const display = renderValue(v);
            if (display === null) return null;
            const lbl = formatLabel(k, 'field');
            return (
              <div key={k} className="leading-tight">
                <span className="text-gray-600">{lbl}:</span>{' '}
                <span className="text-gray-900">{typeof display === 'string' ? display : null}</span>
                {typeof display !== 'string' && display}
              </div>
            );
          })}
        </div>
      );
    }
    return String(val);
  };

  /** Render toàn bộ object cột AK: mỗi key top-level là một section, bên trong là các dòng key-value */
  if (info && Object.keys(info).length > 0) {
    return (
      <div className="space-y-3">
        {Object.entries(info).map(([sectionKey, sectionVal]) => {
          if (sectionVal === undefined || sectionVal === null) return null;
          const title = formatLabel(sectionKey, 'section');
          if (typeof sectionVal === 'object' && !Array.isArray(sectionVal)) {
            const entries = Object.entries(sectionVal as Record<string, unknown>);
            if (entries.length === 0) return null;
            return (
              <Section key={sectionKey} title={title}>
                {entries.map(([key, val]) => {
                  const display = renderValue(val);
                  if (display === null) return null;
                  const label = formatLabel(key, 'field');
                  if (typeof display === 'string') {
                    return <SpecRow key={key} label={label} value={display} />;
                  }
                  return (
                    <div key={key} className="md:col-span-2 py-0.5">
                      <div className="text-gray-600 text-xs mb-0.5">{label}</div>
                      <div className="text-gray-900 text-xs leading-tight">{display}</div>
                    </div>
                  );
                })}
              </Section>
            );
          }
          return (
            <Section key={sectionKey} title={title}>
              <SpecRow label={title} value={String(sectionVal)} />
            </Section>
          );
        })}
      </div>
    );
  }

  /* Không có dữ liệu cột AK: fallback + hướng dẫn */
  return (
    <div className="space-y-3">
      <p className="text-amber-700 text-xs bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
        Chưa có dữ liệu cột AK (Thông tin sản phẩm). Điền JSON vào ô <strong>Thông tin sản phẩm</strong> trong file Excel và import lại để hiển thị tại đây.
      </p>
      <h4 className="font-semibold text-gray-900 text-sm">Thông tin chi tiết (từ các cột khác)</h4>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
        {displayableBrandOrOrigin(product.brand_name) && <SpecRow label="Thương hiệu" value={displayableBrandOrOrigin(product.brand_name)!} />}
        {displayableBrandOrOrigin(product.origin) && <SpecRow label="Xuất xứ" value={displayableBrandOrOrigin(product.origin)!} />}
        {displayableBrandOrOrigin(product.material) && <SpecRow label="Chất liệu" value={displayableBrandOrOrigin(product.material)!} />}
        {displayableBrandOrOrigin(product.style) && <SpecRow label="Phong cách" value={displayableBrandOrOrigin(product.style)!} />}
        {displayableBrandOrOrigin(product.occasion) && <SpecRow label="Dịp" value={displayableBrandOrOrigin(product.occasion)!} />}
        {displayableBrandOrOrigin(product.category) && <SpecRow label="Danh mục" value={displayableBrandOrOrigin(product.category)!} />}
        {product.available !== undefined && <SpecRow label="Tồn kho" value={`${product.available} sản phẩm`} />}
      </div>
    </div>
  );
}

export default function ProductTabs({ product }: ProductTabsProps) {
  const [activeTab, setActiveTab] = useState('description');

  const tabs = [
    { id: 'description', label: 'Mô Tả Sản Phẩm' },
    { id: 'specifications', label: 'Thông tin sản phẩm' },
  ];

  // Lấy ảnh chi tiết từ gallery (cột Q - detail_images)
  const getDetailImages = () => {
    if (product.gallery && Array.isArray(product.gallery) && product.gallery.length > 0) {
      return product.gallery;
    }
    return [];
  };

  // Lấy mô tả sản phẩm - kiểm tra cả description và product_description
  const getProductDescription = () => {
    return product.description || product.product_description || '';
  };

  const detailImages = getDetailImages();
  const description = getProductDescription();

  return (
    <div className="bg-white rounded-lg border border-gray-200">
      {/* Tab Headers */}
      <div className="border-b border-gray-200">
        <div className="flex overflow-x-auto">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex-1 min-w-0 px-4 py-3 text-xs font-medium border-b-2 transition-colors whitespace-nowrap ${
                activeTab === tab.id
                  ? 'border-orange-500 text-orange-600 bg-orange-50'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      <div className="p-4">
        {activeTab === 'description' && (
          <div className="space-y-4">
            <RelatedProducts currentProduct={product} />

            {/* Product Description */}
            <div className="space-y-2">
              <h2 className="text-base font-bold text-gray-900">📋 Mô tả sản phẩm</h2>
              <div className="prose prose-sm max-w-none text-sm">
                {description ? (
                  <div 
                    className="text-gray-700 leading-snug bg-gray-50 p-4 rounded-lg border border-gray-200 text-sm"
                    dangerouslySetInnerHTML={{ 
                      __html: description.replace(/\n/g, '<br/>') 
                    }}
                  />
                ) : (
                  <div className="text-center py-6 text-gray-500 bg-gray-50 rounded-lg border border-gray-200 text-sm">
                    <div className="text-2xl mb-1">📝</div>
                    <p>Chưa có mô tả cho sản phẩm này</p>
                  </div>
                )}
              </div>
            </div>

            {/* ẢNH CHI TIẾT SẢN PHẨM - từ gallery (cột Q) */}
            {detailImages.length > 0 && (
              <div className="mt-4">
                <h2 className="text-base font-bold text-gray-900 mb-3 pb-2 border-b border-gray-200">
                  📸 Hình ảnh chi tiết sản phẩm
                </h2>
                <div className="grid grid-cols-1 lg:grid-cols-[240px_minmax(0,1fr)] gap-4">
                  <div className="hidden lg:block h-fit self-start mt-[26px] lg:sticky lg:top-[26px] lg:max-h-screen lg:overflow-y-auto scrollbar-on-hover lg:pl-5">
                    <ShopSidebarProducts currentProduct={product} />
                  </div>
                  <div className="space-y-4">
                    {detailImages.map((image, index) => (
                      <div 
                        key={index} 
                        className="bg-white rounded-xl overflow-hidden border border-gray-200 shadow-sm"
                      >
                        <div className="relative w-full h-auto">
                          <Image
                            src={getOptimizedImage(image, { width: 800, height: 600 })}
                            alt={`${product.name} chi tiết ${index + 1}`}
                            width={800}
                            height={600}
                            sizes="(max-width: 1024px) 100vw, 800px"
                            className="w-full h-auto max-w-4xl mx-auto"
                            onError={(e) => {
                              e.currentTarget.src = cdnUrl('/images/placeholder.jpg');
                              e.currentTarget.alt = 'Ảnh không khả dụng';
                            }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Product Specifications Grid - ẩn trường nan/rỗng */}
            {(displayableBrandOrOrigin(product.origin) || displayableBrandOrOrigin(product.material) || displayableBrandOrOrigin(product.style) || displayableBrandOrOrigin(product.brand_name)) && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs bg-gray-50 p-4 rounded-lg border border-gray-200 mt-4">
                {displayableBrandOrOrigin(product.origin) && (
                  <div className="flex justify-between py-2 border-b border-gray-200">
                    <span className="font-semibold text-gray-600">Xuất xứ:</span>
                    <span className="text-gray-800 font-medium">{displayableBrandOrOrigin(product.origin)}</span>
                  </div>
                )}
                {displayableBrandOrOrigin(product.material) && (
                  <div className="flex justify-between py-2 border-b border-gray-200">
                    <span className="font-semibold text-gray-600">Chất liệu:</span>
                    <span className="text-gray-800 font-medium">{displayableBrandOrOrigin(product.material)}</span>
                  </div>
                )}
                {displayableBrandOrOrigin(product.style) && (
                  <div className="flex justify-between py-2 border-b border-gray-200">
                    <span className="font-semibold text-gray-600">Phong cách:</span>
                    <span className="text-gray-800 font-medium">{displayableBrandOrOrigin(product.style)}</span>
                  </div>
                )}
                {displayableBrandOrOrigin(product.brand_name) && (
                  <div className="flex justify-between py-2 border-b border-gray-200">
                    <span className="font-semibold text-gray-600">Thương hiệu:</span>
                    <span className="text-gray-800 font-medium">{displayableBrandOrOrigin(product.brand_name)}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {activeTab === 'specifications' && (
          <ProductInfoTab product={product} />
        )}

      </div>
    </div>
  );
}
