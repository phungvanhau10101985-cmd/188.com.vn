const ROOT_SELECTORS = [
  '#nanoai-chat-widget-v1',
  '[id^="nanoai-chat-widget"]',
  '[id*="nanoai-chat-widget"]',
];

export const NANOAI_SHOP_OVERLAY_HTML_ATTR = 'data-nanoai188-shop-overlay';

function collectNanoAiRoots(root: Document | ShadowRoot = document): HTMLElement[] {
  const out: HTMLElement[] = [];
  for (const sel of ROOT_SELECTORS) {
    root.querySelectorAll<HTMLElement>(sel).forEach((el) => out.push(el));
  }
  root.querySelectorAll('*').forEach((host) => {
    if (host instanceof Element && host.shadowRoot) {
      out.push(...collectNanoAiRoots(host.shadowRoot));
    }
  });
  return out;
}

function isLargeFixedOverlay(el: HTMLElement): boolean {
  const cs = getComputedStyle(el);
  if (cs.position !== 'fixed' && cs.position !== 'absolute') return false;
  const r = el.getBoundingClientRect();
  const vw = typeof window !== 'undefined' ? window.innerWidth : 0;
  const vh = typeof window !== 'undefined' ? window.innerHeight : 0;
  if (!vw || !vh) return false;
  return r.width >= vw * 0.72 || r.height >= vh * 0.72;
}

function isLauncherSized(el: HTMLElement): boolean {
  const r = el.getBoundingClientRect();
  if (r.width < 28 || r.height < 28) return false;
  if (r.width > 280 || r.height > 280) return false;
  return true;
}

function isInteractiveNanoAiNode(el: HTMLElement): boolean {
  const tag = el.tagName;
  if (/^(BUTTON|A|IFRAME|INPUT|TEXTAREA|SELECT)$/i.test(tag)) return true;
  const role = el.getAttribute('role');
  if (role === 'button' || role === 'dialog' || role === 'textbox') return true;
  if (el.isContentEditable) return true;
  return isLauncherSized(el);
}

function tagOverlayPass(el: HTMLElement) {
  el.dataset.nanoai188OverlayPass = '1';
}

function setShopOverlayHtmlFlag(active: boolean) {
  if (typeof document === 'undefined') return;
  if (active) {
    document.documentElement.setAttribute(NANOAI_SHOP_OVERLAY_HTML_ATTR, '1');
  } else {
    document.documentElement.removeAttribute(NANOAI_SHOP_OVERLAY_HTML_ATTR);
  }
}

function applyFullSuppress(root: HTMLElement) {
  root.style.setProperty('pointer-events', 'none', 'important');
  tagOverlayPass(root);

  const stack: HTMLElement[] = [root];
  while (stack.length > 0) {
    const node = stack.pop()!;
    for (const child of Array.from(node.children)) {
      if (!(child instanceof HTMLElement)) continue;
      stack.push(child);
      child.style.setProperty('pointer-events', 'none', 'important');
      tagOverlayPass(child);
    }
    if (node.shadowRoot) {
      node.shadowRoot.querySelectorAll<HTMLElement>('*').forEach((el) => {
        stack.push(el);
        el.style.setProperty('pointer-events', 'none', 'important');
        tagOverlayPass(el);
      });
    }
  }
}

function applyPassThrough(root: HTMLElement) {
  if (!isLargeFixedOverlay(root)) {
    for (const child of Array.from(root.children)) {
      if (child instanceof HTMLElement) applyPassThroughOnSubtree(child);
    }
    return;
  }

  root.style.setProperty('pointer-events', 'none', 'important');
  tagOverlayPass(root);

  const stack: HTMLElement[] = [root];
  while (stack.length > 0) {
    const node = stack.pop()!;
    for (const child of Array.from(node.children)) {
      if (!(child instanceof HTMLElement)) continue;
      stack.push(child);
      if (isInteractiveNanoAiNode(child) || !isLargeFixedOverlay(child)) {
        child.style.setProperty('pointer-events', 'auto', 'important');
        tagOverlayPass(child);
      } else {
        child.style.setProperty('pointer-events', 'none', 'important');
        tagOverlayPass(child);
      }
    }
  }
}

function applyPassThroughOnSubtree(el: HTMLElement) {
  if (isLargeFixedOverlay(el)) {
    applyPassThrough(el);
    return;
  }
  for (const child of Array.from(el.children)) {
    if (child instanceof HTMLElement) applyPassThroughOnSubtree(child);
  }
}

export type NanoAiOverlayReleaseMode = 'passThrough' | 'fullSuppress';

/** Khung NanoAI không chặn modal/trang shop — `fullSuppress` tắt hết (kể cả iframe) khi popup shop mở. */
export function releaseNanoAiClickBlockers(opts?: { mode?: NanoAiOverlayReleaseMode }): void {
  if (typeof document === 'undefined') return;

  const mode = opts?.mode ?? 'passThrough';
  // Luôn cập nhật cờ HTML — kể cả khi widget chưa mount / đang re-render DOM.
  // Trước đây return sớm khi roots=0 khiến `visibility:hidden` kẹt sau khi đóng popup.
  setShopOverlayHtmlFlag(mode === 'fullSuppress');

  const roots = collectNanoAiRoots();
  if (roots.length === 0) return;

  for (const root of roots) {
    if (mode === 'fullSuppress') {
      applyFullSuppress(root);
    } else {
      applyPassThrough(root);
    }
  }
}

export function clearNanoAiOverlayPassThrough(): void {
  if (typeof document === 'undefined') return;
  setShopOverlayHtmlFlag(false);
  document.querySelectorAll<HTMLElement>('[data-nanoai188-overlay-pass="1"]').forEach((el) => {
    el.style.removeProperty('pointer-events');
    delete el.dataset.nanoai188OverlayPass;
  });
}

/** Giữ trang giỏ tương tác sau khi khách chọn "Vào giỏ hàng" từ luồng NanoAI. */
export const NANOAI_CHECKOUT_ON_CART_SESSION_KEY = '188_nanoai_checkout_on_cart';

export function markNanoAiCheckoutOnCart(): void {
  if (typeof window === 'undefined') return;
  try {
    sessionStorage.setItem(NANOAI_CHECKOUT_ON_CART_SESSION_KEY, '1');
  } catch {
    /* ignore */
  }
}

export function isNanoAiCheckoutOnCart(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return sessionStorage.getItem(NANOAI_CHECKOUT_ON_CART_SESSION_KEY) === '1';
  } catch {
    return false;
  }
}

export function clearNanoAiCheckoutOnCart(): void {
  if (typeof window === 'undefined') return;
  try {
    sessionStorage.removeItem(NANOAI_CHECKOUT_ON_CART_SESSION_KEY);
  } catch {
    /* ignore */
  }
}
