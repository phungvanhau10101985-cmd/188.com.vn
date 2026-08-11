import CategoryRouteLoading from '@/components/category/CategoryRouteLoading';

/** Hiện ngay khi chuyển route /danh-muc — trước khi SSR page xong. */
export default function DanhMucLoading() {
  return <CategoryRouteLoading message="Đang tải danh mục…" />;
}
