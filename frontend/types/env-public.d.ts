/** Biến NEXT_PUBLIC_* — gợi ý cho IDE; giá trị thật trong frontend/.env(.local) */

declare namespace NodeJS {
  interface ProcessEnv {
    NEXT_PUBLIC_CDN_URL?: string;
    NEXT_PUBLIC_SITE_URL?: string;
    NEXT_PUBLIC_DOMAIN?: string;
    NEXT_PUBLIC_API_BASE_URL?: string;
    NEXT_PUBLIC_SEPAY_CONTENT_PREFIX?: string;
  }
}

export {};
