# dang-nhap-chorm.py - Script đăng nhập Gemini độc lập, tương thích với hệ thống hiện tại
import os
import sys
import time
from pathlib import Path

# Thêm thư mục hiện tại vào PATH
sys.path.insert(0, str(Path(__file__).parent))

try:
    from config import CHROME_PROFILE_PATH, GEMINI_URL, DOWNLOADS_DIR
    print("✅ Đã import config từ hệ thống")
except ImportError:
    print("⚠️ Không tìm thấy config, sử dụng giá trị mặc định")
    _runtime_dir = Path(__file__).resolve().parents[3] / "runtime" / "image_localization"
    CHROME_PROFILE_PATH = str(_runtime_dir / "chrome-profile")
    GEMINI_URL = "https://gemini.google.com/app"
    DOWNLOADS_DIR = str(_runtime_dir / "downloads")

# Tự động thiết lập thư mục
def setup_dirs():
    """Tạo các thư mục cần thiết - tương thích với config.py"""
    from config import setup_directories
    
    print("📁 Đang thiết lập thư mục từ config.py...")
    created_dirs, dir_errors = setup_directories()
    
    if created_dirs:
        print(f"✅ Đã tạo {len(created_dirs)} thư mục")
    
    if dir_errors:
        print(f"⚠️  Lỗi tạo thư mục: {dir_errors}")
    
    # Đảm bảo profile directory tồn tại
    profile_dir = Path(CHROME_PROFILE_PATH)
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "Default").mkdir(exist_ok=True)
    print(f"✅ Đã đảm bảo profile directory: {CHROME_PROFILE_PATH}")

