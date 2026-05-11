import { revalidateTag } from "next/cache";
import { NextResponse } from "next/server";
import { CACHE_TAG_CATEGORY_SEO } from "@/lib/category-seo";

/**
 * POST /api/clear-cache
 * Xóa cache danh mục/sản phẩm (fetch cache có tag category-seo).
 * Trên production (Nginx proxy /api/* → FastAPI), UI admin gọi POST /admin/clear-cache thay cho route này.
 */
export async function POST() {
  try {
    revalidateTag(CACHE_TAG_CATEGORY_SEO, "max");
    return NextResponse.json({
      ok: true,
      message: "Đã xóa sạch cache danh mục và sản phẩm.",
    });
  } catch (e) {
    console.error("clear-cache error:", e);
    return NextResponse.json(
      { ok: false, message: "Lỗi xóa cache." },
      { status: 500 }
    );
  }
}
