import json
from playwright.sync_api import sync_playwright

cookie_data = """[
    {
        "domain": "janmall.vn",
        "expirationDate": 1781962152.95678,
        "hostOnly": True,
        "httpOnly": False,
        "name": "jam_access_token",
        "path": "/",
        "sameSite": "lax",
        "secure": False,
        "session": False,
        "storeId": None,
        "value": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyIjoiMzciLCJlbWFpbCI6InBodW5ndmFuaGF1MTAxMDE5ODVAZ21haWwuY29tIiwiaWF0IjoxNzgxMzU3MzUyLCJleHAiOjE3ODE5NjIxNTJ9.zkZ0K6EMg4R5tovoqM_FXG8eAV5MT6dPI-t9khxks1I"
    },
    {
        "domain": "janmall.vn",
        "expirationDate": 1784134659.127526,
        "hostOnly": True,
        "httpOnly": False,
        "name": "x-hng",
        "path": "/",
        "sameSite": None,
        "secure": False,
        "session": False,
        "storeId": None,
        "value": "lang=en-US&domain=janmall.vn"
    },
    {
        "domain": ".janmall.vn",
        "expirationDate": 1789133346,
        "hostOnly": False,
        "httpOnly": False,
        "name": "_gcl_au",
        "path": "/",
        "sameSite": None,
        "secure": False,
        "session": False,
        "storeId": None,
        "value": "1.1.927247481.1781357346"
    },
    {
        "domain": "janmall.vn",
        "expirationDate": 1782048551.882701,
        "hostOnly": True,
        "httpOnly": True,
        "name": "key",
        "path": "/",
        "sameSite": "no_restriction",
        "secure": True,
        "session": False,
        "storeId": None,
        "value": "rfp25OBRyGjUsjRgcaq77GT96uz3FR92w2DALTrK9BKH8pw5wF4M6v3r2KTLdHrxLOK4NfOV3YjPUV%2BoHRKE8LpP8EekzfUi%2Fxg41BVpscw5XVANVQoHDGj1fdxodh1RBPm6pSLvWEDf%2B1%2FPOjC4YcAzIxiAn06ep1U1CPzs%2FM2VJP5dcKo%2FHN0BRcHu4Om9TigVTxaiIlvMdfgMdP7n0T8OOUl5ZODWdlph%2BgLr92hF8nlxkJRC4Gs1lCH8REcMvtevwo2p%2Fp2iqxEZ2T4jE20izYp4cIXWtn4zcEyK%2F%2FTfgA6SxP7YOYnNiL%2BNG6pEcXF4EZLLudb3ThEu50x93g%3D%3D"
    },
    {
        "domain": ".janmall.vn",
        "expirationDate": 1816102660.750565,
        "hostOnly": False,
        "httpOnly": False,
        "name": "__sbref",
        "path": "/",
        "sameSite": None,
        "secure": False,
        "session": False,
        "storeId": None,
        "value": "tdnywajcpwjjscukpcrevnnxffyqiawcsgafpdgo"
    },
    {
        "domain": "janmall.vn",
        "expirationDate": 1782048551.882615,
        "hostOnly": True,
        "httpOnly": True,
        "name": "session",
        "path": "/",
        "sameSite": "no_restriction",
        "secure": True,
        "session": False,
        "storeId": None,
        "value": "haVHOKen%2BdT5asZ7Dk5gKvivaYpMGUJq%2FNcZjXc674OuX3oiVWgHxqAOU9Is604MAOBCMzrHBy%2FsBe9VvDYsVcJfpBgajiXd6S1akQ3c%2FcaZ7Ru8UQ1OBWy4ibHrOOxgIzLV0RQIgpa4kzWr4ll7wxZYPFxSTb7zc0AWVz55AeUhF6dNfNUqdakHcTFwHuIasEbk2Ym6vfoiGjU0JXREqOF0CAEotDGbpHl9ppWHVHhtTYwnl8kSGUZEDTlVcIPoRjxsczfPtb0%2BSZNuftpPng%3D%3D"
    },
    {
        "domain": "janmall.vn",
        "expirationDate": 1812893342.510192,
        "hostOnly": True,
        "httpOnly": False,
        "name": "JAM_NEXT_LOCALE",
        "path": "/",
        "sameSite": None,
        "secure": False,
        "session": False,
        "storeId": None,
        "value": "vi"
    },
    {
        "domain": "janmall.vn",
        "expirationDate": 1813078660.132351,
        "hostOnly": True,
        "httpOnly": False,
        "name": "jam_ui_version",
        "path": "/",
        "sameSite": None,
        "secure": False,
        "session": False,
        "storeId": None,
        "value": "v2"
    }
]"""

# Thay thế các giá trị True/False/None để JSON có thể parse được nếu cần, 
# nhưng vì chuỗi trên đã được chuyển sang dạng Python dict by eval/json.loads (nếu viết chuẩn JSON thì phải là true/false).
# Sửa lại thành chuỗi JSON chuẩn:
cookie_data_json = cookie_data.replace('True', 'true').replace('False', 'false').replace('None', 'null')
cookies = json.loads(cookie_data_json)

for c in cookies:
    if "sameSite" in c:
        if c["sameSite"] == "no_restriction":
            c["sameSite"] = "None"
        elif c["sameSite"] == "lax":
            c["sameSite"] = "Lax"
        elif c["sameSite"] == "strict":
            c["sameSite"] = "Strict"
        elif c["sameSite"] is None:
            del c["sameSite"]

print("Starting playwright...")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
    context = browser.new_context(viewport={'width': 1366, 'height': 1000}, locale='vi-VN')
    context.add_cookies(cookies)
    page = context.new_page()
    print("Navigating to Janmall...")
    page.goto('https://janmall.vn/1688/detail/935969699245?from=search', wait_until='domcontentloaded')
    page.wait_for_timeout(8000)
    print("Saving screenshot...")
    page.screenshot(path='janmall_test_result.png')
    browser.close()
    print("Done")
