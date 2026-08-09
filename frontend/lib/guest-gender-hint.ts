'use client';

/**
 * Cờ "đã trả lời chọn giới tính nhẹ" cho khách chưa đăng nhập — tránh hỏi lại mỗi lần
 * vào trang chủ trong cùng trình duyệt. Giá trị giới tính thật lưu server-side theo
 * `guest_session_id` (xem `apiClient.setGuestProfileHint`) — cờ này chỉ là UI state.
 */
const ANSWERED_KEY = '188_guest_gender_hint_answered';

export function hasAnsweredGuestGenderHint(): boolean {
  if (typeof window === 'undefined') return true;
  try {
    return localStorage.getItem(ANSWERED_KEY) === '1';
  } catch {
    return false;
  }
}

export function markGuestGenderHintAnswered(): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(ANSWERED_KEY, '1');
  } catch {
    /* ignore */
  }
}

export function resetGuestGenderHintAnswered(): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.removeItem(ANSWERED_KEY);
  } catch {
    /* ignore */
  }
}
