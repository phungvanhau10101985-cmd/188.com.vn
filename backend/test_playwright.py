import asyncio
from playwright.async_api import async_playwright
import sys
import io
import json

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://pandamall.vn/1688/detail/935969699245", wait_until="networkidle")
        
        imgs = await page.evaluate('''() => {
            const els = [...document.querySelectorAll("img")];
            return els.slice(0, 40).map(img => {
                return {
                    src: img.src,
                    className: img.className,
                    parentClass: img.parentElement ? img.parentElement.className : "",
                    gpClass: img.parentElement && img.parentElement.parentElement ? img.parentElement.parentElement.className : ""
                };
            });
        }''')
        print(json.dumps(imgs, indent=2))
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
