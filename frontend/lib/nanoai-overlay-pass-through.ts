const ROOT_SELECTORS = [
  '#nanoai-chat-widget-v1',
  '[id^="nanoai-chat-widget"]',
  '[id*="nanoai-chat-widget"]',
];

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

/** Container NanoAI full-screen không nuốt tap trang — chỉ phần tử tương tác nhận click. */
export function releaseNanoAiClickBlockers(): void {
  if (typeof document === 'undefined') return;

  for (const sel of ROOT_SELECTORS) {
    document.querySelectorAll<HTMLElement>(sel).forEach((root) => {
      if (!isLargeFixedOverlay(root)) return;

      root.style.setProperty('pointer-events', 'none', 'important');
      root.dataset.nanoai188OverlayPass = '1';

      const stack: HTMLElement[] = [root];
      while (stack.length > 0) {
        const node = stack.pop()!;
        for (const child of Array.from(node.children)) {
          if (!(child instanceof HTMLElement)) continue;
          stack.push(child);
          if (isInteractiveNanoAiNode(child) || !isLargeFixedOverlay(child)) {
            child.style.setProperty('pointer-events', 'auto', 'important');
            child.dataset.nanoai188OverlayPass = '1';
          } else {
            child.style.setProperty('pointer-events', 'none', 'important');
            child.dataset.nanoai188OverlayPass = '1';
          }
        }
      }
    });
  }
}

export function clearNanoAiOverlayPassThrough(): void {
  if (typeof document === 'undefined') return;
  document.querySelectorAll<HTMLElement>('[data-nanoai188-overlay-pass="1"]').forEach((el) => {
    el.style.removeProperty('pointer-events');
    delete el.dataset.nanoai188OverlayPass;
  });
}
