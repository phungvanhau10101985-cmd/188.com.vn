export default function ProductSkeleton() {
  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden animate-pulse">
      {/* Image Skeleton */}
      <div className="aspect-square bg-gray-300" />
      
      {/* Content Skeleton */}
      <div className="p-4 space-y-3">
        {/* Brand Skeleton */}
        <div className="flex justify-between">
          <div className="h-4 bg-gray-300 rounded w-16" />
          <div className="h-4 bg-gray-300 rounded w-12" />
        </div>
        
        {/* Title Skeleton */}
        <div className="space-y-2">
          <div className="h-4 bg-gray-300 rounded w-full" />
          <div className="h-4 bg-gray-300 rounded w-3/4" />
        </div>
        
        {/* Price Skeleton */}
        <div className="space-y-1">
          <div className="h-6 bg-gray-300 rounded w-20" />
          <div className="h-3 bg-gray-300 rounded w-24" />
        </div>
        
        {/* Stats Skeleton */}
        <div className="flex justify-between">
          <div className="h-3 bg-gray-300 rounded w-16" />
          <div className="h-3 bg-gray-300 rounded w-12" />
        </div>
        
        {/* Button Skeleton */}
        <div className="h-12 bg-gray-300 rounded-lg" />
      </div>
    </div>
  );
}