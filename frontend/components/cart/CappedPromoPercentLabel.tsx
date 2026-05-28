import {
  formatDiscountPercent,
  MAX_ORDER_DISCOUNT_PERCENT,
  type CappedPromoPercentDisplay,
} from '@/lib/order-discount-limits';

type CappedPromoPercentLabelProps = {
  display: CappedPromoPercentDisplay;
  className?: string;
};

export default function CappedPromoPercentLabel({ display, className }: CappedPromoPercentLabelProps) {
  if (display.kind === 'nominal') {
    return <span className={className}>{display.percent}%</span>;
  }

  if (display.kind === 'capped_site') {
    return (
      <span className={className}>
        còn {formatDiscountPercent(display.effectivePercent)}% ({MAX_ORDER_DISCOUNT_PERCENT}% −{' '}
        {formatDiscountPercent(display.sitePercent)}% sale){' '}
        <span className="font-normal text-gray-400">
          (Giảm giá tổng không quá {MAX_ORDER_DISCOUNT_PERCENT}%)
        </span>
      </span>
    );
  }

  return (
    <span className={className}>
      {formatDiscountPercent(display.effectivePercent)}% ({display.nominalPercent}% −{' '}
      {formatDiscountPercent(display.cutPercent)}% do trần {MAX_ORDER_DISCOUNT_PERCENT}%){' '}
      <span className="font-normal text-gray-400">
        (Giảm giá tổng không quá {MAX_ORDER_DISCOUNT_PERCENT}%)
      </span>
    </span>
  );
}
