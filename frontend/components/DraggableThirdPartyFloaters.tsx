'use client';

import { useEffect } from 'react';
import {
  FLOAT_EMBED_SYNC_END,
  FLOAT_EMBED_SYNC_MOVE,
  type FloatEmbedSyncMoveDetail,
} from '@/lib/floating-drag-sync';
import { clampMeasure } from '@/hooks/useDraggableFloatingOffset';

const DRAG_THRESHOLD_PX = 12;
const STORAGE_PREFIX = '188-float-offset';
const SCAN_DEBOUNCE_MS = 220;

type DragState = { x: number; y: number; storageKey: string };

const dragStates = new WeakMap<HTMLElement, DragState>();

function skipElement(el: HTMLElement): boolean {
  if (el.closest('[data-188-video-fab]')) return true;
  if (el.closest('[data-188-skip-draggable]')) return true;
  if (el.dataset.draggable188Attached === '1') return true;
  return false;
}

function looksLikeFloatingLauncher(el: HTMLElement): boolean {
  if (el.tagName === 'SCRIPT' || el.tagName === 'STYLE') return false;
  const cs = getComputedStyle(el);
  if (cs.position !== 'fixed') return false;
  if (cs.display === 'none' || cs.visibility === 'hidden' || cs.pointerEvents === 'none') return false;
  const r = el.getBoundingClientRect();
  if (r.width < 36 || r.width > 104 || r.height < 36 || r.height > 104) return false;
  const zi = parseInt(cs.zIndex, 10);
  if (cs.zIndex === 'auto' || !Number.isFinite(zi) || zi < 500) return false;
  const iw = window.innerWidth;
  const ih = window.innerHeight;
  const nearHorizontalEdge = r.left < 100 || r.right > iw - 100;
  const inBottomBand = r.top > ih * 0.36;
  return nearHorizontalEdge && inBottomBand;
}

function collectCandidates(): HTMLElement[] {
  const all = Array.from(document.body.querySelectorAll<HTMLElement>('*'));
  const candidates: HTMLElement[] = [];
  for (const el of all) {
    if (!looksLikeFloatingLauncher(el)) continue;
    if (skipElement(el)) continue;
    candidates.push(el);
  }
  return candidates.filter(
    (el) => !candidates.some((o) => o !== el && el.contains(o))
  );
}

function stableStorageId(el: HTMLElement): string {
  let id = el.getAttribute('data-188-drag-offset-key');
  if (!id) {
    id =
      typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
    el.setAttribute('data-188-drag-offset-key', id);
  }
  return `${STORAGE_PREFIX}:${id}`;
}

function loadOffset(storageKey: string): { x: number; y: number } {
  try {
    const raw = localStorage.getItem(storageKey);
    if (!raw) return { x: 0, y: 0 };
    const p = JSON.parse(raw) as { x?: unknown; y?: unknown };
    if (typeof p.x === 'number' && typeof p.y === 'number') return { x: p.x, y: p.y };
  } catch {
    /* noop */
  }
  return { x: 0, y: 0 };
}

function persistOffset(storageKey: string, o: { x: number; y: number }) {
  try {
    localStorage.setItem(storageKey, JSON.stringify(o));
  } catch {
    /* noop */
  }
}

function applyTransform(el: HTMLElement, x: number, y: number) {
  el.style.transform = `translate3d(${x}px, ${y}px, 0)`;
  el.style.touchAction = 'none';
  el.style.setProperty('-webkit-user-drag', 'none');
  el.style.userSelect = 'none';
}

/** Desktop: thẻ liên kết có href kích hoạt HTML5 drag — chặn để custom pointer-drag chạy được */
function disableNativeDragOnHost(el: HTMLElement) {
  if (el instanceof HTMLAnchorElement) el.draggable = false;
  el.addEventListener('dragstart', (ev: DragEvent) => ev.preventDefault(), true);
}

function getOrInitState(el: HTMLElement): DragState {
  let s = dragStates.get(el);
  if (s) return s;
  const storageKey = stableStorageId(el);
  const off = loadOffset(storageKey);
  s = { x: off.x, y: off.y, storageKey };
  dragStates.set(el, s);
  return s;
}

