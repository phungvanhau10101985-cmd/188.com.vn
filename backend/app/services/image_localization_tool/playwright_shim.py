# playwright_shim.py — lớp tương thích Selenium tối thiểu cho gemini_processor (nền Playwright).
from __future__ import annotations

import os
from typing import Any, List, Optional

from playwright.sync_api import BrowserContext, Locator, Page, Playwright, sync_playwright


class By:
    XPATH = "xpath"


class Keys:
    """Mã phím tương thích Selenium (W3C WebDriver)."""

    NULL = "\ue000"
    RETURN = "\ue006"
    ENTER = "\ue007"
    CONTROL = "\ue009"
    ESCAPE = "\ue00c"
    END = "\ue010"


class WebDriverException(Exception):
    pass


class PwElement:
    def __init__(self, locator: Locator, page: Page):
        self._loc = locator
        self._page = page

    def find_elements(self, by: str, xpath: str) -> List["PwElement"]:
        if by != By.XPATH:
            raise ValueError("Chỉ hỗ trợ By.XPATH")
        child = self._loc.locator(f"xpath={xpath}")
        n = child.count()
        return [PwElement(child.nth(i), self._page) for i in range(n)]

    def find_element(self, by: str, xpath: str) -> Optional["PwElement"]:
        els = self.find_elements(by, xpath)
        return els[0] if els else None

    def is_displayed(self) -> bool:
        try:
            return self._loc.is_visible()
        except Exception:
            return False

    def is_enabled(self) -> bool:
        try:
            return self._loc.is_enabled()
        except Exception:
            return False

    @property
    def text(self) -> str:
        try:
            return (self._loc.inner_text(timeout=3000) or "").strip()
        except Exception:
            return ""

    def get_attribute(self, name: str) -> Optional[str]:
        try:
            val = self._loc.evaluate(
                """(el, attr) => {
                    const a = el.getAttribute(attr);
                    if (a !== null && a !== undefined) return a;
                    const p = el[attr];
                    if (p !== undefined && p !== null) {
                        if (typeof p === 'boolean' || typeof p === 'number')
                            return String(p);
                        return p;
                    }
                    return null;
                }""",
                name,
            )
            if val is None:
                return None
            return str(val) if not isinstance(val, str) else val
        except Exception:
            return None

    @property
    def size(self) -> dict:
        try:
            box = self._loc.bounding_box()
            if box:
                return {"width": int(box["width"]), "height": int(box["height"])}
        except Exception:
            pass
        return {"width": 0, "height": 0}

    def click(self) -> None:
        self._loc.click(timeout=15000)

    def clear(self) -> None:
        try:
            self._loc.clear(timeout=5000)
        except Exception:
            try:
                self._loc.fill("")
            except Exception:
                pass

    def send_keys(self, *values: Any) -> None:
        if len(values) == 1 and isinstance(values[0], str):
            p = values[0]
            if os.path.isfile(p):
                self._loc.set_input_files(p)
                return

        self._loc.click(timeout=10000)
        i = 0
        vals = list(values)
        keymap = {
            Keys.RETURN: "Enter",
            Keys.ENTER: "Enter",
            Keys.END: "End",
            Keys.ESCAPE: "Escape",
        }
        while i < len(vals):
            v = vals[i]
            if v == Keys.CONTROL and i + 1 < len(vals):
                nxt = vals[i + 1]
                if str(nxt).lower() == "v":
                    self._page.keyboard.press("Control+v")
                    i += 2
                    continue
            if v in keymap:
                self._page.keyboard.press(keymap[v])
                i += 1
                continue
            if isinstance(v, str):
                if len(v) == 1 and 0xE000 <= ord(v) <= 0xF8FF:
                    i += 1
                    continue
                self._page.keyboard.type(v, delay=3)
            i += 1


class PwDriver:
    def __init__(self, context: BrowserContext, page: Page, playwright: Playwright):
        self.context = context
        self._page = page
        self._pw = playwright
        self._default_timeout_ms = 25000

    @property
    def current_url(self) -> str:
        return self._page.url

    def get(self, url: str) -> None:
        self._page.goto(url, wait_until="domcontentloaded", timeout=self._default_timeout_ms)

    def refresh(self) -> None:
        self._page.reload(wait_until="domcontentloaded", timeout=self._default_timeout_ms)

    def quit(self) -> None:
        try:
            self.context.close()
        except Exception:
            pass
        try:
            self._pw.stop()
        except Exception:
            pass

    def set_page_load_timeout(self, seconds: int) -> None:
        self._default_timeout_ms = max(1000, int(seconds * 1000))

    def execute_script(self, script: str, *args: Any) -> Any:
        handles: List[Any] = []
        for a in args:
            if isinstance(a, PwElement):
                handles.append(a._loc.element_handle(timeout=15000))
            else:
                handles.append(a)
        expr = (
            "(driverArgs) => {\n"
            "  const arguments = driverArgs;\n"
            f"{script}\n"
            "}"
        )
        return self._page.evaluate(expr, handles)

    def find_elements(self, by: str, xpath: str) -> List[PwElement]:
        if by != By.XPATH:
            raise ValueError("Chỉ hỗ trợ By.XPATH")
        loc = self._page.locator(f"xpath={xpath}")
        n = loc.count()
        return [PwElement(loc.nth(i), self._page) for i in range(n)]

    def find_element(self, by: str, xpath: str) -> Optional[PwElement]:
        els = self.find_elements(by, xpath)
        return els[0] if els else None

    def get_cookies(self) -> List[dict]:
        return self.context.cookies()

    def get_window_size(self) -> dict:
        vp = self._page.viewport_size
        if vp:
            return {"width": int(vp["width"]), "height": int(vp["height"])}
        return {"width": 1024, "height": 768}

    def get_window_position(self) -> dict:
        return {"x": 100, "y": 100}

    def is_enabled(self) -> bool:
        return True

    def keyboard_escape(self) -> None:
        self._page.keyboard.press("Escape")


def launch_gemini_driver(
    *,
    headless: bool,
    user_data_dir: str,
    download_dir: str,
    viewport_width: int,
    viewport_height: int,
    window_x: int,
    window_y: int,
) -> PwDriver:
    os.makedirs(download_dir, exist_ok=True)
    os.makedirs(user_data_dir, exist_ok=True)
    pw = sync_playwright().start()
    args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--disable-notifications",
        "--disable-extensions",
        f"--window-position={window_x},{window_y}",
        "--start-maximized=false",
    ]
    launch_kw: dict = {
        "user_data_dir": user_data_dir,
        "channel": "chrome",
        "headless": headless,
        "viewport": {"width": int(viewport_width), "height": int(viewport_height)},
        "args": args,
        "ignore_default_args": ["--enable-automation"],
        "accept_downloads": True,
        "downloads_path": download_dir,
    }
    try:
        context = pw.chromium.launch_persistent_context(**launch_kw)
    except Exception:
        launch_kw.pop("channel", None)
        context = pw.chromium.launch_persistent_context(**launch_kw)
    page = context.pages[0] if context.pages else context.new_page()
    return PwDriver(context, page, pw)
