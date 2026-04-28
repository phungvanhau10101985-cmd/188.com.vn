import { formatPrice, getDiscountPercentage } from '@/lib/utils';

interface PriceDisplayProps {
  price: number;
  originalPrice?: number;
  size?: 'sm' | 'md' | 'lg';
  showDiscount?: boolean;
}

export default function PriceDisplay({ 
  price, 
  originalPrice, 
  size = 'md', 
  showDiscount = true 
}: PriceDisplayProps) {
  const hasDiscount = originalPrice && originalPrice > price;
  const sizeClasses = {
    sm: 'text-lg',
    md: 'text-xl',
    lg: 'text-2xl'
  };

  return (
    <div className="flex items-baseline space-x-2">
      <span className={`font-bold text-red-600 ${sizeClasses[size]}`}>
        {formatPrice(price)}
      </span>
      
      {hasDiscount && (
        <>
          <span className="text-gray-500 line-through text-sm">
            {formatPrice(originalPrice)}
          </span>
          {showDiscount && (
            <span className="text-xs font-bold bg-red-500 text-white px-2 py-1 rounded">
              -{getDiscountPercentage(originalPrice, price)}%
            </span>
          )}
        </>
      )}
    </div>
  );
}