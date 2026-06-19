type OrderItemVariantRef = {
  selected_size?: string | null;
  selected_color?: string | null;
  selected_color_name?: string | null;
  product_image?: string | null;
};

export function orderItemColorLabel(item: Pick<OrderItemVariantRef, 'selected_color' | 'selected_color_name'>): string | null {
  const name = item.selected_color_name?.trim();
  const code = item.selected_color?.trim();
  if (name && code && name !== code) return `${name} (${code})`;
  return name || code || null;
}

export function orderItemImageLink(item: Pick<OrderItemVariantRef, 'product_image'>): string | null {
  const url = item.product_image?.trim();
  return url || null;
}

type OrderItemVariantMetaProps = {
  item: OrderItemVariantRef;
  className?: string;
  /** Hiển thị URL đầy đủ thay vì rút gọn */
  fullImageUrl?: boolean;
};

/** Size, màu và link ảnh biến thể — dùng trong chi tiết đơn hàng. */
export default function OrderItemVariantMeta({
  item,
  className = 'mt-1.5 space-y-0.5 text-xs text-gray-600',
  fullImageUrl = true,
}: OrderItemVariantMetaProps) {
  const size = item.selected_size?.trim();
  const color = orderItemColorLabel(item);
  const imageUrl = orderItemImageLink(item);

  if (!size && !color && !imageUrl) return null;

  return (
    <div className={className}>
      {size ? <p>Size: {size}</p> : null}
      {color ? <p>Màu: {color}</p> : null}
      {imageUrl ? (
        <p className="break-words">
          <span className="text-gray-500">Link ảnh: </span>
          <a
            href={imageUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-700 hover:underline break-all"
            title={imageUrl}
          >
            {fullImageUrl ? imageUrl : imageUrl.replace(/^https?:\/\//, '')}
          </a>
        </p>
      ) : null}
    </div>
  );
}