function attachDraggable(el: HTMLElement) {
  if (el.dataset.draggable188Attached === '1') return;
  el.dataset.draggable188Attached = '1';

  disableNativeDragOnHost(el);

  const state = getOrInitState(el);
  let dragMoved = false;
  let suppressClick = false;
  const session = {
    active: false,
    pointerId: -1,
    startClientX: 0,
    startClientY: 0,
    originX: 0,
    originY: 0,
  };

  applyTransform(el, state.x, state.y);

  const onPointerMove = (e: PointerEvent) => {
    if (!session.active) return;
    const dx = e.clientX - session.startClientX;
    const dy = e.clientY - session.startClientY;
    if (Math.hypot(dx, dy) >= DRAG_THRESHOLD_PX) dragMoved = true;
    if (!dragMoved) return;
    const raw = { x: session.originX + dx, y: session.originY + dy };
    const next = clampMeasure(el, raw.x, raw.y);
    state.x = next.x;
    state.y = next.y;
    applyTransform(el, next.x, next.y);
  };

  const endDrag = (e: PointerEvent | null) => {
    if (!session.active) return;
    session.active = false;
    window.removeEventListener('pointermove', onPointerMove);
    window.removeEventListener('pointerup', endDrag);
    window.removeEventListener('pointercancel', endDrag);
    const pid = session.pointerId;
    session.pointerId = -1;
    if (pid >= 0) {
      try {
        if (el.hasPointerCapture(pid)) el.releasePointerCapture(pid);
      } catch {
        /* noop */
      }
    }
    if (dragMoved) {
      suppressClick = true;
      const next = clampMeasure(el, state.x, state.y);
      state.x = next.x;
      state.y = next.y;
      applyTransform(el, next.x, next.y);
      persistOffset(state.storageKey, next);
      e?.preventDefault();
    }
    dragMoved = false;
  };

  const onPointerDown = (e: PointerEvent) => {
    if (e.button !== 0) return;
    dragMoved = false;
    session.active = true;
    session.pointerId = e.pointerId;
    session.startClientX = e.clientX;
    session.startClientY = e.clientY;
    session.originX = state.x;
    session.originY = state.y;
    try {
      el.setPointerCapture(e.pointerId);
    } catch {
      /* noop */
    }
    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', endDrag);
    window.addEventListener('pointercancel', endDrag);
  };

  const onClickCapture = (e: MouseEvent) => {
    if (suppressClick) {
      e.preventDefault();
      e.stopPropagation();
      suppressClick = false;
    }
  };

  el.addEventListener('pointerdown', onPointerDown);
  el.addEventListener('click', onClickCapture, true);
}

function scanAndAttach() {
  for (const el of collectCandidates()) {
    attachDraggable(el);
  }
}

function reclampAllAttached() {
  const attached = document.querySelectorAll<HTMLElement>('[data-draggable188-attached="1"]');
  attached.forEach((el) => {
    const s = dragStates.get(el);
    if (!s) return;
    const next = clampMeasure(el, s.x, s.y);
    s.x = next.x;
    s.y = next.y;
    persistOffset(s.storageKey, next);
    applyTransform(el, next.x, next.y);
  });
}

function onEmbedSyncMove(ev: Event) {
  const d = (ev as CustomEvent<FloatEmbedSyncMoveDetail>).detail;
  if (!d || (d.dx === 0 && d.dy === 0)) return;
  document.querySelectorAll<HTMLElement>('[data-draggable188-attached="1"]').forEach((node) => {
    const s = dragStates.get(node);
    if (!s) return;
    const next = clampMeasure(node, s.x + d.dx, s.y + d.dy);
    s.x = next.x;
    s.y = next.y;
    applyTransform(node, next.x, next.y);
  });
}

function onEmbedSyncEnd() {
  reclampAllAttached();
}

/**
 * Gắn kéo-thả cho các nút nổi bên thứ ba (chat widget, v.v.) đã inject vào DOM.
 * Heuristic: fixed, gần mép ngang + vùng đáy màn, z-index cao — không đụng nút video/data-skip.
 */
export default function DraggableThirdPartyFloaters() {
  useEffect(() => {
    let scanTimer: ReturnType<typeof setTimeout> | undefined;

    const scheduleScan = () => {
      if (scanTimer) clearTimeout(scanTimer);
      scanTimer = setTimeout(() => {
        scanTimer = undefined;
        scanAndAttach();
      }, SCAN_DEBOUNCE_MS);
    };

    const mo = new MutationObserver(scheduleScan);
    mo.observe(document.body, { childList: true, subtree: true });
    scheduleScan();

    let resizeTimer: ReturnType<typeof setTimeout> | undefined;
    const onResize = () => {
      if (resizeTimer) clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        resizeTimer = undefined;
        reclampAllAttached();
      }, 120);
    };
    window.addEventListener('resize', onResize, { passive: true });

    window.addEventListener(FLOAT_EMBED_SYNC_MOVE, onEmbedSyncMove);
    window.addEventListener(FLOAT_EMBED_SYNC_END, onEmbedSyncEnd);

    return () => {
      mo.disconnect();
      window.removeEventListener(FLOAT_EMBED_SYNC_MOVE, onEmbedSyncMove);
      window.removeEventListener(FLOAT_EMBED_SYNC_END, onEmbedSyncEnd);
      if (scanTimer) clearTimeout(scanTimer);
      window.removeEventListener('resize', onResize);
      if (resizeTimer) clearTimeout(resizeTimer);
    };
  }, []);

  return null;
}
