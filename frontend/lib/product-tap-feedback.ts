/**
 * Phản hồi bấm sản phẩm trên iOS/Android: hiện ngay khi chạm,
 * giữ đến khi thẻ rời DOM (trang sản phẩm bắt đầu mở) hoặc quá 15 giây.
 * Node gắn vào document.body để không bị React ghi đè class lúc điều hướng.
 */

const CHIP_ID = 'product-tap-ack';
const VEIL_ID = 'product-tap-veil';
const HOLD_MS = 140;
const MAX_MS = 15000;
const MOVE_PX = 12;
const MIN_VEIL = 72;

type Session = {
  host: HTMLElement;
  frame: number;
  started: number;
  /** true sau khi thả tay (đúng một cú bấm), không phải lúc mới chạm. */
  committed: boolean;
};

type Gesture = {
  pointerId: number;
  host: HTMLElement;
  x: number;
  y: number;
  moved: boolean;
};

let session: Session | null = null;
let gesture: Gesture | null = null;
let holdTimer = 0;
let installed = false;

function isProductNavigationHref(href: string): boolean {
  if (window.location.pathname.startsWith('/admin')) return false;
  let url: URL;
  try {
    url = new URL(href, window.location.href);
  } catch {
    return false;
  }
  if (url.origin !== window.location.origin) return false;
  if (!/^\/products\/[^/]+/.test(url.pathname)) return false;
  if (url.pathname === window.location.pathname && url.search === window.location.search) return false;
  return true;
}

function findProductAnchor(target: EventTarget | null): HTMLAnchorElement | null {
  if (!(target instanceof Element)) return null;
  if (target.closest('button, input, textarea, select, label, [data-no-product-tap]')) return null;
  const anchor = target.closest('a[href]');
  if (!(anchor instanceof HTMLAnchorElement)) return null;
  if (anchor.target === '_blank') return null;
  if (!isProductNavigationHref(anchor.href)) return null;
  return anchor;
}

function hostForAnchor(anchor: HTMLAnchorElement): HTMLElement {
  return (
    (anchor.closest('.product-card') as HTMLElement | null) ||
    (anchor.closest('article') as HTMLElement | null) ||
    anchor
  );
}

function hostFrom(el: HTMLElement): HTMLElement {
  return (el.closest('[data-product-tap-host]') as HTMLElement | null) || el;
}

function ensureChip(): HTMLElement {
  let chip = document.getElementById(CHIP_ID);
  if (!chip) {
    chip = document.createElement('div');
    chip.id = CHIP_ID;
    chip.className = 'product-tap-ack';
    chip.setAttribute('role', 'status');
    chip.setAttribute('aria-live', 'polite');
    chip.innerHTML =
      '<span class="product-tap-ack-spin" aria-hidden="true"></span><span>Đang mở sản phẩm…</span>';
    document.body.appendChild(chip);
  }
  return chip;
}

function ensureVeil(): HTMLElement {
  let veil = document.getElementById(VEIL_ID);
  if (!veil) {
    veil = document.createElement('div');
    veil.id = VEIL_ID;
    veil.className = 'product-tap-veil';
    veil.setAttribute('aria-hidden', 'true');
    veil.innerHTML = '<span>Đang mở…</span>';
    document.body.appendChild(veil);
  }
  return veil;
}

function placeVeil(veil: HTMLElement, host: HTMLElement) {
  const rect = host.getBoundingClientRect();
  if (rect.width < MIN_VEIL || rect.height < MIN_VEIL) {
    veil.style.display = 'none';
    return;
  }
  veil.style.display = 'flex';
  veil.style.top = `${rect.top}px`;
  veil.style.left = `${rect.left}px`;
  veil.style.width = `${rect.width}px`;
  veil.style.height = `${rect.height}px`;
}

function clearHoldTimer() {
  if (!holdTimer) return;
  window.clearTimeout(holdTimer);
  holdTimer = 0;
}

export function clearProductTapFeedback() {
  clearHoldTimer();
  if (session) {
    window.cancelAnimationFrame(session.frame);
    session.host.removeAttribute('data-product-tap-pressed');
    session = null;
  }
  document.getElementById(CHIP_ID)?.remove();
  document.getElementById(VEIL_ID)?.remove();
}

