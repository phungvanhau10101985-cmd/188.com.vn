import type { MetadataRoute } from "next";
import { APP_WEB_ICON_URL } from "@/lib/app-web-icon";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "188.COM.VN",
    short_name: "188",
    description:
      "Nền tảng thương mại điện tử 188.com.vn — thời trang nam nữ, nhiều ngành hàng khác, giày dép, phụ kiện.",
    start_url: "/",
    display: "standalone",
    background_color: "#fafafa",
    theme_color: "#ea580c",
    orientation: "portrait-primary",
    scope: "/",
    lang: "vi",
    categories: ["shopping", "fashion"],
    icons: [
      {
        src: APP_WEB_ICON_URL,
        sizes: "192x192",
        type: "image/png",
        purpose: "any",
      },
      {
        src: APP_WEB_ICON_URL,
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
