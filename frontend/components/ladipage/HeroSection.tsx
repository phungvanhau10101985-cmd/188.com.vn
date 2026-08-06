'use client';

import EditableText from './EditableText';
import EditableImage from './EditableImage';
import HeroEditableImage from './HeroEditableImage';
import HeroDisplayImage from './HeroDisplayImage';
import type { HeroSectionData } from './types';
import type { HeroImageOption } from '@/components/ladipage/types';

interface HeroSectionProps {
  data: HeroSectionData;
  editable?: boolean;
  isBusy?: boolean;
  imagePrompt?: string;
  productImageOptions?: HeroImageOption[];
  onSaveField?: (field: keyof HeroSectionData, value: string) => void | Promise<void>;
  onRegenerateText?: (instruction: string) => void | Promise<void>;
  onRegenerateImage?: (prompt: string) => void | Promise<void>;
  ctaSlot?: React.ReactNode;
}

export default function HeroSection({
  data,
  editable = false,
  isBusy = false,
  imagePrompt = '',
  productImageOptions = [],
  onSaveField,
  onRegenerateText,
  onRegenerateImage,
  ctaSlot,
}: HeroSectionProps) {
  const useProductHeroPicker = editable && !!onSaveField;

  const renderHeroImage = () => {
    if (useProductHeroPicker) {
      return (
        <HeroEditableImage
          src={data.image_url}
          objectPosition={data.image_object_position}
          alt={data.headline || 'Ảnh banner'}
          aspectClassName="aspect-[4/3]"
          imageOptions={productImageOptions}
          isBusy={isBusy}
          onSelectImage={(url) => onSaveField!('image_url', url)}
          onSavePosition={(position) => onSaveField!('image_object_position', position)}
        />
      );
    }

    if (!editable) {
      return (
        <HeroDisplayImage
          src={data.image_url}
          objectPosition={data.image_object_position}
          alt={data.headline || 'Ảnh banner'}
          aspectClassName="aspect-[4/3]"
        />
      );
    }

    return (
      <EditableImage
        src={data.image_url}
        alt={data.headline || 'Ảnh banner'}
        editable={editable}
        isBusy={isBusy}
        initialPrompt={imagePrompt}
        onRegenerate={onRegenerateImage}
        aspectClassName="aspect-[4/3]"
      />
    );
  };

  return (
    <section className="relative isolate my-4 overflow-hidden rounded-[2rem] border border-orange-100 bg-gradient-to-br from-orange-50 via-white to-amber-50 px-5 py-8 sm:px-8 md:my-8 md:px-10 md:py-12">
      <div aria-hidden="true" className="absolute -left-20 bottom-0 h-48 w-48 rounded-full bg-orange-200/30 blur-3xl" />
      <div aria-hidden="true" className="absolute -right-16 -top-16 h-52 w-52 rounded-full bg-amber-200/40 blur-3xl" />
      <div className="relative grid grid-cols-1 items-center gap-8 md:grid-cols-2 md:gap-12">
        <div className="order-2 md:order-1">
          <p className="mb-3 inline-flex items-center gap-2 rounded-full border border-orange-200 bg-white/80 px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-orange-700 shadow-sm">
            <span className="h-1.5 w-1.5 rounded-full bg-orange-500" />
            Gợi ý dành cho bạn
          </p>
          <EditableText
            as="h1"
            value={data.headline || ''}
            placeholder="Tiêu đề chính chưa có nội dung"
            className="max-w-xl text-3xl font-extrabold leading-[1.12] tracking-tight text-gray-950 md:text-5xl"
            editable={editable}
            isBusy={isBusy}
            onSave={onSaveField ? (v) => onSaveField('headline', v) : undefined}
            onRegenerate={onRegenerateText}
            regenerateLabel="Yêu cầu thêm cho tiêu đề (có thể để trống)"
          />
          <EditableText
            as="p"
            value={data.subheadline || ''}
            placeholder="Câu mô tả phụ chưa có nội dung"
            className="mt-5 max-w-lg text-base leading-relaxed text-gray-600 md:text-lg"
            multiline
            editable={editable}
            isBusy={isBusy}
            onSave={onSaveField ? (v) => onSaveField('subheadline', v) : undefined}
          />
          {ctaSlot ? <div className="mt-7">{ctaSlot}</div> : null}
        </div>
        <div className="order-1 md:order-2">
          <div className="relative">
            <div aria-hidden="true" className="absolute -inset-3 rounded-[1.75rem] bg-orange-200/50 blur-xl" />
            <div className="relative overflow-hidden rounded-[1.5rem] border-4 border-white bg-white shadow-xl shadow-orange-900/10">
              {renderHeroImage()}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