function watch(host: HTMLElement) {
  const tick = () => {
    if (!session || session.host !== host) return;
    const veil = document.getElementById(VEIL_ID);
    if (!host.isConnected || performance.now() - session.started > MAX_MS) {
      clearProductTapFeedback();
      return;
    }
    if (veil) placeVeil(veil, host);
    session.frame = window.requestAnimationFrame(tick);
  };
  session!.frame = window.requestAnimationFrame(tick);
}

function openSession(host: HTMLElement, committed: boolean) {
  if (session?.host === host) {
    session.committed = session.committed || committed;
    host.setAttribute('data-product-tap-pressed', '');
    return;
  }
  clearProductTapFeedback();
  host.setAttribute('data-product-tap-pressed', '');
  const chip = ensureChip();
  const veil = ensureVeil();
  placeVeil(veil, host);
  // Ép layout để iOS kịp vẽ lớp phản hồi trước khi click/router chiếm luồng chính.
  void chip.offsetWidth;
  session = {
    host,
    frame: 0,
    started: performance.now(),
    committed,
  };
  watch(host);
}

/** Gọi từ chỗ mở sản phẩm không phải thẻ `<a>` (ví dụ dòng trong giỏ). */
export function markProductTap(from: HTMLElement) {
  openSession(hostFrom(from), true);
}

function onPointerDown(event: PointerEvent) {
  if (event.pointerType === 'mouse' && event.button !== 0) return;
  const anchor = findProductAnchor(event.target);
  if (!anchor) return;
  const host = hostForAnchor(anchor);
  gesture = {
    pointerId: event.pointerId,
    host,
    x: event.clientX,
    y: event.clientY,
    moved: false,
  };
  host.setAttribute('data-product-tap-pressed', '');
  clearHoldTimer();
  holdTimer = window.setTimeout(() => {
    holdTimer = 0;
    if (!gesture || gesture.moved || gesture.host !== host) return;
    openSession(host, false);
  }, HOLD_MS);
}

function onPointerMove(event: PointerEvent) {
  if (!gesture || event.pointerId !== gesture.pointerId || gesture.moved) return;
  const dx = event.clientX - gesture.x;
  const dy = event.clientY - gesture.y;
  if (dx * dx + dy * dy < MOVE_PX * MOVE_PX) return;
  gesture.moved = true;
  clearHoldTimer();
  gesture.host.removeAttribute('data-product-tap-pressed');
  if (session && !session.committed && session.host === gesture.host) {
    clearProductTapFeedback();
  }
}

function onPointerUp(event: PointerEvent) {
  if (!gesture || event.pointerId !== gesture.pointerId) return;
  const current = gesture;
  gesture = null;
  clearHoldTimer();
  if (current.moved) {
    current.host.removeAttribute('data-product-tap-pressed');
    return;
  }
  openSession(current.host, true);
}

function onPointerCancel(event: PointerEvent) {
  if (!gesture || event.pointerId !== gesture.pointerId) return;
  const current = gesture;
  gesture = null;
  clearHoldTimer();
  if (session && !session.committed && session.host === current.host) {
    clearProductTapFeedback();
    return;
  }
  current.host.removeAttribute('data-product-tap-pressed');
}

function onClick(event: MouseEvent) {
  if (event.defaultPrevented || event.button !== 0) return;
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
    clearProductTapFeedback();
    return;
  }
  const anchor = findProductAnchor(event.target);
  if (!anchor) return;
  openSession(hostForAnchor(anchor), true);
}

function onKeyDown(event: KeyboardEvent) {
  if (event.key !== 'Enter' && event.key !== ' ') return;
  if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) return;
  const anchor = findProductAnchor(event.target);
  if (!anchor) return;
  openSession(hostForAnchor(anchor), true);
}

export function installProductTapFeedback(): () => void {
  if (installed || typeof document === 'undefined') return () => {};
  installed = true;
  document.addEventListener('pointerdown', onPointerDown, true);
  document.addEventListener('pointermove', onPointerMove, true);
  document.addEventListener('pointerup', onPointerUp, true);
  document.addEventListener('pointercancel', onPointerCancel, true);
  document.addEventListener('click', onClick, false);
  document.addEventListener('keydown', onKeyDown, true);
  return () => {
    installed = false;
    gesture = null;
    clearProductTapFeedback();
    document.removeEventListener('pointerdown', onPointerDown, true);
    document.removeEventListener('pointermove', onPointerMove, true);
    document.removeEventListener('pointerup', onPointerUp, true);
    document.removeEventListener('pointercancel', onPointerCancel, true);
    document.removeEventListener('click', onClick, false);
    document.removeEventListener('keydown', onKeyDown, true);
  };
}
