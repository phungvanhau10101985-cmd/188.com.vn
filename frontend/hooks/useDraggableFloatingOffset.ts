'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

const DRAG_THRESHOLD_PX = 12;

export type FloatingOffset = { x: number; y: number };

export function clampMeasure(el: HTMLElement, x: number, y: number): FloatingOffset {
  if (typeof window === 'undefined') return { x, y };
  const m = 10;
  const prev = el.style.transform;
  el.style.transform = `translate3d(${x}px, ${y}px, 0)`;
  const r = el.getBoundingClientRect();
  let nx = x;
  let ny = y;
  if (r.left < m) nx += m - r.left;
  if (r.right > window.innerWidth - m) nx -= r.right - (window.innerWidth - m);
  if (r.top < m) ny += m - r.top;
  if (r.bottom > window.innerHeight - m) ny -= r.bottom - (window.innerHeight - m);
  el.style.transform = prev;
  return { x: nx, y: ny };
}

/**
 * FAB / nút nổi: kéo = translate3d, nhấn nhanh = click Link vẫn chạy (sau ngưỡng kéo thì chặn click).
 */
export function useDraggableFloatingOffset(storageKey: string, enabled: boolean) {
  const [translate, setTranslate] = useState<FloatingOffset>({ x: 0, y: 0 });
  const latestRef = useRef<FloatingOffset>({ x: 0, y: 0 });

  const dragMovedRef = useRef(false);
  const sessionRef = useRef({
    active: false,
    pointerId: -1,
    startClientX: 0,
    startClientY: 0,
    originX: 0,
    originY: 0,
  });
  const targetRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!enabled) return;
    try {
      const raw = localStorage.getItem(storageKey);
      if (!raw) return;
      const p = JSON.parse(raw) as FloatingOffset;
      if (typeof p.x === 'number' && typeof p.y === 'number') {
        const v = { x: p.x, y: p.y };
        setTranslate(v);
        latestRef.current = v;
      }
    } catch {
      /* noop */
    }
  }, [storageKey, enabled]);

  const persist = useCallback(
    (t: FloatingOffset) => {
      try {
        localStorage.setItem(storageKey, JSON.stringify(t));
      } catch {
        /* noop */
      }
    },
    [storageKey]
  );

  const onPointerMove = useCallback((e: PointerEvent) => {
    const s = sessionRef.current;
    if (!s.active) return;
    const dx = e.clientX - s.startClientX;
    const dy = e.clientY - s.startClientY;
    if (Math.hypot(dx, dy) >= DRAG_THRESHOLD_PX) dragMovedRef.current = true;
    if (!dragMovedRef.current) return;
    const raw = { x: s.originX + dx, y: s.originY + dy };
    const el = targetRef.current;
    const next = el ? clampMeasure(el, raw.x, raw.y) : raw;
    latestRef.current = next;
    setTranslate(next);
  }, []);

  const endDrag = useCallback(
    (e: PointerEvent | null) => {
      const s = sessionRef.current;
      if (!s.active) return;
      s.active = false;
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', endDrag);
      window.removeEventListener('pointercancel', endDrag);
      if (dragMovedRef.current) {
        const el = targetRef.current;
        const t = latestRef.current;
        const final = el ? clampMeasure(el, t.x, t.y) : t;
        latestRef.current = final;
        setTranslate(final);
        persist(final);
        e?.preventDefault();
      }
      const el = targetRef.current;
      const pid = sessionRef.current.pointerId;
      sessionRef.current.pointerId = -1;
      if (el != null && pid >= 0) {
        try {
          if (el.hasPointerCapture(pid)) el.releasePointerCapture(pid);
        } catch {
          /* noop */
        }
      }
    },
    [onPointerMove, persist]
  );

  const onPointerDown = useCallback(
    (e: React.PointerEvent<HTMLElement>) => {
      if (!enabled || e.button !== 0) return;
      dragMovedRef.current = false;
      targetRef.current = e.currentTarget;
      const target = e.currentTarget;
      sessionRef.current = {
        active: true,
        pointerId: e.pointerId,
        startClientX: e.clientX,
        startClientY: e.clientY,
        originX: latestRef.current.x,
        originY: latestRef.current.y,
      };
      try {
        target.setPointerCapture(e.pointerId);
      } catch {
        /* noop — một số browser / shadow DOM */
      }
      window.addEventListener('pointermove', onPointerMove);
      window.addEventListener('pointerup', endDrag);
      window.addEventListener('pointercancel', endDrag);
    },
    [enabled, onPointerMove, endDrag]
  );

  const onClickCapture = useCallback((e: React.MouseEvent) => {
    if (dragMovedRef.current) {
      e.preventDefault();
      e.stopPropagation();
      dragMovedRef.current = false;
    }
  }, []);

  useEffect(() => {
    return () => endDrag(null);
  }, [endDrag]);

  const dragStyle = {
    transform: `translate3d(${translate.x}px, ${translate.y}px, 0)`,
    touchAction: 'none' as const,
    WebkitUserDrag: 'none' as const,
    userSelect: 'none' as const,
  };

  return {
    dragStyle,
    onPointerDown,
    onClickCapture,
    cursorClass: 'cursor-grab active:cursor-grabbing touch-none select-none',
  };
}
