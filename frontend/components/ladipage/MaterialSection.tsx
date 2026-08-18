'use client';

import EditableText from './EditableText';
import EditableImage from './EditableImage';
import HeroEditableImage from './HeroEditableImage';
import HeroDisplayImage from './HeroDisplayImage';
import { MaterialImageZoomView, isAiMaterialImage } from './MaterialImageZoomView';
import type { HeroImageOption, MaterialSectionData } from './types';

/** Ảnh chất liệu AI: poster 4:3 — kính lúp + 4 ô 2 tầng chữ + banner cam kết. */
const MATERIAL_IMAGE_ASPECT = 'aspect-[4/3]';
const MATERIAL_IMAGE_FIT = 'contain' as const;

interface MaterialSectionProps {
  data: MaterialSectionData;
  editable?: boolean;
  isBusy?: boolean;
  imagePrompt?: string;
  /** Ladipage 1 SP — bật chọn ảnh SP thay vì AI */
  singleProductMode?: boolean;
  productImageOptions?: HeroImageOption[];
  /** URL gallery/màu SP — phân biệt ảnh pick từ SP vs ảnh AI trên trang công khai */
  productImageUrls?: string[];
  onSaveField?: (field: keyof MaterialSectionData, value: string) => void | Promise<void>;
  onRegenerateText?: (instruction: string) => void | Promise<void>;
  onRegenerateImage?: (prompt: string) => void | Promise<void>;
}

export default function MaterialSection({
  data,
  editable = false,
  isBusy = false,
  imagePrompt = '',
  singleProductMode = false,
  productImageOptions = [],
  productImageUrls = [],
  onSaveField,
  onRegenerateText,
  onRegenerateImage,
}: MaterialSectionProps) {
  const imageSource =
    !singleProductMode || data.image_source === 'ai' ? 'ai' : 'product';
  /** Trang công khai: chỉ ảnh AI mới có kính lúp. */
  const publicMaterialZoomEnabled =
    !editable &&
    isAiMaterialImage(data, {
      singleProductMode,
      productImageUrls:
        productImageUrls.length > 0
          ? productImageUrls
          : productImageOptions.map((item) => item.url),
    });
  const useProductImagePicker =
    editable && singleProductMode && imageSource === 'product' && !!onSaveField;

  const renderImage = () => {
    if (useProductImagePicker) {
      return (
        <HeroEditableImage
          src={data.image_url}
          objectPosition={data.image_object_position}
          alt={data.material ? `Chất liệu ${data.material}` : 'Ảnh chất liệu'}
          aspectClassName={MATERIAL_IMAGE_ASPECT}
          imageOptions={productImageOptions}
          isBusy={isBusy}
          onSelectImage={(url) => onSaveField!('image_url', url)}
          onSavePosition={(position) => onSaveField!('image_object_position', position)}
        />
      );
    }

    if (!editable) {
      const alt = data.material ? `Chất liệu ${data.material}` : 'Ảnh chất liệu';
      if (publicMaterialZoomEnabled) {
        return (
          <MaterialImageZoomView
            url={data.image_url!}
            alt={alt}
            zoomEnabled
            className={`${MATERIAL_IMAGE_ASPECT} w-full overflow-hidden rounded-xl bg-gray-100`}
            imgClassName="object-contain"
            lensSize={120}
            zoomScale={6}
            previewSize={420}
          />
        );
      }
      return (
        <HeroDisplayImage
          src={data.image_url}
          objectPosition={data.image_object_position}
          alt={alt}
          aspectClassName={MATERIAL_IMAGE_ASPECT}
          objectFit={MATERIAL_IMAGE_FIT}
        />
      );
    }

    return (
      <EditableImage
        src={data.image_url}
        alt={data.material ? `Chất liệu ${data.material}` : 'Ảnh chất liệu'}
        editable={editable}
        isBusy={isBusy}
        initialPrompt={imagePrompt}
        onRegenerate={imageSource === 'ai' ? onRegenerateImage : undefined}
        aspectClassName={MATERIAL_IMAGE_ASPECT}
        objectFit={MATERIAL_IMAGE_FIT}
      />
    );
  };

  return (
    <section className="my-6 grid grid-cols-1 items-center gap-7 overflow-hidden rounded-[1.75rem] border border-gray-100 bg-gradient-to-br from-gray-50 via-white to-orange-50/50 p-5 py-8 md:my-10 md:grid-cols-2 md:gap-12 md:p-10">
      <div>
        {editable && singleProductMode && onSaveField ? (
          <div className="mb-3 flex flex-wrap gap-2">
            <button
              type="button"
              disabled={isBusy}
              onClick={() => onSaveField('image_source', 'ai')}
              className={`rounded-full border px-3 py-1 text-xs font-medium ${
                imageSource === 'ai'
                  ? 'border-orange-500 bg-orange-50 text-orange-700'
                  : 'border-gray-200 text-gray-600 hover:bg-gray-50'
              }`}
            >
              AI tạo ảnh chất liệu
            </button>
            <button
              type="button"
              disabled={isBusy}
              onClick={() => {
                void onSaveField('image_source', 'product');
                if (!data.image_url && productImageOptions[0]) {
                  void onSaveField('image_url', productImageOptions[0].url);
                  void onSaveField('image_object_position', '50% 50%');
                }
              }}
              className={`rounded-full border px-3 py-1 text-xs font-medium ${
                imageSource === 'product'
                  ? 'border-orange-500 bg-orange-50 text-orange-700'
                  : 'border-gray-200 text-gray-600 hover:bg-gray-50'
              }`}
            >
              Chọn ảnh sản phẩm
            </button>
          </div>
        ) : null}
        <div className="overflow-hidden rounded-2xl bg-white shadow-lg shadow-gray-900/5">{renderImage()}</div>
        {editable && singleProductMode && imageSource === 'product' ? (
          <p className="mt-2 text-xs text-gray-500">
            Bấm ảnh để chọn từ gallery / màu / chi tiết SP và kéo để chỉnh vị trí hiển thị.
          </p>
        ) : null}
      </div>
      <div>
        <p className="text-xs font-bold uppercase tracking-[0.16em] text-orange-600">Chất liệu và trải nghiệm</p>
        <h2 className="mt-2 text-2xl font-extrabold tracking-tight text-gray-950 md:text-3xl">
          Chất liệu {data.material ? <span className="text-orange-600">{data.material}</span> : ''}
        </h2>
        <EditableText
          as="p"
          value={data.body || ''}
          placeholder="Chưa có nội dung giải thích chất liệu"
          className="mt-4 text-base leading-relaxed text-gray-700"
          multiline
          editable={editable}
          isBusy={isBusy}
          onSave={onSaveField ? (v) => onSaveField('body', v) : undefined}
          onRegenerate={onRegenerateText}
          regenerateLabel="Yêu cầu thêm khi viết lại (có thể để trống)"
        />
        {data.callouts && data.callouts.length > 0 && (
          <ul className="mt-4 flex flex-wrap gap-2">
            {data.callouts.map((c, i) => (
              <li
                key={i}
                className="rounded-full border border-orange-100 bg-white px-3 py-1.5 text-xs font-semibold text-orange-700 shadow-sm"
              >
                {c}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
