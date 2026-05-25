export type CartAddCloseMode = 'nanoai' | 'back' | 'product' | 'path';

export function parseCartAddCloseMode(
  rawReturn?: string | null,
  fromNanoAi?: boolean,
): { mode: CartAddCloseMode; path?: string } {
  const v = (rawReturn || '').trim();
  const lower = v.toLowerCase();

  if (lower === 'nanoai' || lower === 'chat') return { mode: 'nanoai' };
  if (lower === 'back') return { mode: 'back' };
  if (lower === 'product' || lower === 'pdp') return { mode: 'product' };
  if (v.startsWith('/') && !v.startsWith('//')) return { mode: 'path', path: v };

  if (fromNanoAi) return { mode: 'nanoai' };

  // Mặc định trang landing từ chat: đóng → về khung NanoAI
  return { mode: 'nanoai' };
}
