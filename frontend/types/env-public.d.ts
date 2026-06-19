/** Biến NEXT_PUBLIC_* — gợi ý cho IDE; giá trị thật trong frontend/.env(.local) */

declare namespace NodeJS {
  interface ProcessEnv {
    NEXT_PUBLIC_CDN_URL?: string;
    NEXT_PUBLIC_SITE_URL?: string;
    NEXT_PUBLIC_DOMAIN?: string;
    NEXT_PUBLIC_API_BASE_URL?: string;
    /** Dev: origin FastAPI chỉ để ghép `/static/...` khi API qua `/api/v1` cùng host Next (proxy). Mặc định trong code là http://127.0.0.1:8001 */
    NEXT_PUBLIC_FASTAPI_ORIGIN?: string;
    /** Base `/api/v1` công khai cho feed TSV catalogue (Google / Meta / TikTok), ví dụ `https://api.example.com/api/v1` */
    NEXT_PUBLIC_CATALOG_FEED_API_BASE_URL?: string;
    /** Merchant Center ID — CwCD + xác thực pv2 client (khớp backend GOOGLE_MERCHANT_CENTER_ID) */
    NEXT_PUBLIC_GOOGLE_MERCHANT_CENTER_ID?: string;
    NEXT_PUBLIC_GOOGLE_FEED_COUNTRY?: string;
    NEXT_PUBLIC_GOOGLE_FEED_LANGUAGE?: string;
    NEXT_PUBLIC_GOOGLE_FEED_CURRENCY?: string;
    NEXT_PUBLIC_SEPAY_CONTENT_PREFIX?: string;
    NEXT_PUBLIC_SEPAY_CONTENT_SUFFIX_MIN_LENGTH?: string;
    NEXT_PUBLIC_SEPAY_CONTENT_SUFFIX_MAX_LENGTH?: string;
    /** Trùng backend — route `/api/report-broken-product-media` (server-only) */
    BROKEN_MEDIA_PURGE_SECRET?: string;
  }
}

export {};
