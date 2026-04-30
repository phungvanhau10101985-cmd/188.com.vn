import type { MetadataRoute } from "next";

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
        src: "https://188comvn.b-cdn.net/logo188.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "https://188comvn.b-cdn.net/logo188.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
