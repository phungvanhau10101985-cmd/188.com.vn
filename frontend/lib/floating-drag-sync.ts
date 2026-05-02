/** Kéo nút video FAB → các launcher nhúng (`DraggableThirdPartyFloaters`) nhận cùng delta đã clamp. */
export const FLOAT_EMBED_SYNC_MOVE = '188-float-embed-sync-move';

/** Sau khi thả nút video — lưu offset launcher vào localStorage. */
export const FLOAT_EMBED_SYNC_END = '188-float-embed-sync-end';

export type FloatEmbedSyncMoveDetail = { dx: number; dy: number };
