interface RatingStarsProps {
  rating: number;
  size?: 'sm' | 'md' | 'lg';
  showNumber?: boolean;
  reviewCount?: number;
}

export default function RatingStars({ 
  rating, 
  size = 'md', 
  showNumber = false,
  reviewCount 
}: RatingStarsProps) {
  const sizeClasses = {
    sm: 'text-sm',
    md: 'text-base',
    lg: 'text-lg'
  };

  const fullStars = Math.floor(rating);
  const hasHalfStar = rating % 1 >= 0.5;

  return (
    <div className="flex items-center space-x-2">
      <div className="flex items-center space-x-1">
        {[1, 2, 3, 4, 5].map((star) => (
          <span 
            key={star} 
            className={`text-yellow-400 ${sizeClasses[size]}`}
          >
            {star <= fullStars ? '★' : star === fullStars + 1 && hasHalfStar ? '⭐' : '☆'}
          </span>
        ))}
      </div>
      
      {showNumber && (
        <span className="font-medium text-gray-700">{rating.toFixed(1)}</span>
      )}
      
      {reviewCount !== undefined && (
        <span className="text-gray-500 text-sm">({reviewCount})</span>
      )}
    </div>
  );
}