/** Giữ số hữu ích đang hiện trên đánh giá import khi bấm Hữu ích (số đó là số hiển thị theo sản phẩm, không phải số trong DB). */
export function mergeReviewUsefulToggle<
  T extends { useful?: number; user_has_voted?: boolean | null; is_imported?: boolean },
>(review: T, res: { useful: number; user_has_voted: boolean }): T {
  if (review.is_imported) {
    const delta = Boolean(res.user_has_voted) === Boolean(review.user_has_voted) ? 0 : res.user_has_voted ? 1 : -1;
    return {
      ...review,
      useful: Math.max(0, (review.useful || 0) + delta),
      user_has_voted: res.user_has_voted,
    };
  }
  return { ...review, useful: res.useful, user_has_voted: res.user_has_voted };
}
