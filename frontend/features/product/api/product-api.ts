// frontend/features/product/api/product-api.ts
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8001/api/v1";

import { Product, ProductListResponse, ImportResults, ImportResponse, FiltersResponse } from '@/types/api';






// Error handling utility
class APIError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'APIError';
  }
}

const handleResponse = async (response: Response) => {
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new APIError(response.status, errorData.detail || `HTTP error! status: ${response.status}`);
  }
  return response.json();
};

const handleFileResponse = async (response: Response) => {
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new APIError(response.status, errorData.detail || `HTTP error! status: ${response.status}`);
  }
  return response.blob();
};

// Product API functions
export const productAPI = {
  // Get products with filters
  getProducts: async (params?: {
    skip?: number;
    limit?: number;
    category?: string;
    subcategory?: string;
    gender?: string;
    style?: string;
    fashion_style?: string;
    material?: string;
    brand?: string;
    origin?: string;
    min_price?: number;
    max_price?: number;
    min_rating?: number;
    is_active?: boolean;
    has_deposit?: boolean;
  }): Promise<ProductListResponse> => {
    const searchParams = new URLSearchParams();
    
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') {
          searchParams.append(key, value.toString());
        }
      });
    }

    const url = `${API_BASE}/products/?${searchParams}`;
    const response = await fetch(url);
    return handleResponse(response);
  },

  // Search products
  searchProducts: async (query: string, skip: number = 0, limit: number = 50): Promise<ProductListResponse> => {
    const url = `${API_BASE}/products/search/?q=${encodeURIComponent(query)}&skip=${skip}&limit=${limit}`;
    const response = await fetch(url);
    return handleResponse(response);
  },

  // Get product by ID
  getProductById: async (id: number): Promise<Product> => {
    const response = await fetch(`${API_BASE}/products/${id}`);
    return handleResponse(response);
  },

  // Get product by product_id
  getProductByProductId: async (productId: string): Promise<Product> => {
    const response = await fetch(`${API_BASE}/products/product-id/${encodeURIComponent(productId)}`);
    return handleResponse(response);
  },

  // Get product by slug
  getProductBySlug: async (slug: string): Promise<Product> => {
    const response = await fetch(`${API_BASE}/products/slug/${encodeURIComponent(slug)}`);
    return handleResponse(response);
  },

  // Create product
  createProduct: async (product: Omit<Product, 'id' | 'created_at' | 'updated_at'>): Promise<Product> => {
    const response = await fetch(`${API_BASE}/products/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(product),
    });
    return handleResponse(response);
  },

  // Update product
  updateProduct: async (id: number, product: Partial<Product>): Promise<Product> => {
    const response = await fetch(`${API_BASE}/products/${id}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(product),
    });
    return handleResponse(response);
  },

  // Delete product
  deleteProduct: async (id: number): Promise<void> => {
    const response = await fetch(`${API_BASE}/products/${id}`, {
      method: 'DELETE',
    });
    await handleResponse(response);
  },

  // Bulk update products
  bulkUpdateProducts: async (productIds: number[], updateData: Partial<Product>): Promise<{ updated_count: number }> => {
    const response = await fetch(`${API_BASE}/products/bulk/update/`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        product_ids: productIds,
        update_data: updateData,
      }),
    });
    return handleResponse(response);
  },
};

// Import/Export API functions
export const importExportAPI = {
  // Import products from Excel - FIXED ROUTE
  importProducts: async (file: File): Promise<ImportResponse> => {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_BASE}/import-export/import/excel`, {
      method: 'POST',
      body: formData,
    });

    return handleResponse(response);
  },

  // Export products to Excel - FIXED ROUTE
  exportProducts: async (): Promise<Blob> => {
    const response = await fetch(`${API_BASE}/import-export/export/excel`);
    return handleFileResponse(response);
  },

  // Download exported file
  downloadExportedFile: async (): Promise<void> => {
    const blob = await importExportAPI.exportProducts();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = url;
    
    // Create filename with timestamp
    const timestamp = new Date().toISOString().split('T')[0];
    a.download = `products_export_${timestamp}.xlsx`;
    
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  },
};

// Filters API functions
export const filtersAPI = {
  // Get all filters
  getAllFilters: async (): Promise<FiltersResponse> => {
    const response = await fetch(`${API_BASE}/products/filters/all/`);
    return handleResponse(response);
  },

  // Get categories
  getCategories: async (): Promise<{ categories: string[] }> => {
    const response = await fetch(`${API_BASE}/products/filters/categories/`);
    return handleResponse(response);
  },

  // Get brands
  getBrands: async (): Promise<{ brands: string[] }> => {
    const response = await fetch(`${API_BASE}/products/filters/brands/`);
    return handleResponse(response);
  },

  // Get materials
  getMaterials: async (): Promise<{ materials: string[] }> => {
    const response = await fetch(`${API_BASE}/products/filters/materials/`);
    return handleResponse(response);
  },

  // Get styles
  getStyles: async (): Promise<{ styles: string[] }> => {
    const response = await fetch(`${API_BASE}/products/filters/styles/`);
    return handleResponse(response);
  },

  // Get fashion styles
  getFashionStyles: async (): Promise<{ fashion_styles: string[] }> => {
    const response = await fetch(`${API_BASE}/products/filters/fashion-styles/`);
    return handleResponse(response);
  },

  // Get genders
  getGenders: async (): Promise<{ genders: string[] }> => {
    const response = await fetch(`${API_BASE}/products/filters/genders/`);
    return handleResponse(response);
  },

  // Get origins
  getOrigins: async (): Promise<{ origins: string[] }> => {
    const response = await fetch(`${API_BASE}/products/filters/origins/`);
    return handleResponse(response);
  },

  // Get occasions
  getOccasions: async (): Promise<{ occasions: string[] }> => {
    const response = await fetch(`${API_BASE}/products/filters/occasions/`);
    return handleResponse(response);
  },
};

// Categories API functions
export const categoriesAPI = {
  getCategories: async (): Promise<any> => {
    const response = await fetch(`${API_BASE}/categories/`);
    return handleResponse(response);
  },

  getCategory: async (id: number): Promise<any> => {
    const response = await fetch(`${API_BASE}/categories/${id}`);
    return handleResponse(response);
  },

  getCategoryBySlug: async (slug: string): Promise<any> => {
    const response = await fetch(`${API_BASE}/categories/slug/${slug}`);
    return handleResponse(response);
  },
};

// Utility function for API health check
export const healthCheck = async (): Promise<{ status: string; service: string }> => {
  const response = await fetch(`${API_BASE.replace('/api/v1', '')}/health`);
  return handleResponse(response);
};

// Utility function to check if API is reachable
export const checkAPIStatus = async (): Promise<boolean> => {
  try {
    await healthCheck();
    return true;
  } catch {
    return false;
  }
};

export default {
  product: productAPI,
  importExport: importExportAPI,
  filters: filtersAPI,
  categories: categoriesAPI,
  healthCheck,
  checkAPIStatus,
};