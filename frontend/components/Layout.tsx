// frontend/components/Layout.tsx - UPDATED WITH 70% SIZE
'use client';

import { ReactNode, useState } from 'react';
import Header from './Header';
import Footer from './Footer';
import Navigation from './Navigation';

interface LayoutProps {
  children: ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  const [cartItemsCount, setCartItemsCount] = useState(0);
  const [favoriteItemsCount, setFavoriteItemsCount] = useState(0);
  const [selectedFilter, setSelectedFilter] = useState<{
    category?: string;
    subcategory?: string;
    sub_subcategory?: string;
  }>({});

  // Xử lý search tập trung cho toàn bộ app
  const handleSearch = (searchTerm: string) => {
    console.log('🔍 Search tập trung:', searchTerm);
  };

  // Danh mục 3 cấp: category (AB), subcategory (AC), sub_subcategory (AD)
  const handleCategoryChange = (
    category: string,
    subcategory?: string,
    sub_subcategory?: string
  ) => {
    if (!category) {
      setSelectedFilter({});
      return;
    }
    setSelectedFilter({
      category,
      ...(subcategory && { subcategory }),
      ...(sub_subcategory && { sub_subcategory }),
    });
  };

  // Các hàm xử lý cart/favorite (có thể mở rộng sau)
  const handleAddToCart = () => {
    setCartItemsCount(prev => prev + 1);
  };

  const handleAddToFavorite = () => {
    setFavoriteItemsCount(prev => prev + 1);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header - CHỈ RENDER 1 LẦN DUY NHẤT */}
      <Header 
        onSearch={handleSearch}
        cartItemsCount={cartItemsCount}
        favoriteItemsCount={favoriteItemsCount}
      />
      
      {/* Navigation - CHỈ RENDER 1 LẦN DUY NHẤT */}
      <Navigation 
        selectedFilter={selectedFilter}
        onCategoryChange={handleCategoryChange}
      />

      {/* Main content với container 70% width */}
      <main className="flex-1">
        <div className="max-w-5xl mx-auto px-4"> {/* Giảm từ max-w-7xl xuống max-w-5xl (khoảng 70%) */}
          {children}
        </div>
      </main>

      {/* Footer - CHỈ RENDER 1 LẦN DUY NHẤT */}
      <Footer />
    </div>
  );
}