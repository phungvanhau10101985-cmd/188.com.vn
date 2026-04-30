import { revalidateTag } from "next/cache";
import { NextResponse } from "next/server";
import { CACHE_TAG_CATEGORY_SEO } from "@/lib/category-seo";

/**
 * POST /admin/clear-cache
 * Tránh xung đột với Nginx: `location /api/` thường proxy hết sang FastAPI → /api/clear-cache
 * không tới được Next. Đường dẫn /admin/* đi qua `location /` tới Next.
 */
export async function POST() {
  try {
    revalidateTag(CACHE_TAG_CATEGORY_SEO);
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
