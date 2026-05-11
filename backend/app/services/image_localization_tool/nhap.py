import time
import os
import sys
import base64
import mimetypes

from playwright_shim import By, launch_gemini_driver

# Import cấu hình
try:
    from config import CHROME_PROFILE_PATH, GEMINI_URL, DOWNLOADS_DIR
except ImportError:
    print("❌ Lỗi: Không tìm thấy file config.py")
    sys.exit(1)


def main():
    print("=" * 60)
    print("🚀 TEST UPLOAD: VIRTUAL PASTE (DÁN ẢO - KHÔNG CHIẾM CLIPBOARD)")
    print("=" * 60)

    image_path = os.path.abspath("test_image.jpg")
    if not os.path.exists(image_path):
        from PIL import Image

        img = Image.new("RGB", (300, 300), color="blue")
        img.save(image_path)
        print(f"⚠️ Đã tạo file ảnh giả để test tại: {image_path}")

    temp_download = os.path.join(DOWNLOADS_DIR, "temp_download")
    os.makedirs(temp_download, exist_ok=True)

    driver = launch_gemini_driver(
        headless=False,
        user_data_dir=CHROME_PROFILE_PATH,
        download_dir=os.path.abspath(temp_download),
        viewport_width=1280,
        viewport_height=900,
        window_x=100,
        window_y=100,
    )

    try:
        print(f"🌐 Đang vào: {GEMINI_URL}")
        driver.get(GEMINI_URL)
        print("⏳ Đợi 8 giây cho trang tải xong...")
        time.sleep(8)

        print("\n🎯 Đang tìm khung chat (Rich Text Editor)...")
        target = None
        for _ in range(30):
            target = driver.find_element(By.XPATH, "//div[@contenteditable='true']")
            if target and target.is_displayed():
                break
            target = None
            time.sleep(0.5)

        if not target:
            print("❌ Không tìm thấy khung chat contenteditable.")
            return

        print("✅ Đã tìm thấy khung chat.")
        target.click()
        time.sleep(0.5)

        print("⚙️  Đang mã hóa ảnh sang Base64...")
        mime_type, _ = mimetypes.guess_type(image_path)
        if not mime_type:
            mime_type = "image/jpeg"

        with open(image_path, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode("utf-8")

        filename = os.path.basename(image_path)
        print(f"   • File: {filename}")
        print(f"   • Type: {mime_type}")
        print(f"   • Size: {len(b64_data)} chars")

        print("💉 Đang thực hiện Paste Ảo (JS Injection)...")
        js_paste_script = """
        async function virtualPaste(target, b64Data, filename, mimeType) {
            const byteCharacters = atob(b64Data);
            const byteArrays = [];
            for (let offset = 0; offset < byteCharacters.length; offset += 512) {
                const slice = byteCharacters.slice(offset, offset + 512);
                const byteNumbers = new Array(slice.length);
                for (let i = 0; i < slice.length; i++) {
                    byteNumbers[i] = slice.charCodeAt(i);
                }
                const byteArray = new Uint8Array(byteNumbers);
                byteArrays.push(byteArray);
            }
            const blob = new Blob(byteArrays, {type: mimeType});
            const file = new File([blob], filename, {type: mimeType});
            const dataTransfer = new DataTransfer();
            dataTransfer.items.add(file);
            const pasteEvent = new ClipboardEvent('paste', {
                bubbles: true,
                cancelable: true,
                clipboardData: dataTransfer
            });
            target.dispatchEvent(pasteEvent);
            return true;
        }
        return virtualPaste(arguments[0], arguments[1], arguments[2], arguments[3]);
        """

        driver.execute_script(js_paste_script, target, b64_data, filename, mime_type)
        print("✅ Đã gửi lệnh Paste.")

        print("⏳ Đang chờ ảnh xuất hiện (Tối đa 10s)...")
        found = False
        for i in range(10):
            time.sleep(1.0)
            imgs = driver.find_elements(By.XPATH, "//img[starts-with(@src, 'blob:')]")
            valid_imgs = [img for img in imgs if img.is_displayed() and img.size["width"] > 40]

            if valid_imgs:
                print(f"🎉 THÀNH CÔNG! Thấy {len(valid_imgs)} ảnh đã được paste vào khung chat.")
                driver.execute_script("arguments[0].style.border='5px solid green';", valid_imgs[0])
                found = True
                break
            print(f"   ⏳ Giây {i+1}: Chưa thấy ảnh...")

        if not found:
            print("❌ THẤT BẠI: Ảnh không hiện lên.")

        print("\n" + "=" * 60)
        input("👉 Nhấn Enter để đóng trình duyệt...")

    except Exception as e:
        print(f"❌ Lỗi: {e}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
