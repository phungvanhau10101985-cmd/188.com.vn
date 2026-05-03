import type { ProductQuestionItem, ProductReviewItem } from '@/types/api';

/**
 * Đánh giá: có user_id (đánh giá sau mua qua shop) hoặc đánh giá import có nội dung hiển thị.
 */
export function reviewShowsVerifiedPurchaserBadge(r: ProductReviewItem): boolean {
  if (r.user_id != null && r.user_id !== undefined) return true;
  return Boolean(r.is_imported && (r.content ?? '').trim());
}

/**
 * Trả lời Q&A — người mua: có user id (reply qua shop) hoặc dòng QA import (excel) có nội dung buyer.
 * Không dùng cho dòng “X hỏi:” — đặt câu hỏi chỉ cần đăng nhập, không chứng minh đã mua.
 */
export function qaSlotShowsVerifiedPurchaserBadge(q: ProductQuestionItem, slot: 1 | 2): boolean {
  if (slot === 1) {
    if (q.reply_user_one_id != null && q.reply_user_one_id !== undefined) return true;
    return Boolean(q.is_imported && (q.reply_user_one_content ?? '').trim());
  }
  if (q.reply_user_two_id != null && q.reply_user_two_id !== undefined) return true;
  return Boolean(q.is_imported && (q.reply_user_two_content ?? '').trim());
}
