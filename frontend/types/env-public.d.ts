/** Biến NEXT_PUBLIC_* — gợi ý cho IDE; giá trị thật trong frontend/.env(.local) */

declare namespace NodeJS {
  interface ProcessEnv {
    NEXT_PUBLIC_CDN_URL?: string;
    NEXT_PUBLIC_SITE_URL?: string;
    NEXT_PUBLIC_DOMAIN?: string;
    NEXT_PUBLIC_API_BASE_URL?: string;
    /** Base `/api/v1` công khai cho feed TSV catalogue (Google / Meta / TikTok), ví dụ `https://api.example.com/api/v1` */
    NEXT_PUBLIC_CATALOG_FEED_API_BASE_URL?: string;
    NEXT_PUBLIC_SEPAY_CONTENT_PREFIX?: string;
    NEXT_PUBLIC_SEPAY_CONTENT_SUFFIX_MIN_LENGTH?: string;
    NEXT_PUBLIC_SEPAY_CONTENT_SUFFIX_MAX_LENGTH?: string;
  }
}

export {};
