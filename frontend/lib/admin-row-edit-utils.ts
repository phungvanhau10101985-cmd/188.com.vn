/** Giữ lại ô đang sửa nếu khách vẫn gõ trong lúc auto-save. */
export function pruneRowEditAfterSave<T extends Record<string, unknown>>(
  edit: Partial<T> | undefined,
  saved: T,
  keys: readonly (keyof T)[],
): Partial<T> {
  if (!edit) return {};
  const pruned: Partial<T> = {};
  for (const key of keys) {
    if (!(key in edit)) continue;
    if (edit[key] !== saved[key]) {
      pruned[key] = edit[key];
    }
  }
  return pruned;
}