def main():
    print("=" * 80)
    print("🔐 SETUP GEMINI LOGIN - ĐĂNG NHẬP LẦN ĐẦU")
    print("(Tương thích với hệ thống xử lý ảnh)")
    print("=" * 80)
    
    setup_dirs()
    
    print("\n📝 HƯỚNG DẪN ĐĂNG NHẬP:")
    print(f"1. Trình duyệt Chrome sẽ mở lên với profile: {CHROME_PROFILE_PATH}")
    print("2. Đăng nhập vào Gemini với tài khoản Google")
    print("3. Đợi cho đến khi thấy giao diện chat Gemini hoàn chỉnh")
    print("4. QUAY LẠI CỬA SỔ NÀY và NHẤN ENTER")
    print("\n⚠️ QUAN TRỌNG:")
    print("• KHÔNG đóng cửa sổ Python trong lúc đăng nhập")
    print("• Chỉ đóng trình duyệt SAU KHI đã nhấn Enter")
    print("• Đảm bảo internet ổn định")
    print("=" * 80)
    
    input("\n👉 Nhấn ENTER để bắt đầu đăng nhập...")
    
    try:
        from playwright_shim import By, launch_gemini_driver

        download_dir = str(Path(DOWNLOADS_DIR) / "temp_download")
        Path(download_dir).mkdir(parents=True, exist_ok=True)

        print("\n🖥️  Đang mở Chrome (Playwright)...")
        driver = launch_gemini_driver(
            headless=False,
            user_data_dir=CHROME_PROFILE_PATH,
            download_dir=os.path.abspath(download_dir),
            viewport_width=1280,
            viewport_height=900,
            window_x=100,
            window_y=100,
        )
        
        print(f"🌐 Đang truy cập Gemini: {GEMINI_URL}")
        driver.get(GEMINI_URL)
        
        print("\n" + "="*60)
        print("✅ TRÌNH DUYỆT ĐÃ MỞ!")
        print("="*60)
        print("HÃY ĐĂNG NHẬP NGAY BÂY GIỜ!")
        print("1. Đăng nhập bằng tài khoản Google của bạn")
        print("2. Nếu được hỏi, chấp nhận điều khoản")
        print("3. Đợi cho đến khi thấy giao diện chat Gemini (có ô nhập text)")
        print("4. SAU ĐÓ quay lại đây và NHẤN ENTER")
        print("="*60)
        
        input("\n👉 Nhấn ENTER sau khi đăng nhập xong... ")
        
        # Kiểm tra đăng nhập thành công
        time.sleep(3)
        
        # Refresh để đảm bảo đã đăng nhập
        driver.refresh()
        time.sleep(5)
        
        # Kiểm tra xem đã thấy textarea chưa - Sử dụng logic giống gemini_processor.py
        logged_in = False
        textareas = []
        for _ in range(5):
            try:
                textareas = driver.find_elements(
                    By.XPATH,
                    "//div[@contenteditable='true' or textarea]",
                )
                for textarea in textareas:
                    if textarea.is_displayed():
                        logged_in = True
                        break
            except Exception:
                pass

            if logged_in:
                break
            time.sleep(1)
        
        if logged_in:
            print("\n✅ THÀNH CÔNG: Đã đăng nhập Gemini!")
            
            # Lưu marker đăng nhập - KHỚP với gemini_processor.py
            marker_file = Path(CHROME_PROFILE_PATH) / "gemini_logged_in.marker"
            with open(marker_file, 'w', encoding='utf-8') as f:
                f.write(f"Logged in at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            print(f"✅ Đã lưu marker đăng nhập: {marker_file}")
            
            # Test thử bằng cách nhập một tin nhắn test
            try:
                for textarea in textareas:
                    if textarea.is_displayed() and textarea.is_enabled():
                        textarea.click()
                        time.sleep(0.5)
                        textarea.send_keys("Test login")
                        time.sleep(1)
                        print("✅ Đã test nhập tin nhắn thành công")
                        break
            except:
                print("⚠️  Không thể test nhập tin nhắn, nhưng đăng nhập vẫn thành công")
        else:
            print("\n⚠️  CẢNH BÁO: Không thấy giao diện chat rõ ràng")
            print("Nhưng vẫn lưu marker để thử nghiệm...")
            
            # Vẫn lưu marker
            marker_file = Path(CHROME_PROFILE_PATH) / "gemini_logged_in.marker"
            with open(marker_file, 'w', encoding='utf-8') as f:
                f.write(f"Logged in at: {time.strftime('%Y-%m-%d %H:%M:%S')} - Check needed")
        
        # Đóng trình duyệt
        print("\n🔒 Đang đóng trình duyệt...")
        driver.quit()
        print("✅ Đã đóng trình duyệt")
        
        print("\n" + "="*80)
        print("🎉 ĐĂNG NHẬP HOÀN TẤT!")
        print("="*80)
        print(f"\n📁 Profile Chrome: {CHROME_PROFILE_PATH}")
        print(f"📝 Marker file: {CHROME_PROFILE_PATH}/gemini_logged_in.marker")
        
        print("\n📋 Bây giờ bạn có thể chạy các lệnh sau:")
        print("👉 Kiểm tra hệ thống: python main.py --check")
        print("👉 Xử lý dòng đầu tiên: python main.py --row 2")
        print("👉 Xử lý tất cả: python main.py")
        
        print("\n⚠️ LƯU Ý:")
        print("• Nếu gặp lỗi 'Not logged in', chạy lại script này")
        print("• Đảm bảo Chrome không đang chạy khi chạy script")
        
    except ImportError as e:
        print(f"\n❌ LỖI: Thiếu thư viện cần thiết!")
        print(f"Chi tiết: {e}")
        print("\n📦 Vui lòng cài đặt dependencies:")
        print("pip install playwright")
        print("playwright install chrome")
        
    except Exception as e:
        print(f"\n❌ LỖI KHÔNG XÁC ĐỊNH: {e}")
        import traceback
        traceback.print_exc()
        
        print("\n🔧 KHẮC PHỤC:")
        print("1. Đã cài đặt Chrome chưa?")
        print("2. Có kết nối internet không?")
        print("3. Chạy: playwright install chrome")
        print("4. Đóng hết cửa sổ Chrome đang dùng profile này rồi thử lại")
        print("\nChạy lại script sau khi khắc phục.")

if __name__ == "__main__":
    main()