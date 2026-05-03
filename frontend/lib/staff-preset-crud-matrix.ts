/** Hiển thị ô ✓ / — trong bảng preset quyền. */

export function crudCell(ok: boolean): string {
  return ok ? '✓' : '—';
}
