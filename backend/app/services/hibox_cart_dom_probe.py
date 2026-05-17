"""Playwright-eval (ES5-ish): PDP Hibox có CTA giỏ hàng không.

Bar cố định / dock: `#addCartBtn`, `button.add-cart-btn`, hay text/aria chứa «Сагслах»
(hỗn hợp hoa–thường như trong `aria-label` thật) hoặc «САГСЛАХ».
"""

from __future__ import annotations

HIBOX_CART_CTA_PROBE_JS = r"""() => {
  try {
    if (document.querySelector('#addCartBtn')) {
      return true;
    }
    if (document.querySelector('button.add-cart-btn')) {
      return true;
    }
    /** «САГСЛАХ» và «Сагслах» (đúng các dạng thường gặp trên PDP/bản aria). */
    var needleCaps = '\u0421\u0410\u0413\u0421\u041b\u0410\u0425';
    var needleMix = '\u0421\u0430\u0433\u0441\u043b\u0430\u0445';
    function hasCartWord(txt) {
      var x = String(txt || '');
      if (x.indexOf(needleCaps) !== -1) return true;
      if (x.indexOf(needleMix) !== -1) return true;
      return false;
    }

    var labIdx;
    var labNodes = document.querySelectorAll('[aria-label]');
    for (labIdx = 0; labIdx < labNodes.length; labIdx++) {
      var al = '';
      try {
        al = labNodes[labIdx].getAttribute ? labNodes[labIdx].getAttribute('aria-label') || '' : '';
      } catch (e1) {
        al = '';
      }
      if (hasCartWord(al)) return true;
    }

    var nodes = document.querySelectorAll('button,[role="button"],a');
    var i;
    var el;
    var tBody;
    for (i = 0; i < nodes.length; i++) {
      el = nodes[i];
      tBody = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
      if (hasCartWord(tBody)) return true;
    }
    return false;
  } catch (e0) {
    return false;
  }
}"""
