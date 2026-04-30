// app/layout.tsx - HOÀN CHỈNH
import type { Metadata, Viewport } from "next";
import { Suspense } from "react";
import { Inter, Roboto_Mono } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/features/auth/hooks/useAuth";
import { CartProvider } from "@/features/cart/hooks/useCart";
import { FavoriteProvider } from "@/features/favorites/hooks/useFavorites";
import AppShell from "@/components/AppShell";
import SiteEmbedsRoot from "@/components/SiteEmbedsRoot";
import AnalyticsTracker from "@/components/AnalyticsTracker";
import { fetchPublicSiteEmbeds } from "@/lib/site-embeds-public";
import { ToastProvider } from "@/components/ToastProvider";
import PwaPushRegister from "@/components/PwaPushRegister";
import { getCategoryTreeForLayout } from "@/lib/category-seo";

/** Origin cho metadata (OG, icons). Luôn có scheme — `new URL("188.com.vn")` throw → SSR 500 / trắng trang nếu env prod thiếu https:// */
function normalizeAbsoluteSiteUrl(raw: string): string {
  const t = raw.trim();
  if (!t) return "https://188.com.vn";
  if (/^https?:\/\//i.test(t)) return t;
  return `https://${t.replace(/^\/+/, "")}`;
}

const METADATA_BASE_URL = normalizeAbsoluteSiteUrl(
  process.env.NEXT_PUBLIC_SITE_URL?.trim() ||
    process.env.NEXT_PUBLIC_DOMAIN?.trim() ||
    (process.env.NODE_ENV === "development"
      ? "http://localhost:3001"
      : "https://188.com.vn")
);

const inter = Inter({
  subsets: ["latin", "vietnamese"],
  display: "swap",
  variable: "--font-inter",
});

const robotoMono = Roboto_Mono({
  subsets: ["latin", "vietnamese"],
  display: "swap",
  variable: "--font-roboto-mono",
  weight: ["400"],
});

// Fonts: next/font — tối ưu tải, giảm CSS chặn render và CLS so với @fontsource toàn trang.

// Viewport configuration cho PWA ready
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#ea580c",
};

// Metadata với SEO optimization
export const metadata: Metadata = {
  title: {
    template: "%s | 188.COM.VN",
    default: "188.COM.VN - Nền tảng TMĐT số 1 Việt Nam",
  },
  description: "188.COM.VN - Nền tảng thương mại điện tử hàng đầu Việt Nam. Thời trang nam cao cấp, giày dép, phụ kiện chính hãng.",
  keywords: ["thời trang nam", "giày dép nam", "phụ kiện nam", "mua sắm online", "188.com.vn"],
  authors: [{ name: "188 Team" }],
  creator: "188.com.vn",
  publisher: "188.com.vn",
  formatDetection: {
    email: false,
    address: false,
    telephone: false,
  },
  metadataBase: new URL(METADATA_BASE_URL),
  alternates: {
    canonical: "/",
    languages: {
      "vi-VN": "/vi",
    },
  },
  openGraph: {
    type: "website",
    locale: "vi_VN",
    url: "https://188.com.vn",
    siteName: "188.COM.VN",
    title: "188.COM.VN - Nền tảng TMĐT số 1 Việt Nam",
    description: "Thời trang nam cao cấp, giày dép, phụ kiện chính hãng",
    images: [
      {
        url: "https://188comvn.b-cdn.net/logo188.png",
        width: 400,
        height: 120,
        alt: "188.COM.VN - XEM LÀ THÍCH",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "188.COM.VN - Nền tảng TMĐT số 1",
    description: "Thời trang nam cao cấp, giày dép, phụ kiện chính hãng",
    images: ["https://188comvn.b-cdn.net/logo188.png"],
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-video-preview": -1,
      "max-image-preview": "large",
      "max-snippet": -1,
    },
  },
  // Icon từ app/icon.png — Next tự thêm <link rel="icon">; /favicon.ico → rewrite sang /favicon.png trong next.config
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
  },
  other: {
    "mobile-web-app-capable": "yes",
  },
  verification: {
    google: "your-google-verification-code",
    yandex: "your-yandex-verification-code",
  },
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const initialCategoryTree = await getCategoryTreeForLayout();
  const siteEmbeds = await fetchPublicSiteEmbeds();
  return (
    <html
      lang="vi"
      className={`${inter.variable} ${robotoMono.variable}`}
      suppressHydrationWarning
    >
      <body className="antialiased font-sans bg-[#fafafa] text-gray-900 min-h-screen" suppressHydrationWarning>
        <SiteEmbedsRoot embeds={siteEmbeds} />
        {/* Global Providers + Header/Footer xuyên suốt */}
        <ToastProvider>
          <AuthProvider>
            <PwaPushRegister />
            <CartProvider>
              <FavoriteProvider>
                <Suspense fallback={<div className="min-h-screen bg-gray-50" />}>
                  <AppShell initialCategoryTree={initialCategoryTree}>
                    <Suspense fallback={null}>
                      <AnalyticsTracker />
                    </Suspense>
                    <Suspense
                      fallback={
                        <div
                          className="min-h-[50vh] bg-gray-50"
                          aria-busy="true"
                          aria-label="Đang tải nội dung"
                        />
                      }
                    >
                      {children}
                    </Suspense>
                  </AppShell>
                </Suspense>
              </FavoriteProvider>
            </CartProvider>
          </AuthProvider>
        </ToastProvider>
        
      </body>
    </html>
  );
}
