import type { MetadataRoute } from "next";
import { APP_WEB_ICON_URL } from "@/lib/app-web-icon";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "188.COM.VN - Xem là thích click là mê",
    short_name: "188",
    description:
      "188.COM.VN — Xem là thích click là mê. Thời trang nam nữ, giày dép, phụ kiện và nhiều ngành hàng khác.",
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
