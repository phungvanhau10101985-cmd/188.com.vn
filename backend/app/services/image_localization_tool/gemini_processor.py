# gemini_processor.py
import os
import time
import sys
import json
import psutil
import threading
import base64
import io
from playwright_shim import By, Keys, WebDriverException, launch_gemini_driver
from PIL import Image
import requests
import cv2
import numpy as np
import hashlib
import re
import uuid
from datetime import datetime, timedelta

from config import *
from utils_logger import gemini_logger, log_function_call

class ClipboardManager:
    """Quản lý clipboard - CHỈ CÔ LẬP TẠM THỜI TRONG THỜI GIAN SỬ DỤNG"""
    
    _instance = None
    _lock = threading.Lock()
    _clipboard_in_use = False
    _clipboard_last_used = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ClipboardManager, cls).__new__(cls)
        return cls._instance
    
    @classmethod
    def wait_for_clipboard(cls, program_id, timeout=5):
        """Chờ clipboard khả dụng - TỐI ĐA timeout GIÂY"""
        start_time = time.time()
        attempts = 0
        
        while time.time() - start_time < timeout:
            with cls._lock:
                if not cls._clipboard_in_use:
                    cls._clipboard_in_use = True
                    cls._clipboard_last_used[program_id] = time.time()
                    gemini_logger.debug(f"✅ Clipboard acquired by {program_id} after {attempts*0.3:.1f}s")
                    return True
            
            attempts += 1
            if attempts % 3 == 0:
                elapsed = time.time() - start_time
                gemini_logger.debug(f"⏳ Program {program_id} waiting for clipboard... ({elapsed:.1f}s)")
            
            time.sleep(0.3)
        
        gemini_logger.warning(f"⚠️ Program {program_id} timeout after {timeout}s")
        
        try:
            if sys.platform == "win32":
                import win32clipboard
                try:
                    win32clipboard.CloseClipboard()
                except:
                    pass
        except:
            pass
        
        with cls._lock:
            cls._clipboard_in_use = True
            cls._clipboard_last_used[program_id] = time.time()
            gemini_logger.warning(f"⚠️ FORCED: Clipboard taken by {program_id}")
            return True
    
    @classmethod
    def release_clipboard(cls, program_id):
        """Giải phóng clipboard"""
        with cls._lock:
            if cls._clipboard_in_use:
                cls._clipboard_in_use = False
                if program_id in cls._clipboard_last_used:
                    del cls._clipboard_last_used[program_id]
                gemini_logger.debug(f"✅ Clipboard released by {program_id}")
                return True
        
        try:
            if sys.platform == "win32":
                import win32clipboard
                try:
                    win32clipboard.CloseClipboard()
                except:
                    pass
        except:
            pass
        
        return False
    
    @classmethod
    def clear_clipboard(cls, program_id):
        """Xóa nội dung clipboard"""
        try:
            if sys.platform == "win32":
                import win32clipboard
                
                for _ in range(2):
                    try:
                        win32clipboard.OpenClipboard()
                        win32clipboard.EmptyClipboard()
                        win32clipboard.CloseClipboard()
                        gemini_logger.debug(f"🧹 Clipboard cleared by {program_id}")
                        return True
                    except:
                        time.sleep(0.1)
                        continue
        except Exception as e:
            gemini_logger.debug(f"⚠️ Cannot clear clipboard: {e}")
        return False
    
    @classmethod
    def force_clear_clipboard(cls, program_id):
        """Xóa clipboard BẮT BUỘC"""
        try:
            if sys.platform == "win32":
                import win32clipboard
                
                for attempt in range(3):
                    try:
                        win32clipboard.OpenClipboard()
                        win32clipboard.EmptyClipboard()
                        win32clipboard.CloseClipboard()
                        
                        if attempt > 0:
                            gemini_logger.info(f"🧹 FORCE CLEAR: Cleared on attempt {attempt+1}")
                        return True
                    except:
                        time.sleep(0.2)
                        continue
        except Exception as e:
            gemini_logger.debug(f"⚠️ Cannot force clear: {e}")
        return False
    
    @classmethod
    def get_clipboard_status(cls):
        """Lấy trạng thái clipboard"""
        with cls._lock:
            status = {
                'in_use': cls._clipboard_in_use,
                'last_used_by': list(cls._clipboard_last_used.keys()),
                'last_used_time': cls._clipboard_last_used.copy()
            }
            return status
    
    @classmethod
    def reset_clipboard_state(cls):
        """Reset trạng thái (debug)"""
        with cls._lock:
            cls._clipboard_in_use = False
            cls._clipboard_last_used.clear()
            
            try:
                if sys.platform == "win32":
                    import win32clipboard
                    try:
                        win32clipboard.CloseClipboard()
                    except:
                        pass
            except:
                pass
            
            gemini_logger.info("🔄 Clipboard state reset")
            return True


class GeminiImageProcessor:
    def __init__(self):
        gemini_logger.info("🚀 Initializing Gemini Image Processor...")
        self.driver = None
        self.wait = None
        self.is_logged_in = False
        self.is_initialized = False
        
        self.program_id = str(uuid.uuid4())[:8]
        gemini_logger.info(f"📝 Program ID: {self.program_id}")
        
        self.clipboard_manager = ClipboardManager()
        
        self.consecutive_errors = 0
        self.max_consecutive_errors = 3
        self.last_success_time = time.time()
        self.current_image_retries = 0
        self.max_image_retries = 5
        self.system_failure_mode = False
        self.system_failure_start_time = 0
        self.system_failure_cooldown = 360
        
        self.original_width = None
        
        self.window_state_file = os.path.join(CHROME_PROFILE_PATH, "Default", "window_state.json")
        self.current_temp_image_path = None
        self.STABLE_WAIT_TIME = 1.5
        
        # Thống kê upload methods
        self.upload_stats = {
            'virtual_paste_success': 0,
            'virtual_paste_failed': 0,
            'real_clipboard_success': 0,
            'real_clipboard_failed': 0,
            'total_attempts': 0
        }
        
        os.makedirs(DOWNLOADS_DIR, exist_ok=True)
        os.makedirs(TEMP_IMAGES_DIR, exist_ok=True)
        os.makedirs(CHROME_PROFILE_PATH, exist_ok=True)
    
    # ========== QUẢN LÝ VỊ TRÍ CỬA SỔ ==========
    
    def _save_window_state(self, width=1024, height=768, x=100, y=100):
        """Lưu vị trí cửa sổ"""
        try:
            state_data = {
                'width': width,
                'height': height,
                'x': x,
                'y': y,
                'maximized': False,
                'timestamp': time.time()
            }
            
            os.makedirs(os.path.dirname(self.window_state_file), exist_ok=True)
            
            with open(self.window_state_file, 'w') as f:
                json.dump(state_data, f)
            
            gemini_logger.info(f"✅ Saved window position: {state_data}")
            return True
        except Exception as e:
            gemini_logger.error(f"⚠️ Error saving window: {e}")
            return False
    
    def _get_last_window_state(self):
        """Lấy vị trí cửa sổ lần trước"""
        try:
            if os.path.exists(self.window_state_file):
                with open(self.window_state_file, 'r') as f:
                    data = json.load(f)
                
                if time.time() - data.get('timestamp', 0) > 86400:
                    gemini_logger.info("⏰ Window state file too old, resetting")
                    return None
                
                data['maximized'] = False
                gemini_logger.info(f"📋 Read window state: {data}")
                return data
        except Exception as e:
            gemini_logger.debug(f"⚠️ Cannot read window file: {e}")
        return None
    
    def _apply_window_state(self):
        """Áp dụng vị trí cửa sổ"""
        try:
            if self.driver:
                state = self._get_last_window_state()
                if state:
                    js_code = f"""
                    window.moveTo({state.get('x', 100)}, {state.get('y', 100)});
                    window.resizeTo({state.get('width', 1024)}, {state.get('height', 768)});
                    """
                    self.driver.execute_script(js_code)
                    time.sleep(0.5)
                    gemini_logger.info(f"✅ Applied window state")
                    return True
        except Exception as e:
            gemini_logger.debug(f"⚠️ Error applying window: {e}")
        return False
    
    # ========== QUẢN LÝ LỖI HỆ THỐNG ==========
    
    def _enter_system_failure_mode(self):
        """Vào chế độ lỗi hệ thống"""
        self.system_failure_mode = True
        self.system_failure_start_time = time.time()
        
        gemini_logger.critical("=" * 80)
        gemini_logger.critical("🚨🚨🚨 SYSTEM FAILURE 🚨🚨🚨")
        gemini_logger.critical("=" * 80)
        gemini_logger.critical("Gemini failed 5 times consecutively!")
        gemini_logger.critical(f"Possible reasons:")
        gemini_logger.critical("1. Gemini quota/credit exhausted")
        gemini_logger.critical("2. Network/Gemini server down")
        gemini_logger.critical("3. Account blocked/suspended")
        gemini_logger.critical("=" * 80)
        gemini_logger.critical(f"⏰ PAUSING FOR {self.system_failure_cooldown//60} MINUTES...")
        gemini_logger.critical("=" * 80)
        
        print("\n" + "="*80)
        print("🚨🚨🚨 SYSTEM FAILURE 🚨🚨🚨")
        print("="*80)
        print("Gemini failed 5 times consecutively!")
        print(f"Possible reasons:")
        print("1. Gemini quota/credit exhausted")
        print("2. Network/Gemini server down")
        print("3. Account blocked/suspended")
        print("="*80)
        print(f"⏰ PAUSING FOR {self.system_failure_cooldown//60} MINUTES...")
        print("="*80)
    
    def _check_system_failure_cooldown(self):
        """Kiểm tra thời gian chờ lỗi"""
        if not self.system_failure_mode:
            return True
        
        elapsed = time.time() - self.system_failure_start_time
        
        if elapsed >= self.system_failure_cooldown:
            self.system_failure_mode = False
            self.system_failure_start_time = 0
            self.current_image_retries = 0
            self.consecutive_errors = 0
            
            gemini_logger.info("=" * 80)
            gemini_logger.info("✅ SYSTEM FAILURE COOLDOWN COMPLETE")
            gemini_logger.info("=" * 80)
            gemini_logger.info("🔄 RESTARTING AND RETRYING...")
            gemini_logger.info("=" * 80)
            
            print("\n" + "="*80)
            print("✅ SYSTEM FAILURE COOLDOWN COMPLETE")
            print("="*80)
            print("🔄 RESTARTING AND RETRYING...")
            print("="*80)
            
            return self._reset_driver_hard(save_position=True)
        else:
            remaining = self.system_failure_cooldown - elapsed
            minutes = int(remaining // 60)
            seconds = int(remaining % 60)
            
            if minutes % 5 == 0 or minutes <= 5:
                gemini_logger.info(f"⏳ System failure cooldown: {minutes}m {seconds}s remaining")
                print(f"⏳ System failure cooldown: {minutes}m {seconds}s remaining")
            
            return False
    
    # ========== RESIZE ẢNH ==========
    
    def _resize_to_original_width(self, image_path: str, target_width: int) -> str:
        """Resize ảnh về chiều rộng gốc"""
        try:
            if not os.path.exists(image_path) or target_width <= 0:
                return image_path
            
            img = cv2.imread(image_path, cv2.IMREAD_COLOR)
            if img is None:
                return image_path
            
            h, w = img.shape[:2]
            
            if w == target_width:
                return image_path
            
            ratio = target_width / w
            new_height = int(h * ratio)
            
            resized_img = cv2.resize(img, (target_width, new_height), 
                                     interpolation=cv2.INTER_LANCZOS4)
            
            dir_name = os.path.dirname(image_path)
            file_name, file_ext = os.path.splitext(os.path.basename(image_path))
            
            if not file_ext or file_ext == '':
                file_ext = '.jpg'
            
            resized_filename = f"{file_name}_resized{file_ext}"
            resized_path = os.path.join(dir_name, resized_filename)
            
            cv2.imwrite(resized_path, resized_img, [cv2.IMWRITE_JPEG_QUALITY, 95])
            
            gemini_logger.info(f"✅ Resized: {w}x{h} -> {target_width}x{new_height}")
            
            return resized_path
            
        except Exception as e:
            gemini_logger.error(f"❌ Resize error: {e}")
            return image_path
    
    # ========== KIỂM TRA ỔN ĐỊNH ẢNH & PROMPT ==========
    
    def _wait_for_content_stability(self, timeout=10):
        """Chờ ảnh và prompt ổn định"""
        try:
            gemini_logger.info(f"⏳ Waiting {self.STABLE_WAIT_TIME}s for content stability...")
            start_time = time.time()
            
            gemini_logger.info(f"  🔄 Waiting {self.STABLE_WAIT_TIME}s...")
            time.sleep(self.STABLE_WAIT_TIME)
            
            has_image, has_prompt = self._check_work_area_content_detailed()
            
            if not has_image:
                gemini_logger.warning("⚠️ No image detected after wait")
                return False
                
            if not has_prompt:
                gemini_logger.warning("⚠️ No prompt detected after wait")
                return False
            
            images_loaded = self._check_images_fully_loaded()
            if not images_loaded:
                gemini_logger.warning("⚠️ Images not fully loaded")
                return False
            
            prompt_ok = self._check_prompt_completeness()
            if not prompt_ok:
                gemini_logger.warning("⚠️ Prompt incomplete")
                return False
            
            elapsed = time.time() - start_time
            gemini_logger.info(f"✅ Waited {elapsed:.1f}s - Content stable!")
            return True
            
        except Exception as e:
            gemini_logger.error(f"❌ Stability check error: {e}")
            return False
    
    def _check_work_area_content_detailed(self):
        """Kiểm tra chi tiết nội dung"""
        try:
            gemini_logger.info("🔍 Detailed content check...")
            
            has_image = False
            image_count = 0
            image_selectors = [
                "//img[contains(@src, 'blob:')]",
                "//img[contains(@src, 'data:image')]",
                "//img[contains(@src, 'googleusercontent.com')]",
                "//img[contains(@class, 'uploaded-image')]",
                "//img[contains(@class, 'image-thumbnail')]",
            ]
            
            for selector in image_selectors:
                try:
                    images = self.driver.find_elements(By.XPATH, selector)
                    if images:
                        for img in images:
                            try:
                                if img.is_displayed():
                                    src = img.get_attribute('src') or ''
                                    if src and ('blob:' in src or 'data:image' in src or 'googleusercontent.com' in src):
                                        image_count += 1
                                        has_image = True
                            except:
                                continue
                except:
                    continue
            
            has_prompt = False
            prompt_found = False
            textarea = self._get_textarea_element()
            
            if textarea:
                try:
                    content = ""
                    
                    try:
                        content = textarea.get_attribute('value') or ''
                    except:
                        pass
                    
                    if not content:
                        try:
                            content = textarea.text or ''
                        except:
                            pass
                    
                    if not content:
                        try:
                            content = textarea.get_attribute('innerText') or ''
                        except:
                            pass
                    
                    if not content:
                        try:
                            content = textarea.get_attribute('textContent') or ''
                        except:
                            pass
                    
                    if content:
                        prompt_parts = [
                            GEMINI_PROMPT[:30],
                            GEMINI_PROMPT[-30:],
                            "trung và domain",
                            "ảnh sạch"
                        ]
                        
                        for part in prompt_parts:
                            if part in content:
                                prompt_found = True
                                break
                        
                        if prompt_found:
                            has_prompt = True
                            gemini_logger.info(f"✅ Prompt found ({len(content)} chars)")
                except Exception as e:
                    gemini_logger.debug(f"⚠️ Read prompt error: {e}")
            
            gemini_logger.info(f"📊 Detailed check: images={image_count}, has_prompt={has_prompt}")
            return has_image, has_prompt
            
        except Exception as e:
            gemini_logger.error(f"❌ Detailed check error: {e}")
            return False, False
    
    def _check_images_fully_loaded(self):
        """Kiểm tra ảnh đã load hoàn toàn"""
        try:
            gemini_logger.info("🔍 Checking images fully loaded...")
            
            image_selectors = [
                "//img[contains(@src, 'blob:')]",
                "//img[contains(@src, 'data:image')]",
                "//img[contains(@src, 'googleusercontent.com')]",
            ]
            
            all_loaded = True
            
            for selector in image_selectors:
                try:
                    images = self.driver.find_elements(By.XPATH, selector)
                    for img in images:
                        try:
                            if img.is_displayed():
                                complete = img.get_attribute('complete')
                                natural_width = img.get_attribute('naturalWidth')
                                
                                if complete == 'false' or (natural_width and int(natural_width) == 0):
                                    gemini_logger.debug(f"⚠️ Image not loaded: complete={complete}, naturalWidth={natural_width}")
                                    all_loaded = False
                        except:
                            continue
                except:
                    continue
            
            if all_loaded:
                gemini_logger.info("✅ All images loaded")
            else:
                gemini_logger.warning("⚠️ Some images not fully loaded")
            
            return all_loaded
            
        except Exception as e:
            gemini_logger.error(f"❌ Image load check error: {e}")
            return True
    
    def _check_prompt_completeness(self):
        """Kiểm tra prompt đầy đủ"""
        try:
            textarea = self._get_textarea_element()
            if not textarea:
                return False
            
            content = ""
            try:
                content = textarea.get_attribute('value') or ''
            except:
                pass
            
            if not content:
                try:
                    content = textarea.text or ''
                except:
                    pass
            
            if not content:
                try:
                    content = textarea.get_attribute('innerText') or ''
                except:
                    pass
            
            min_length = len(GEMINI_PROMPT) * 0.8
            
            if len(content) < min_length:
                gemini_logger.warning(f"⚠️ Prompt too short: {len(content)} chars (min {int(min_length)})")
                return False
            
            important_keywords = ["trung", "domain", "sạch", "ảnh"]
            found_keywords = sum(1 for keyword in important_keywords if keyword in content.lower())
            
            if found_keywords < 2:
                gemini_logger.warning(f"⚠️ Missing important keywords")
                return False
            
            gemini_logger.info(f"✅ Prompt complete: {len(content)} chars, {found_keywords}/4 keywords")
            return True
            
        except Exception as e:
            gemini_logger.error(f"❌ Prompt check error: {e}")
            return True
    
    # ========== QUẢN LÝ BROWSER ==========
    
    def _force_kill_chrome_processes(self):
        """Đóng Chrome processes"""
        try:
            killed = 0
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if proc.info['name'] and 'chrome' in proc.info['name'].lower():
                        cmdline = ' '.join(proc.info['cmdline'] or [])
                        if CHROME_PROFILE_PATH in cmdline:
                            proc.kill()
                            killed += 1
                except:
                    continue
            
            if killed > 0:
                gemini_logger.info(f"✅ Killed {killed} Chrome processes")
            
            time.sleep(1)
            return True
            
        except Exception as e:
            gemini_logger.error(f"Error killing Chrome: {e}")
            return False
    
    def _check_login_state_marker(self):
        """Kiểm tra marker đăng nhập"""
        try:
            marker_file = os.path.join(CHROME_PROFILE_PATH, "gemini_logged_in.marker")
            if os.path.exists(marker_file):
                with open(marker_file, 'r') as f:
                    content = f.read()
                gemini_logger.info(f"✅ Found login marker: {content}")
                return True
            return False
        except:
            return False
    
    def _save_login_marker(self):
        """Lưu marker đăng nhập"""
        try:
            marker_file = os.path.join(CHROME_PROFILE_PATH, "gemini_logged_in.marker")
            with open(marker_file, 'w') as f:
                f.write(f"Logged in at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
            return True
        except:
            return False
    
    def _launch_pw_browser(self):
        """Mở Chrome qua Playwright (persistent profile, cùng thư mục user-data như trước)."""
        last_state = self._get_last_window_state() or {}
        w = int(last_state.get("width", 1024))
        h = int(last_state.get("height", 768))
        x = int(last_state.get("x", 100))
        y = int(last_state.get("y", 100))
        temp_download_dir = os.path.join(DOWNLOADS_DIR, "temp_download")
        os.makedirs(temp_download_dir, exist_ok=True)
        self.driver = launch_gemini_driver(
            headless=HEADLESS,
            user_data_dir=CHROME_PROFILE_PATH,
            download_dir=os.path.abspath(temp_download_dir),
            viewport_width=w,
            viewport_height=h,
            window_x=x,
            window_y=y,
        )
        self.wait = None
        self.driver.set_page_load_timeout(25)
    
    def _is_driver_active(self):
        """Kiểm tra driver hoạt động"""
        try:
            if self.driver:
                current_url = self.driver.current_url
                return True
        except (WebDriverException, Exception) as e:
            gemini_logger.debug(f"Driver not active: {e}")
            return False
        return False
    
    # ========== QUẢN LÝ CHẾ ĐỘ PRO ==========
    
    def _ensure_pro_mode_strict(self, max_retries=3):
        """
        Đảm bảo chắc chắn ở chế độ Pro trước khi xử lý ảnh
        Nếu không chuyển được sẽ reset driver và retry
        """
        for attempt in range(max_retries):
            try:
                gemini_logger.info(f"🔧 Kiểm tra chế độ Pro (lần {attempt + 1}/{max_retries})...")
                
                # Chờ ổn định trang
                time.sleep(2)
                
                # Selector để tìm nút chuyển đổi chế độ
                trigger_selectors = [
                    "//div[contains(@class, 'input-area-switch-label')]",
                    "//button[contains(@aria-label, 'Switch mode')]",
                    "//div[contains(@class, 'mode-switch')]",
                    "//div[@role='switch']",
                    "//div[contains(@class, 'model-selector-container')]",
                ]
                
                trigger_btn = None
                for selector in trigger_selectors:
                    try:
                        elements = self.driver.find_elements(By.XPATH, selector)
                        for elem in elements:
                            if elem.is_displayed():
                                trigger_btn = elem
                                break
                        if trigger_btn:
                            break
                    except:
                        continue
                
                if not trigger_btn:
                    gemini_logger.error("❌ Không tìm thấy nút chuyển chế độ")
                    if attempt < max_retries - 1:
                        gemini_logger.info(f"🔄 Retry {attempt + 1}/{max_retries}...")
                        self.driver.refresh()
                        time.sleep(3)
                        continue
                    return False
                
                # Lấy trạng thái hiện tại
                current_mode_text = ""
                try:
                    # Thử lấy text từ nhiều nơi
                    text_selectors = [
                        f"{trigger_selectors[0]}//span",
                        "//span[contains(@class, 'mode-text')]",
                        "//div[contains(@class, 'mode-label')]",
                        "//div[contains(@class, 'selected-model-name')]",
                    ]
                    
                    for selector in text_selectors:
                        try:
                            text_elem = self.driver.find_element(By.XPATH, selector)
                            if text_elem.is_displayed():
                                current_mode_text = text_elem.text.strip()
                                if current_mode_text:
                                    break
                        except:
                            continue
                    
                    gemini_logger.info(f"ℹ️ Trạng thái hiện tại: [{current_mode_text}]")
                    
                    # KIỂM TRA NGHIÊM NGẶT - CHỈ TIẾP TỤC NẾU ĐÃ Ở PRO
                    pro_keywords = ["Pro", "Advanced", "pro", "PRO", "Nâng cao", "Gemini Advanced"]
                    if any(keyword in current_mode_text for keyword in pro_keywords):
                        gemini_logger.info("✅ ĐÃ Ở CHẾ ĐỘ PRO - SẴN SÀNG XỬ LÝ")
                        return True
                    else:
                        gemini_logger.warning(f"⚠️ CHƯA Ở CHẾ ĐỘ PRO: [{current_mode_text}]")
                        
                except Exception as e:
                    gemini_logger.warning(f"⚠️ Không đọc được trạng thái: {e}")
                    current_mode_text = "Unknown"
                
                # NẾU CHƯA Ở PRO - THỰC HIỆN CHUYỂN ĐỔI
                gemini_logger.info("🔄 Thực hiện chuyển sang chế độ Pro...")
                
                # Click mở menu
                try:
                    self.driver.execute_script("arguments[0].click();", trigger_btn)
                    gemini_logger.info("🖱️ Đã mở menu chế độ")
                    time.sleep(1.5)
                except Exception as e:
                    gemini_logger.error(f"❌ Không mở được menu: {e}")
                    if attempt < max_retries - 1:
                        self.driver.refresh()
                        time.sleep(3)
                        continue
                    return False
                
                # Tìm và click nút Pro
                pro_selectors = [
                    "//button[@data-test-id='bard-mode-option-pro']",
                    "//div[text()='Pro' and @role='option']",
                    "//div[contains(text(), 'Advanced') and @role='option']",
                    "//div[contains(@class, 'pro-option')]",
                    "//li[contains(text(), 'Pro')]",
                    "//button[.//span[text()='Pro']]",
                    "//div[contains(text(), 'Gemini Advanced')]",
                ]
                
                pro_selected = False
                for selector in pro_selectors:
                    try:
                        elements = self.driver.find_elements(By.XPATH, selector)
                        for elem in elements:
                            if elem.is_displayed() and elem.is_enabled():
                                self.driver.execute_script("arguments[0].scrollIntoView();", elem)
                                time.sleep(0.3)
                                self.driver.execute_script("arguments[0].click();", elem)
                                gemini_logger.info(f"✅ Đã click chọn Pro: {selector}")
                                pro_selected = True
                                time.sleep(2)  # Chờ thay đổi
                                break
                        if pro_selected:
                            break
                    except:
                        continue
                
                if not pro_selected:
                    gemini_logger.error("❌ Không tìm thấy/tương tác được với nút Pro")
                    if attempt < max_retries - 1:
                        gemini_logger.info("🔄 Thử đóng menu bằng ESC và retry...")
                        try:
                            self.driver.keyboard_escape()
                            time.sleep(1)
                        except:
                            pass
                        self.driver.refresh()
                        time.sleep(3)
                        continue
                    return False
                
                # KIỂM TRA XÁC NHẬN SAU KHI CHỌN
                gemini_logger.info("🔍 Xác nhận đã chuyển sang Pro...")
                time.sleep(2)
                
                # Lấy lại trạng thái mới
                new_mode_text = ""
                for selector in text_selectors:
                    try:
                        text_elem = self.driver.find_element(By.XPATH, selector)
                        if text_elem.is_displayed():
                            new_mode_text = text_elem.text.strip()
                            if new_mode_text:
                                break
                    except:
                        continue
                
                # XÁC NHẬN CUỐI CÙNG - NGHIÊM NGẶT
                if any(keyword in new_mode_text for keyword in pro_keywords):
                    gemini_logger.info(f"✅ XÁC NHẬN: ĐÃ CHUYỂN SANG PRO [{new_mode_text}]")
                    return True
                else:
                    gemini_logger.warning(f"⚠️ Xác nhận thất bại: Vẫn hiển thị [{new_mode_text}]")
                    
                    if attempt < max_retries - 1:
                        gemini_logger.info(f"🔄 Retry {attempt + 1}/{max_retries}...")
                        # Reset trang và thử lại
                        self.driver.get(GEMINI_URL)
                        time.sleep(4)
                        continue
                    
                    gemini_logger.error("❌ KHÔNG THỂ CHUYỂN SANG PRO SAU NHIỀU LẦN THỬ")
                    return False
                    
            except Exception as e:
                gemini_logger.error(f"❌ Lỗi trong quá trình đảm bảo Pro mode: {e}")
                if attempt < max_retries - 1:
                    gemini_logger.info(f"🔄 Retry sau lỗi...")
                    self.driver.refresh()
                    time.sleep(3)
                    continue
                return False
        
        return False
    
    def _force_pro_mode_with_reset(self):
        """
        Buộc chuyển sang Pro mode bằng cách reset nếu cần
        """
        gemini_logger.info("🔄 Buộc chuyển sang Pro mode bằng reset...")
        
        # Thử phương pháp thông thường trước
        if self._ensure_pro_mode_strict(max_retries=1):
            return True
        
        # Nếu không được, reset và thử lại
        gemini_logger.info("🔄 Phương pháp thường thất bại, thử reset...")
        
        # Lưu vị trí cửa sổ
        try:
            window_info = {
                'width': self.driver.get_window_size()['width'],
                'height': self.driver.get_window_size()['height'],
                'x': self.driver.get_window_position()['x'],
                'y': self.driver.get_window_position()['y']
            }
            self._save_window_state(**window_info)
        except:
            pass
        
        # Đóng và mở lại trình duyệt
        try:
            self.driver.quit()
        except Exception:
            pass
        self.driver = None

        self._force_kill_chrome_processes()
        time.sleep(3)

        self._launch_pw_browser()
        time.sleep(1)
        self._apply_window_state()
        self.driver.get(GEMINI_URL)
        time.sleep(4)
        
        # Check login
        if not self._check_logged_in():
            gemini_logger.error("❌ Không login được sau reset")
            return False
        
        # Thử đảm bảo Pro mode lại
        return self._ensure_pro_mode_strict(max_retries=2)
    
    def ensure_driver_running(self):
        """Đảm bảo driver đang chạy"""
        try:
            if self.system_failure_mode:
                if not self._check_system_failure_cooldown():
                    return False
            
            if self.driver and self._is_driver_active():
                if self.consecutive_errors > 0:
                    gemini_logger.info(f"✅ Driver active, reset error count")
                    self.consecutive_errors = 0
                return True
            
            gemini_logger.info("🔄 Driver not active, reinitializing...")
            
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
                self.driver = None
            
            if not self._check_login_state_marker():
                gemini_logger.error("❌ Not logged into Gemini")
                return False
            
            self._force_kill_chrome_processes()
            time.sleep(2)

            self._launch_pw_browser()
            time.sleep(1)
            self._apply_window_state()

            self.driver.get(GEMINI_URL)
            time.sleep(4)
            
            if self._check_logged_in():
                self.is_logged_in = True
                self.is_initialized = True
                self.consecutive_errors = 0
                self.last_success_time = time.time()
                
                # KIỂM TRA VÀ ĐẢM BẢO PRO MODE NGAY KHI KHỞI ĐỘNG
                gemini_logger.info("🔒 Đảm bảo chế độ Pro khi khởi động...")
                time.sleep(2)
                
                if not self._ensure_pro_mode_strict(max_retries=1):
                    gemini_logger.warning("⚠️ Không đảm bảo được Pro mode khi khởi động")
                    # Ghi nhận lỗi nhưng vẫn tiếp tục
                    self.consecutive_errors += 1
                
                gemini_logger.info("✅ Driver restarted successfully")
                return True
            else:
                gemini_logger.error("❌ Not logged in after restart")
                return False
                
        except Exception as e:
            gemini_logger.error(f"❌ Driver ensure error: {e}")
            self.driver = None
            return False
    
    def _reset_driver_soft(self):
        """Reset nhẹ driver"""
        try:
            if self.driver and self._is_driver_active():
                gemini_logger.info("🔄 Soft reset - reload page")
                self.driver.get(GEMINI_URL)
                time.sleep(3)
                
                if self._check_logged_in():
                    # Đảm bảo Pro mode sau khi reset
                    time.sleep(1)
                    self._ensure_pro_mode_strict(max_retries=1)
                    
                    gemini_logger.info("✅ Soft reset successful")
                    return True
        except Exception as e:
            gemini_logger.error(f"❌ Soft reset error: {e}")
        return False
    
    def _reset_driver_hard(self, save_position=True):
        """Reset mạnh driver"""
        try:
            gemini_logger.info("🔄 Hard reset - restart browser")
            
            if self.driver and save_position:
                try:
                    window_info = {
                        'width': self.driver.get_window_size()['width'],
                        'height': self.driver.get_window_size()['height'],
                        'x': self.driver.get_window_position()['x'],
                        'y': self.driver.get_window_position()['y']
                    }
                    self._save_window_state(**window_info)
                except:
                    pass
                
                try:
                    self.driver.quit()
                except:
                    pass
            
            self.driver = None
            self.is_logged_in = False
            self.current_temp_image_path = None
            time.sleep(2)
            
            self._force_kill_chrome_processes()
            time.sleep(3)
            
            self.consecutive_errors = 0
            
            # Khởi động lại và đảm bảo Pro mode
            if self.ensure_driver_running():
                # Thêm đảm bảo Pro mode sau khi khởi động lại
                time.sleep(2)
                if not self._ensure_pro_mode_strict(max_retries=2):
                    gemini_logger.warning("⚠️ Không đảm bảo được Pro mode sau hard reset")
                    return False
                
                gemini_logger.info("✅ Hard reset successful")
                return True
            
            return False
            
        except Exception as e:
            gemini_logger.error(f"❌ Hard reset error: {e}")
            return False
    
    def _handle_error(self, error_msg):
        """Xử lý lỗi"""
        self.consecutive_errors += 1
        gemini_logger.warning(f"⚠️ Error #{self.consecutive_errors}: {error_msg}")
        
        if self.consecutive_errors >= self.max_consecutive_errors:
            gemini_logger.error(f"❌ Too many errors ({self.max_consecutive_errors}), hard reset")
            success = self._reset_driver_hard()
            if success:
                self.consecutive_errors = 0
            return success
        else:
            gemini_logger.info(f"🔄 Try soft reset (error #{self.consecutive_errors})")
            return self._reset_driver_soft()
    
    def _check_logged_in(self):
        """Kiểm tra đã login"""
        try:
            for _ in range(5):
                try:
                    textarea = self.driver.find_element(By.XPATH, 
                        "//div[@contenteditable='true' or textarea]")
                    if textarea.is_displayed():
                        return True
                except:
                    time.sleep(1)
            return False
        except:
            return False
    
    # ========== KIỂM TRA NỘI DUNG ==========
    
    def _check_work_area_content(self):
        """Kiểm tra nội dung trong khung làm việc"""
        try:
            gemini_logger.info("🔍 Checking work area content...")
            
            has_image = False
            image_selectors = [
                "//img[contains(@src, 'blob:')]",
                "//img[contains(@src, 'data:image')]",
                "//img[contains(@src, 'googleusercontent.com')]",
                "//img[contains(@class, 'uploaded-image')]",
                "//img[contains(@class, 'image-thumbnail')]",
            ]
            
            for selector in image_selectors:
                try:
                    images = self.driver.find_elements(By.XPATH, selector)
                    if images:
                        visible_images = []
                        for img in images:
                            try:
                                if img.is_displayed():
                                    src = img.get_attribute('src') or ''
                                    if src and ('blob:' in src or 'data:image' in src or 'googleusercontent.com' in src):
                                        visible_images.append(img)
                            except:
                                continue
                        
                        if visible_images:
                            has_image = True
                            gemini_logger.info(f"✅ Found {len(visible_images)} images")
                            break
                except:
                    continue
            
            has_prompt = False
            textarea = self._get_textarea_element()
            if textarea:
                try:
                    content = ""
                    try:
                        content = textarea.get_attribute('value') or ''
                    except:
                        pass
                    
                    if not content:
                        try:
                            content = textarea.text or ''
                        except:
                            pass
                    
                    if not content:
                        try:
                            content = textarea.get_attribute('innerText') or ''
                        except:
                            pass
                    
                    if content and GEMINI_PROMPT[:20] in content:
                        has_prompt = True
                        gemini_logger.info("✅ Found prompt")
                except:
                    pass
            
            gemini_logger.info(f"📊 Content check: has_image={has_image}, has_prompt={has_prompt}")
            return has_image, has_prompt
            
        except Exception as e:
            gemini_logger.error(f"❌ Content check error: {e}")
            return False, False
    
    def _ensure_work_area_has_content(self, image_path):
        """Đảm bảo khung làm việc có đủ nội dung"""
        try:
            gemini_logger.info("🛠️ Ensuring work area has content...")
            
            if image_path is None or not os.path.exists(image_path):
                gemini_logger.error(f"❌ Image path không hợp lệ: {image_path}")
                if self.current_temp_image_path and os.path.exists(self.current_temp_image_path):
                    gemini_logger.info(f"🔄 Sử dụng current_temp_image_path thay thế: {self.current_temp_image_path}")
                    image_path = self.current_temp_image_path
                else:
                    return False
            
            has_image, has_prompt = self._check_work_area_content()
            gemini_logger.info(f"📊 Current: has_image={has_image}, has_prompt={has_prompt}")
            
            if not has_image:
                gemini_logger.warning("🖼️ Missing image, uploading...")
                
                if not os.path.exists(image_path):
                    gemini_logger.error(f"❌ Image file missing: {image_path}")
                    return False
                
                textarea = self._get_textarea_element()
                if textarea:
                    textarea.click()
                    time.sleep(0.3)
                
                # Sử dụng phương pháp upload hybrid mới
                if not self._upload_image_hybrid(image_path):
                    gemini_logger.error("❌ Cannot upload image")
                    return False
                
                time.sleep(1.0)
                
                has_image, _ = self._check_work_area_content_detailed()
                if not has_image:
                    gemini_logger.error("❌ Still no image after upload")
                    return False
                else:
                    gemini_logger.info("✅ Image added successfully")
            
            if not has_prompt:
                gemini_logger.warning("💬 Missing prompt, entering...")
                
                textarea = self._get_textarea_element()
                if textarea:
                    textarea.click()
                    time.sleep(0.3)
                
                if not self._enter_prompt_direct():
                    gemini_logger.error("❌ Cannot enter prompt")
                    return False
                else:
                    gemini_logger.info("✅ Prompt added successfully")
            
            has_image_final, has_prompt_final = self._check_work_area_content_detailed()
            
            if has_image_final and has_prompt_final:
                gemini_logger.info("✅ Work area has full content")
                return True
            else:
                gemini_logger.error(f"❌ Still missing: image={has_image_final}, prompt={has_prompt_final}")
                return False
                
        except Exception as e:
            gemini_logger.error(f"❌ Ensure content error: {e}")
            return False
    
    # ========== UPLOAD ẢNH HYBRID - KẾT HỢP CLIPBOARD ẢO & THẬT ==========
    
    def _upload_image_hybrid(self, image_path):
        """
        Upload ảnh với chiến lược hybrid:
        1. Thử Clipboard Ảo (Virtual Paste) trước
        2. Nếu thất bại, dùng Clipboard Thật
        """
        self.upload_stats['total_attempts'] += 1
        gemini_logger.info(f"🔄 Hybrid Upload Strategy for: {os.path.basename(image_path)}")
        
        # Bước 1: Thử Clipboard Ảo trước
        gemini_logger.info("  📋 Attempt 1: Virtual Paste (Clipboard Ảo)")
        if self._virtual_paste_upload(image_path):
            self.upload_stats['virtual_paste_success'] += 1
            gemini_logger.info("  ✅ Virtual Paste SUCCESS")
            return True
        else:
            self.upload_stats['virtual_paste_failed'] += 1
            gemini_logger.warning("  ⚠️ Virtual Paste FAILED")
        
        # Bước 2: Nếu Clipboard Ảo thất bại, dùng Clipboard Thật
        gemini_logger.info("  📋 Attempt 2: Real Clipboard (Clipboard Thật)")
        if self._real_clipboard_upload(image_path):
            self.upload_stats['real_clipboard_success'] += 1
            gemini_logger.info("  ✅ Real Clipboard SUCCESS")
            return True
        else:
            self.upload_stats['real_clipboard_failed'] += 1
            gemini_logger.error("  ❌ Real Clipboard FAILED")
        
        return False
    
    def _virtual_paste_upload(self, image_path):
        """
        Phương pháp 1: Clipboard Ảo (Virtual Paste)
        Không chiếm clipboard hệ thống
        """
        try:
            # Kiểm tra kích thước file - chỉ dùng cho ảnh nhỏ
            file_size = os.path.getsize(image_path)
            if file_size > 2 * 1024 * 1024:  # >2MB
                gemini_logger.info("  ⚠️ Image too large for virtual paste, skipping")
                return False
            
            # Đọc ảnh và mã hóa base64
            with open(image_path, "rb") as f:
                b64_data = base64.b64encode(f.read()).decode('utf-8')
            
            # Tìm textarea
            textarea = self._get_textarea_element()
            if not textarea:
                gemini_logger.error("  ❌ No textarea found")
                return False
            
            # JavaScript để tạo clipboard event ảo
            js_virtual_paste = f"""
            // Hàm chuyển base64 thành blob
            function base64ToBlob(base64, mimeType) {{
                const byteCharacters = atob(base64);
                const byteArrays = [];
                
                for (let offset = 0; offset < byteCharacters.length; offset += 512) {{
                    const slice = byteCharacters.slice(offset, offset + 512);
                    const byteNumbers = new Array(slice.length);
                    
                    for (let i = 0; i < slice.length; i++) {{
                        byteNumbers[i] = slice.charCodeAt(i);
                    }}
                    
                    byteArrays.push(new Uint8Array(byteNumbers));
                }}
                
                return new Blob(byteArrays, {{ type: mimeType }});
            }}
            
            // Tạo blob từ base64
            const blob = base64ToBlob("{b64_data}", "image/jpeg");
            const file = new File([blob], "image.jpg", {{ type: "image/jpeg" }});
            
            // Tạo DataTransfer ảo
            const dataTransfer = new DataTransfer();
            dataTransfer.items.add(file);
            
            // Tạo paste event ảo
            const pasteEvent = new ClipboardEvent('paste', {{
                bubbles: true,
                cancelable: true,
                clipboardData: dataTransfer
            }});
            
            // Dispatch event vào textarea
            arguments[0].dispatchEvent(pasteEvent);
            
            // Fallback: tạo img element trực tiếp
            setTimeout(() => {{
                const img = document.createElement('img');
                img.src = URL.createObjectURL(blob);
                img.style.maxWidth = '400px';
                img.style.maxHeight = '400px';
                arguments[0].appendChild(img);
                
                // Kích hoạt input event
                const inputEvent = new Event('input', {{ bubbles: true }});
                arguments[0].dispatchEvent(inputEvent);
            }}, 100);
            
            return true;
            """
            
            # Thực thi JavaScript
            result = self.driver.execute_script(js_virtual_paste, textarea)
            time.sleep(2)  # Chờ xử lý
            
            # Kiểm tra kết quả
            if result:
                # Kiểm tra xem ảnh đã xuất hiện chưa
                time.sleep(1)
                if self._check_image_pasted_virtual():
                    return True
            
            # Thử phương pháp JS đơn giản hơn
            return self._simple_js_image_insert(image_path)
            
        except Exception as e:
            gemini_logger.error(f"  ❌ Virtual paste error: {e}")
            return False
    
    def _simple_js_image_insert(self, image_path):
        """Phương pháp JS đơn giản để chèn ảnh"""
        try:
            with open(image_path, "rb") as f:
                b64_data = base64.b64encode(f.read()).decode('utf-8')
            
            textarea = self._get_textarea_element()
            if not textarea:
                return False
            
            # JS đơn giản để chèn ảnh trực tiếp
            js_simple = f"""
            // Tạo img element với base64 src
            const img = document.createElement('img');
            img.src = 'data:image/jpeg;base64,{b64_data}';
            img.style.maxWidth = '500px';
            img.style.maxHeight = '500px';
            img.style.border = '2px solid #4CAF50';
            
            // Chèn vào textarea
            arguments[0].appendChild(img);
            
            // Kích hoạt input event
            const inputEvent = new Event('input', {{ bubbles: true }});
            arguments[0].dispatchEvent(inputEvent);
            
            return true;
            """
            
            result = self.driver.execute_script(js_simple, textarea)
            time.sleep(1.5)
            
            return bool(result)
            
        except Exception as e:
            gemini_logger.error(f"  ❌ Simple JS insert error: {e}")
            return False
    
    def _check_image_pasted_virtual(self):
        """Kiểm tra ảnh đã được paste bằng phương pháp ảo"""
        try:
            time.sleep(1)
            
            # Kiểm tra các img element
            img_selectors = [
                "//img[starts-with(@src, 'blob:')]",
                "//img[contains(@src, 'data:image')]",
                "//img[@style]"
            ]
            
            for selector in img_selectors:
                try:
                    images = self.driver.find_elements(By.XPATH, selector)
                    for img in images:
                        try:
                            if img.is_displayed() and img.size['width'] > 10:
                                src = img.get_attribute('src') or ''
                                if src:
                                    return True
                        except:
                            continue
                except:
                    continue
            
            return False
            
        except Exception as e:
            gemini_logger.error(f"  ❌ Check virtual paste error: {e}")
            return False
    
    def _real_clipboard_upload(self, image_path):
        """
        Phương pháp 2: Clipboard Thật
        Dùng clipboard hệ thống thật sự với quản lý phức tạp
        """
        max_attempts = 2
        
        for attempt in range(max_attempts):
            try:
                gemini_logger.info(f"  📋 Real Clipboard attempt {attempt + 1}/{max_attempts}")
                
                if not os.path.exists(image_path):
                    gemini_logger.error("  ❌ Image file not found")
                    return False
                
                # Chờ clipboard khả dụng
                if not self.clipboard_manager.wait_for_clipboard(self.program_id, timeout=3):
                    gemini_logger.warning(f"  ⚠️ Cannot get clipboard on attempt {attempt + 1}")
                    if attempt < max_attempts - 1:
                        time.sleep(1.5)
                    continue
                
                # Xử lý ảnh và copy vào clipboard
                success = self._copy_to_clipboard_advanced(image_path)
                
                if not success:
                    self.clipboard_manager.release_clipboard(self.program_id)
                    if attempt < max_attempts - 1:
                        time.sleep(2.0)
                    continue
                
                # Tìm textarea và paste
                textarea = self._get_textarea_element()
                if not textarea:
                    gemini_logger.error("  ❌ No textarea found")
                    self.clipboard_manager.release_clipboard(self.program_id)
                    continue
                
                textarea.click()
                time.sleep(0.3)
                
                # Thử nhiều cách paste
                paste_success = False
                
                # Cách 1: Ctrl+V
                try:
                    textarea.send_keys(Keys.CONTROL, 'v')
                    gemini_logger.debug("  📋 Tried Ctrl+V paste")
                    paste_success = True
                except:
                    pass
                
                # Cách 2: JavaScript paste
                if not paste_success:
                    try:
                        self.driver.execute_script("document.execCommand('paste');")
                        gemini_logger.debug("  📋 Tried execCommand paste")
                        paste_success = True
                    except:
                        pass
                
                # Cách 3: Clipboard event
                if not paste_success:
                    try:
                        self.driver.execute_script("""
                            var elem = arguments[0];
                            var event = new ClipboardEvent('paste', {
                                bubbles: true
                            });
                            elem.dispatchEvent(event);
                        """, textarea)
                        gemini_logger.debug("  📋 Tried raw paste event")
                        paste_success = True
                    except:
                        pass
                
                time.sleep(1.5)
                
                # Kiểm tra kết quả
                uploaded_count = self._count_uploaded_images_detailed()
                if uploaded_count > 0:
                    gemini_logger.info(f"  ✅ Upload successful! Found {uploaded_count} image(s)")
                    
                    # Clear clipboard và release
                    try:
                        if sys.platform == "win32":
                            import win32clipboard
                            win32clipboard.OpenClipboard()
                            win32clipboard.EmptyClipboard()
                            win32clipboard.CloseClipboard()
                    except:
                        pass
                    
                    self.clipboard_manager.release_clipboard(self.program_id)
                    self.clipboard_manager.clear_clipboard(self.program_id)
                    
                    time.sleep(0.8)
                    return True
                else:
                    gemini_logger.warning("  ⚠️ No images detected after paste")
                
                # Release clipboard để thử lại
                self.clipboard_manager.release_clipboard(self.program_id)
                
                if attempt < max_attempts - 1:
                    wait_time = 2.0 * (attempt + 1)
                    gemini_logger.info(f"  ⏳ Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                
            except Exception as e:
                gemini_logger.error(f"  ❌ Real clipboard attempt {attempt + 1} error: {e}")
                self.clipboard_manager.release_clipboard(self.program_id)
                
                if attempt < max_attempts - 1:
                    time.sleep(2.0)
        
        gemini_logger.error(f"  ❌ Real clipboard failed after {max_attempts} attempts")
        return False
    
    def _copy_to_clipboard_advanced(self, image_path):
        """Copy ảnh vào clipboard với xử lý nâng cao"""
        try:
            file_size = os.path.getsize(image_path)
            gemini_logger.info(f"  📁 File size: {file_size:,} bytes")
            
            if file_size == 0:
                gemini_logger.error("  ❌ Empty image file")
                return False
            
            # Xử lý ảnh với PIL
            img = Image.open(image_path)
            gemini_logger.info(f"  🖼️ Image format: {img.format}, size: {img.size}, mode: {img.mode}")
            
            if img.mode != 'RGB':
                img = img.convert('RGB')
                gemini_logger.info(f"  🔄 Converted to RGB mode")
            
            # Resize nếu ảnh quá lớn
            if file_size > 5 * 1024 * 1024:
                gemini_logger.info(f"  📏 Image too large ({file_size:,} bytes), resizing...")
                max_dimension = 2048
                ratio = max_dimension / max(img.size)
                new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                gemini_logger.info(f"  🔄 Resized to: {new_size}")
            
            # Chuyển sang BMP để copy vào clipboard
            output = io.BytesIO()
            img.save(output, 'BMP')
            data = output.getvalue()
            output.close()
            
            if len(data) > 14:
                dib_data = data[14:]
                gemini_logger.info(f"  📋 Prepared DIB data: {len(dib_data):,} bytes")
            else:
                gemini_logger.error("  ❌ Invalid BMP data")
                return False
            
            # Copy vào clipboard (Windows)
            if sys.platform == "win32":
                import win32clipboard
                
                gemini_logger.info("  📋 Copying to clipboard...")
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                
                try:
                    win32clipboard.SetClipboardData(win32clipboard.CF_DIB, dib_data)
                    gemini_logger.info("  ✅ Copied as CF_DIB")
                    win32clipboard.CloseClipboard()
                    return True
                except Exception as dib_error:
                    gemini_logger.warning(f"  ⚠️ CF_DIB failed: {dib_error}")
                    
                    try:
                        # Thử lại với toàn bộ BMP data
                        output = io.BytesIO()
                        img.save(output, 'BMP')
                        bmp_data = output.getvalue()
                        output.close()
                        
                        win32clipboard.SetClipboardData(win32clipboard.CF_BITMAP, bmp_data)
                        gemini_logger.info("  ✅ Copied as CF_BITMAP")
                        win32clipboard.CloseClipboard()
                        return True
                    except Exception as bmp_error:
                        gemini_logger.error(f"  ❌ CF_BITMAP also failed: {bmp_error}")
                        win32clipboard.CloseClipboard()
                        return False
            else:
                gemini_logger.error(f"  ❌ Unsupported platform: {sys.platform}")
                return False
                
        except Exception as e:
            gemini_logger.error(f"  ❌ Copy to clipboard error: {e}")
            return False
    
    def _count_uploaded_images_detailed(self):
        """Đếm ảnh đã upload - chi tiết hơn"""
        try:
            time.sleep(0.8)
            selectors = [
                "//img[contains(@src, 'blob:')]",
                "//img[contains(@src, 'data:image')]",
                "//img[contains(@src, 'googleusercontent.com')]",
                "//img[contains(@class, 'uploaded-image')]",
                "//img[contains(@class, 'image-thumbnail')]",
                "//img[@alt='Uploaded image']",
                "//img[contains(@alt, 'image')]",
            ]
            
            all_images = []
            for selector in selectors:
                try:
                    images = self.driver.find_elements(By.XPATH, selector)
                    for img in images:
                        try:
                            if img.is_displayed():
                                src = img.get_attribute('src') or ''
                                alt = img.get_attribute('alt') or ''
                                gemini_logger.debug(f"  📸 Found image: src={src[:50]}, alt={alt}")
                                all_images.append(img)
                        except:
                            continue
                except:
                    continue
            
            gemini_logger.info(f"  🔍 Detailed image check found {len(all_images)} images")
            return len(all_images)
            
        except Exception as e:
            gemini_logger.error(f"  ❌ Detailed count error: {e}")
            return 0
    
    def _upload_via_file_input(self, image_path):
        """Thử upload bằng input file element"""
        try:
            gemini_logger.info("📁 Trying file input upload...")
            
            file_inputs = self.driver.find_elements(By.XPATH, "//input[@type='file']")
            
            if not file_inputs:
                gemini_logger.warning("⚠️ No file input found")
                return False
            
            for file_input in file_inputs:
                try:
                    if file_input.is_displayed():
                        file_input.send_keys(os.path.abspath(image_path))
                        gemini_logger.info("✅ File sent via input")
                        
                        time.sleep(2.0)
                        
                        uploaded = self._count_uploaded_images_detailed()
                        if uploaded > 0:
                            gemini_logger.info(f"✅ File upload successful: {uploaded} images")
                            return True
                except Exception as e:
                    gemini_logger.debug(f"⚠️ File input error: {e}")
                    continue
            
            return False
            
        except Exception as e:
            gemini_logger.error(f"❌ File input upload error: {e}")
            return False
    
    def _upload_single_image_reliable(self, image_path):
        """Upload ảnh với multiple fallback methods"""
        try:
            gemini_logger.info(f"📤 UPLOADING: {os.path.basename(image_path)}")
            
            # Sử dụng phương pháp hybrid mới
            if self._upload_image_hybrid(image_path):
                return True
            
            gemini_logger.warning("🔄 All hybrid methods failed, trying alternatives...")
            
            # Fallback cũ
            try:
                time.sleep(1)
                textarea = self._get_textarea_element()
                if textarea:
                    js_drag_drop = """
                    var fileInput = document.createElement('input');
                    fileInput.type = 'file';
                    fileInput.style.display = 'none';
                    document.body.appendChild(fileInput);
                    
                    fileInput.onchange = function(e) {
                        var file = e.target.files[0];
                        var reader = new FileReader();
                        
                        reader.onload = function(e) {
                            var img = new Image();
                            img.src = e.target.result;
                            
                            var blob = new Blob([e.target.result], {type: 'image/jpeg'});
                            var blobUrl = URL.createObjectURL(blob);
                            
                            var imgElem = document.createElement('img');
                            imgElem.src = blobUrl;
                            imgElem.style.maxWidth = '300px';
                            imgElem.style.maxHeight = '300px';
                            
                            var chatBox = document.querySelector('[contenteditable="true"]');
                            if (chatBox) {
                                chatBox.appendChild(imgElem);
                            }
                        };
                        
                        reader.readAsArrayBuffer(file);
                    };
                    
                    fileInput.click();
                    """
                    self.driver.execute_script(js_drag_drop)
                    time.sleep(2)
                    
                    if self._count_uploaded_images_detailed() > 0:
                        gemini_logger.info("✅ Drag-drop upload successful")
                        return True
            except Exception as e:
                gemini_logger.debug(f"⚠️ Drag-drop error: {e}")
            
            gemini_logger.info("🔄 Reloading page and retrying...")
            self.driver.get(GEMINI_URL)
            time.sleep(3)
            
            if self._upload_image_hybrid(image_path):
                return True
            
            gemini_logger.error("❌ All upload methods failed")
            return False
            
        except Exception as e:
            gemini_logger.error(f"❌ Upload error: {e}")
            return False
    
    def _enter_prompt_direct(self):
        """Nhập prompt trực tiếp"""
        try:
            gemini_logger.info("💬 Entering prompt directly...")
            
            textarea = self._get_textarea_element()
            if not textarea:
                return False
            
            textarea.click()
            time.sleep(0.3)
            
            textarea.send_keys(Keys.END)
            time.sleep(0.2)
            
            try:
                current_text = textarea.text or ""
                if current_text and not current_text.endswith(' '):
                    textarea.send_keys(' ')
                    time.sleep(0.1)
            except:
                pass
            
            textarea.send_keys(GEMINI_PROMPT)
            time.sleep(0.3)
            
            gemini_logger.info("✅ Prompt added")
            return True
            
        except Exception as e:
            gemini_logger.error(f"Prompt entry error: {e}")
            return False
    
    # ========== IMAGE UPLOAD CƠ BẢN ==========
    
    def _clean_temp_folder(self):
        """Dọn thư mục tạm"""
        try:
            temp_download_dir = os.path.join(DOWNLOADS_DIR, "temp_download")
            if os.path.exists(temp_download_dir):
                for filename in os.listdir(temp_download_dir):
                    filepath = os.path.join(temp_download_dir, filename)
                    try:
                        if os.path.isfile(filepath):
                            os.remove(filepath)
                    except:
                        pass
            return True
        except:
            return False
    
    def _ensure_stable_browser(self):
        """Đảm bảo trình duyệt ổn định"""
        try:
            gemini_logger.info("⚙️ Waiting for browser stability...")
            
            time.sleep(2.0)
            
            try:
                ready_state = self.driver.execute_script("return document.readyState")
                if ready_state != "complete":
                    gemini_logger.info(f"⏳ Still loading: {ready_state}")
                    for _ in range(5):
                        time.sleep(0.5)
                        ready_state = self.driver.execute_script("return document.readyState")
                        if ready_state == "complete":
                            break
            except:
                pass
            
            gemini_indicators = [
                "//*[contains(text(), 'Gemini')]",
                "//*[contains(text(), 'Ask Gemini')]",
                "//*[contains(@placeholder, 'Ask Gemini')]",
            ]
            
            for indicator in gemini_indicators:
                try:
                    elements = self.driver.find_elements(By.XPATH, indicator)
                    if elements:
                        gemini_logger.info("✅ Gemini interface detected")
                        break
                except:
                    continue
            
            textarea = self._get_textarea_element()
            if not textarea:
                gemini_logger.warning("⚠️ Textarea not ready, retrying...")
                for _ in range(3):
                    time.sleep(0.8)
                    textarea = self._get_textarea_element()
                    if textarea:
                        break
            
            if not textarea:
                gemini_logger.error("❌ Textarea not found after multiple attempts")
                return False
            
            try:
                textarea.click()
                time.sleep(0.5)
                try:
                    textarea.clear()
                    time.sleep(0.3)
                except:
                    pass
                gemini_logger.info("✅ Browser stable and textarea ready")
                return True
            except Exception as e:
                gemini_logger.warning(f"⚠️ Cannot focus textarea: {e}")
                return True
                
        except Exception as e:
            gemini_logger.error(f"❌ Browser stability error: {e}")
            return True
    
    def _upload_single_image(self, image_path):
        """Upload ảnh chính"""
        try:
            gemini_logger.info(f"📤 UPLOAD MAIN: {os.path.basename(image_path)}")
            
            self._clean_temp_folder()
            
            if not os.path.exists(image_path):
                gemini_logger.error(f"❌ Image file missing: {image_path}")
                return False
            
            self.driver.get(GEMINI_URL)
            time.sleep(2.5)
            
            if not self._ensure_stable_browser():
                gemini_logger.warning("⚠️ Browser not stable, trying anyway...")
            
            return self._upload_single_image_reliable(image_path)
            
        except Exception as e:
            gemini_logger.error(f"❌ Main upload error: {e}")
            return False
    
    def _get_textarea_element(self):
        """Tìm textarea"""
        try:
            selectors = [
                "//div[@contenteditable='true' and @role='textbox']",
                "//textarea[@id='mat-input-0']",
                "//textarea",
                "//input[@type='text']",
                "//div[contains(@class, 'ql-editor')]",
            ]
            
            for _ in range(5):
                for selector in selectors:
                    try:
                        elements = self.driver.find_elements(By.XPATH, selector)
                        for elem in elements:
                            try:
                                if elem.is_displayed() and elem.is_enabled():
                                    gemini_logger.debug(f"✅ Found textarea: {selector}")
                                    return elem
                            except:
                                continue
                    except:
                        continue
                
                time.sleep(0.8)
            
            gemini_logger.error("❌ No textarea found")
            return None
            
        except Exception as e:
            gemini_logger.error(f"Textarea error: {e}")
            return None
    
    def _count_uploaded_images(self):
        """Đếm ảnh đã upload"""
        try:
            time.sleep(0.5)
            selectors = [
                "//img[contains(@src, 'blob:')]",
                "//img[contains(@src, 'data:image')]",
                "//img[contains(@src, 'googleusercontent.com')]",
                "//img[contains(@class, 'uploaded-image')]",
                "//img[contains(@class, 'image-thumbnail')]",
            ]
            
            all_images = set()
            for selector in selectors:
                try:
                    images = self.driver.find_elements(By.XPATH, selector)
                    for img in images:
                        try:
                            src = img.get_attribute('src') or ''
                            if src:
                                all_images.add(src)
                        except:
                            continue
                except:
                    continue
            
            return len(all_images)
        except:
            return 0
    
    # ========== PROMPT & WORKFLOW ==========
    
    def _enter_prompt(self):
        """Nhập prompt (lần đầu)"""
        try:
            gemini_logger.info("💬 Entering prompt (first time)...")
            
            textarea = self._get_textarea_element()
            if not textarea:
                return False
            
            textarea.click()
            time.sleep(0.3)
            
            try:
                textarea.clear()
                time.sleep(0.2)
            except:
                pass
            
            textarea.send_keys("1")
            time.sleep(0.3)
            
            try:
                js_script = f"""
                var textarea = arguments[0];
                var promptText = `{GEMINI_PROMPT}`;
                
                if (textarea.value) {{
                    textarea.value = textarea.value + promptText;
                }} else if (textarea.innerText) {{
                    textarea.innerText = textarea.innerText + promptText;
                }} else if (textarea.textContent) {{
                    textarea.textContent = textarea.textContent + promptText;
                }}
                
                var event = new Event('input', {{ bubbles: true }});
                textarea.dispatchEvent(event);
                """
                
                self.driver.execute_script(js_script, textarea)
                gemini_logger.info("✅ Prompt set via JS")
                time.sleep(0.3)
            except:
                textarea.send_keys(GEMINI_PROMPT)
            
            textarea.send_keys("1")
            time.sleep(0.3)
            
            gemini_logger.info("✅ Prompt entered")
            return True
            
        except Exception as e:
            gemini_logger.error(f"Prompt error: {e}")
            return False
    
    def _click_tools_menu(self):
        """Click menu Tools"""
        try:
            gemini_logger.info("🔧 Clicking Tools menu...")
            time.sleep(0.6)
            
            selectors = [
                "//span[text()='Công cụ']",
                "//button[.//span[text()='Công cụ']]",
                "//div[text()='Công cụ']",
                "//button[contains(@aria-label, 'Công cụ')]",
                "//button[contains(@aria-label, 'Tools')]",
                "//div[text()='Tools']",
            ]
            
            for selector in selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    for element in elements:
                        try:
                            if element.is_displayed() and element.is_enabled():
                                self.driver.execute_script("arguments[0].click();", element)
                                time.sleep(0.6)
                                
                                menu_options = self.driver.find_elements(By.XPATH, 
                                    "//div[contains(text(), 'Tạo hình ảnh') or contains(text(), 'Image')]")
                                
                                if menu_options:
                                    gemini_logger.info("✅ Tools menu opened")
                                    return True
                        except:
                            continue
                except:
                    continue
            
            return False
            
        except Exception as e:
            gemini_logger.error(f"Tools menu error: {e}")
            return False
    
    def _select_image_generation(self):
        """Chọn Image Generation"""
        try:
            gemini_logger.info("🎨 Selecting Image Generation...")
            time.sleep(0.4)
            
            selectors = [
                "//div[@aria-label='Tạo hình ảnh' and @role='option']",
                "//div[@role='option' and contains(text(), 'Tạo hình ảnh')]",
                "//div[@aria-label='Tạo hình ảnh']",
                "//div[text()='Tạo hình ảnh' and @role='menuitem']",
                "//div[text()='Tạo hình ảnh']",
                "//div[contains(text(), 'Tạo hình ảnh')]",
                "//div[@aria-label='Image generation' and @role='option']",
                "//div[@role='option' and contains(text(), 'Image generation')]",
                "//div[@aria-label='Image generation']",
                "//div[text()='Image generation']",
                "//div[contains(text(), 'Image generation')]",
            ]
            
            for selector in selectors:
                try:
                    js_script = f"""
                    var element = document.evaluate(
                        "{selector.replace('"', '\\"')}",
                        document,
                        null,
                        XPathResult.FIRST_ORDERED_NODE_TYPE,
                        null
                    ).singleNodeValue;
                    
                    if (element) {{
                        element.click();
                        return true;
                    }}
                    return false;
                    """
                    
                    result = self.driver.execute_script(js_script)
                    if result:
                        gemini_logger.info(f"✅ Image generation selected")
                        time.sleep(0.2)
                        return True
                except:
                    continue
            
            return False
            
        except Exception as e:
            gemini_logger.error(f"Image generation error: {e}")
            return False
    
    def _send_prompt_final(self):
        """Gửi prompt cuối"""
        try:
            gemini_logger.info("📤 Preparing to send prompt...")
            
            if not self._ensure_work_area_has_content(self.current_temp_image_path):
                gemini_logger.error("❌ Work area missing content")
                return False
            
            gemini_logger.info("⏳ Waiting 1.5s for content stability...")
            if not self._wait_for_content_stability():
                gemini_logger.warning("⚠️ Content not fully stable, continuing...")
            
            textarea = self._get_textarea_element()
            if not textarea:
                return False
            
            self.driver.execute_script("arguments[0].focus();", textarea)
            time.sleep(0.15)
            
            textarea.send_keys(Keys.RETURN)
            time.sleep(0.2)
            
            gemini_logger.info("✅ Prompt sent")
            return True
            
        except Exception as e:
            gemini_logger.error(f"Send prompt error: {e}")
            return False
    
    # ========== XỬ LÝ QUOTA MỚI ==========
    
    def _handle_quota_wait(self, text):
        """Xử lý chờ khi hết hạn mức - CỘNG THÊM 20 PHÚT"""
        try:
            gemini_logger.error("🛑 PHÁT HIỆN HẠN MỨC SỬ DỤNG!")
            
            match = re.search(r"(\w{3} \d{1,2}, \d{1,2}:\d{2} [AP]M)", text)
            
            wait_seconds = 3600
            reset_time_str = "Unknown"
            resume_time_str = "Unknown"

            if match:
                date_str = match.group(1)
                
                try:
                    reset_time = datetime.strptime(date_str, "%b %d, %I:%M %p")
                    now = datetime.now()
                    reset_time = reset_time.replace(year=now.year)
                    
                    if reset_time < now and (now.month == 12 and reset_time.month == 1):
                        reset_time = reset_time.replace(year=now.year + 1)
                    
                    reset_time_str = reset_time.strftime("%Y-%m-%d %H:%M:%S")

                    resume_time = reset_time + timedelta(minutes=20)
                    resume_time_str = resume_time.strftime("%Y-%m-%d %H:%M:%S")

                    diff = resume_time - now
                    wait_seconds = diff.total_seconds()
                    
                    if wait_seconds < 0:
                        wait_seconds = 60 
                        
                except Exception as e:
                    gemini_logger.error(f"❌ Date parsing error: {e}")
            
            hours = int(wait_seconds // 3600)
            minutes = int((wait_seconds % 3600) // 60)
            seconds = int(wait_seconds % 60)
            
            msg = f"""
            ╔════════════════════════════════════════════════════════════╗
            ║                 ⛔ QUOTA LIMIT REACHED                     ║
            ╠════════════════════════════════════════════════════════════╣
            ║ Original Text : {text.strip()}
            ║ Reset Time    : {reset_time_str}
            ║ Buffer Time   : +20 minutes
            ║ RESUME AT     : {resume_time_str}
            ║ Waiting for   : {hours}h {minutes}m {seconds}s
            ╚════════════════════════════════════════════════════════════╝
            """
            print(msg)
            gemini_logger.warning(msg)
            
            start_wait = time.time()
            while time.time() - start_wait < wait_seconds:
                remaining = wait_seconds - (time.time() - start_wait)
                
                r_h = int(remaining // 3600)
                r_m = int((remaining % 3600) // 60)
                r_s = int(remaining % 60)
                
                sys.stdout.write(f"\r⏳ PAUSED: Resume at {resume_time_str} | Remaining: {r_h:02d}:{r_m:02d}:{r_s:02d}   ")
                sys.stdout.flush()
                time.sleep(1)
            
            print("\n\n✅ Resume time reached. Restarting browser session...")
            return True
            
        except Exception as e:
            gemini_logger.error(f"❌ Handle quota error: {e}")
            time.sleep(3600)
            return True

    # ========== QUÉT VÀ TẢI ẢNH (UPDATED FOR MAIN CHAT ONLY) ==========
    
    def _get_chat_frame_element(self):
        """
        Tìm element bao quanh khung chat chính và LOẠI TRỪ thanh sidebar.
        Cập nhật: Dùng logic tổ tiên (ancestor) để tránh bắt nhầm lịch sử chat.
        """
        try:
            # Các selector ưu tiên tìm khung chat chính
            selectors = [
                # Cách 1: Tìm infinite-scroller nằm TRỰC TIẾP trong chat-window (Chính xác nhất)
                "//chat-window//infinite-scroller",
                
                # Cách 2: Tìm infinite-scroller nhưng LOẠI TRỪ cái nằm trong thanh bên (sidenav)
                "//infinite-scroller[not(ancestor::bard-sidenav-content) and not(ancestor::mat-sidenav)]",
                
                # Cách 3: Tìm thẻ main (thường chứa nội dung chính)
                "//main//infinite-scroller",
                
                # Cách 4: Tìm div chứa lịch sử chat (nếu cấu trúc đổi)
                "//div[contains(@class, 'chat-history-scroll-container')]"
            ]
            
            for selector in selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    for element in elements:
                        # Kiểm tra hiển thị và kích thước
                        if element.is_displayed():
                            size = element.size
                            # Khung chat chính luôn to hơn khung sidebar (thường sidebar < 300px)
                            if size['width'] > 350 and size['height'] > 300:
                                # gemini_logger.debug(f"✅ Found MAIN chat frame: {selector}")
                                return element
                except:
                    continue
            
            # Fallback: Nếu không tìm thấy khung cụ thể, dùng driver (chấp nhận rủi ro quét toàn trang)
            gemini_logger.warning("⚠️ Could not locate specific Chat Frame, falling back to full page.")
            return self.driver
            
        except Exception as e:
            gemini_logger.error(f"Error finding chat frame: {e}")
            return self.driver

    def _continuous_scan_for_completion(self, timeout=120):
        """Quét liên tục chờ hoàn thành (CHỈ QUÉT TRONG KHUNG CHAT CHÍNH)"""
        try:
            gemini_logger.info("🔍 Starting continuous scan in MAIN CHAT FRAME...")
            start_time = time.time()
            
            # 1. Lấy khung chat chính ngay từ đầu
            chat_frame = self._get_chat_frame_element()
            
            scan_count = 0
            
            # Định nghĩa XPath lỗi quota để dùng lại nhiều lần
            quota_xpath = "//*[contains(text(), 'hạn mức được đặt lại') or contains(text(), 'hạn mức sử dụng') or contains(text(), 'reached your Nano Banana Pro limit') or contains(text(), 'limit resets on')]"

            while time.time() - start_time < timeout:
                scan_count += 1
                elapsed = time.time() - start_time
                
                if scan_count % 10 == 0:
                    gemini_logger.info(f"  Scan #{scan_count} - {elapsed:.1f}s elapsed")
                
                try:
                    # Kiểm tra kết nối khung chat
                    try:
                        chat_frame.is_enabled()
                    except:
                        chat_frame = self._get_chat_frame_element()

                    # --- 1. ƯU TIÊN CAO NHẤT: QUÉT LỖI HẠN MỨC (Quota) ---
                    try:
                        quota_elements = self.driver.find_elements(By.XPATH, quota_xpath)
                        if quota_elements:
                            for elem in quota_elements:
                                if elem.is_displayed():
                                    text = elem.text
                                    # Kiểm tra kỹ nội dung text để tránh bắt nhầm
                                    if "Dec" in text or "Jan" in text or "Feb" in text or "AM" in text or "PM" in text or "hạn mức" in text:
                                        self._handle_quota_wait(text)
                                        return "quota_reset"
                    except:
                        pass

                    # --- 2. Check generated image (CÓ KIỂM TRA KÉP) ---
                    google_images = chat_frame.find_elements(By.XPATH,
                        ".//img[contains(@src, 'googleusercontent.com') and starts-with(@src, 'http')]")
                    
                    if google_images:
                        visible_images = []
                        for img in google_images:
                            try:
                                if img.is_displayed() and img.size['width'] > 150:
                                    visible_images.append(img)
                            except:
                                continue
                        
                        if visible_images:
                            # =================================================================
                            # 🛑 FIX STRICT: KHÔNG ĐƯỢC RETURN NGAY!
                            # Phải chờ xem thông báo lỗi có xuất hiện chậm hơn ảnh không.
                            # =================================================================
                            gemini_logger.info("👀 Ảnh đã hiện, nhưng đang chờ kiểm tra lỗi (Double Check)...")
                            time.sleep(2.5) # Chờ 2.5 giây - Thời gian vàng để thông báo lỗi kịp hiện ra

                            # KIỂM TRA LẠI QUOTA LẦN 2
                            try:
                                q_elems_check = self.driver.find_elements(By.XPATH, quota_xpath)
                                for q in q_elems_check:
                                    if q.is_displayed():
                                        gemini_logger.warning("🚨 Phát hiện lỗi Quota xuất hiện SAU ảnh! Hủy nhận ảnh.")
                                        self._handle_quota_wait(q.text)
                                        return "quota_reset" # Trả về quota_reset để retry ảnh này
                            except:
                                pass

                            # KIỂM TRA LẠI ERROR TEXT LẦN 2
                            err_check = chat_frame.find_elements(By.XPATH, 
                                ".//*[contains(text(), 'Error') or contains(text(), 'Lỗi')]")
                            for e in err_check:
                                if e.is_displayed():
                                     gemini_logger.warning("🚨 Phát hiện thông báo Lỗi xuất hiện SAU ảnh!")
                                     return "error"

                            # Nếu sau khi chờ mà vẫn không thấy lỗi -> Mới xác nhận là OK
                            gemini_logger.info(f"🖼️ CONFIRMED: {len(visible_images)} Google images (Clean check pass)")
                            return "processed"
                    
                    # --- 3. Check "Clean Image" ---
                    clean_text = chat_frame.find_elements(By.XPATH,
                        ".//*[contains(text(), 'Ảnh sạch không có tiếng trung và domain')]")
                    if clean_text:
                        for elem in clean_text:
                            if elem.is_displayed():
                                return "clean"
                    
                    # --- 4. Check "Delete Image" ---
                    delete_text = chat_frame.find_elements(By.XPATH,
                        ".//*[contains(text(), 'Ảnh này cần xóa')]")
                    if delete_text:
                        for elem in delete_text:
                            if elem.is_displayed():
                                return "delete"
                    
                    # --- 5. Check Policy Violation ---
                    try:
                        policy_elements = chat_frame.find_elements(By.XPATH, ".//*[text()[substring(., string-length(.)) = '?']]")
                        for elem in policy_elements:
                             if elem.is_displayed() and len(elem.text) < 200:
                                 return "fallback_policy"
                    except:
                        pass
                    
                    # --- 6. Check Loading ---
                    loading_elements = chat_frame.find_elements(By.XPATH,
                        ".//*[contains(text(), 'Generating') or contains(text(), 'Đang tạo') or contains(@class, 'loading')]")
                    if loading_elements:
                        time.sleep(1.0)
                        continue
                    
                    # --- 7. Check Error ---
                    error_elements = chat_frame.find_elements(By.XPATH,
                        ".//*[contains(text(), 'Error') or contains(text(), 'Lỗi') or contains(text(), 'Sorry')]")
                    if error_elements:
                        for elem in error_elements:
                            if elem.is_displayed():
                                return "error"
                    
                    time.sleep(0.8)
                    
                except Exception as e:
                    gemini_logger.debug(f"  Scan loop hiccup: {str(e)[:50]}")
                    time.sleep(1.0)
            
            gemini_logger.warning(f"⏰ TIMEOUT: {timeout}s")
            return "timeout"
            
        except Exception as e:
            gemini_logger.error(f"❌ Scan error: {e}")
            return "error"
    
    def _download_processed_image(self):
        """Tải ảnh đã xử lý (CHỈ TỪ KHUNG CHAT CHÍNH)"""
        try:
            gemini_logger.info("📥 Downloading processed image from MAIN FRAME...")
            time.sleep(1.0)
            
            # 1. Lấy khung chat chính
            chat_frame = self._get_chat_frame_element()
            
            # 2. Tìm ảnh TRONG khung chat (Dùng .//)
            # Thêm điều kiện lọc kích thước để tránh các icon nhỏ
            google_images = chat_frame.find_elements(By.XPATH,
                ".//img[contains(@src, 'googleusercontent.com') and starts-with(@src, 'http')]")
            
            if not google_images:
                gemini_logger.warning("⚠️ No Google images found in chat frame")
                return None
            
            # Duyệt ngược từ dưới lên (ảnh mới nhất thường ở cuối)
            for img in reversed(google_images):
                try:
                    if img.is_displayed():
                        # Kiểm tra kích thước: Ảnh kết quả phải đủ lớn (ví dụ > 200px)
                        # Ảnh thumbnail trong sidebar thường nhỏ (khoảng 100-150px)
                        if img.size['width'] < 200:
                            continue

                        src = img.get_attribute("src")
                        if not src:
                            continue
                        
                        gemini_logger.info(f"📥 Downloading: {src[:80]}...")
                        
                        # --- Giữ nguyên logic requests session ---
                        session = requests.Session()
                        for cookie in self.driver.get_cookies():
                            session.cookies.set(cookie['name'], cookie['value'])
                        
                        headers = {
                            'User-Agent': self.driver.execute_script("return navigator.userAgent;"),
                            'Referer': GEMINI_URL,
                        }
                        
                        response = session.get(src, headers=headers, timeout=15)
                        
                        if response.status_code == 200 and 'image' in response.headers.get('content-type', ''):
                            gemini_temp_dir = os.path.join(TEMP_IMAGES_DIR, "gemini_temp_keep")
                            os.makedirs(gemini_temp_dir, exist_ok=True)
                            
                            timestamp = int(time.time())
                            random_str = str(uuid.uuid4())[:8]
                            filename = f"gemini_{timestamp}_{random_str}.png"
                            filepath = os.path.join(gemini_temp_dir, filename)
                            
                            with open(filepath, 'wb') as f:
                                f.write(response.content)
                            
                            file_size = len(response.content)
                            gemini_logger.info(f"✅ Saved: {file_size:,} bytes -> {filepath}")
                            
                            # --- Giữ nguyên logic resize ---
                            if self.original_width:
                                try:
                                    with Image.open(filepath) as img_check:
                                        width, height = img_check.size
                                        if width != self.original_width:
                                            resized_path = self._resize_to_original_width(filepath, self.original_width)
                                            return resized_path
                                except:
                                    pass
                            
                            return filepath
                        
                        # Nếu tải được ảnh đầu tiên hợp lệ thì dừng luôn
                        break
                except Exception as e:
                    gemini_logger.debug(f"Download error for specific image: {e}")
                    continue
            
            return None
            
        except Exception as e:
            gemini_logger.error(f"❌ Download error: {e}")
            return None
    
    # ========== WORKFLOW CHÍNH ==========
    
    def send_prompt_with_image_generation_mode(self):
        """Workflow chính - Gửi prompt với chế độ tạo ảnh"""
        try:
            gemini_logger.info("🔄 Starting Image Generation workflow...")
            
            if not self._ensure_work_area_has_content(self.current_temp_image_path):
                gemini_logger.error("❌ Work area incomplete")
                return "error"
            
            if not self._click_tools_menu():
                gemini_logger.error("❌ Failed to open Tools")
                return "error"
            
            if not self._select_image_generation():
                gemini_logger.error("❌ Failed to select Image Generation")
                return "error"
            
            time.sleep(0.2)
            
            gemini_logger.info(f"⏳ Waiting {self.STABLE_WAIT_TIME}s before sending...")
            time.sleep(self.STABLE_WAIT_TIME)
            
            if not self._send_prompt_final():
                gemini_logger.error("❌ Failed to send prompt")
                return "error"
            
            gemini_logger.info("✅ Prompt sent, scanning...")
            
            result = self._continuous_scan_for_completion(timeout=90)
            
            gemini_logger.info(f"Gemini result: {result}")
            return result
            
        except Exception as e:
            gemini_logger.error(f"❌ Workflow error: {e}")
            return "error"
    
    # ========== CÁC PHƯƠNG THỨC TRỢ GIÚP ==========
    
    def _extract_text_from_ocr_blocks(self, ocr_results):
        """Trích xuất text từ OCR results"""
        texts = []
        if ocr_results:
            for block in ocr_results:
                if isinstance(block, dict):
                    text = block.get('text', '')
                else:
                    try:
                        text = getattr(block, 'text', '')
                    except:
                        text = str(block)
                
                if text and text.strip():
                    texts.append(text.strip())
        
        return texts
    
    def get_fallback_data(self, image_path, filename, image_url, ocr_results):
        """Tạo dữ liệu fallback khi Gemini lỗi"""
        try:
            if os.path.exists(image_path):
                img_np = cv2.imread(image_path)
                if img_np is not None:
                    return {
                        'type': 'fallback_local',
                        'ocr_results': ocr_results,
                        'image_data': img_np,
                        'filename': filename,
                        'original_url': image_url,
                        'gemini_error': True
                    }
        except Exception as e:
            gemini_logger.error(f"❌ Cannot create fallback data: {e}")
        
        return None
    
    @log_function_call(gemini_logger)
    def process_single_image(self, image_data, filename, image_url, 
                             ocr_results=None, processed_blocks=None, ignore_blocks=None):
        """Xử lý 1 ảnh duy nhất với các tham số bổ sung cho fallback"""
        try:
            gemini_logger.info(f"🔄 Processing SINGLE image: {filename}")
            
            # Log upload stats
            gemini_logger.info(f"📊 Upload Statistics: {self.upload_stats}")
            
            if "188.com.vn/uploads" in image_url:
                gemini_logger.info("✅ 188.com.vn image - KEEP ORIGINAL")
                return "keep_original"
            
            try:
                nparr = np.frombuffer(image_data, np.uint8)
                img_cv = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img_cv is not None:
                    h, w = img_cv.shape[:2]
                    self.original_width = w
                    gemini_logger.info(f"📏 Original: {w}x{h}px")
                else:
                    self.original_width = None
            except Exception as e:
                gemini_logger.warning(f"⚠️ Cannot get size: {e}")
                self.original_width = None
            
            self.current_image_retries = 0
            
            while True:
                self.current_image_retries += 1
                gemini_logger.info(f"🔄 ATTEMPT {self.current_image_retries} for this image")
                
                if self.system_failure_mode:
                    gemini_logger.info("⏳ In system failure mode, waiting...")
                    while not self._check_system_failure_cooldown():
                        time.sleep(30)
                    
                    self.current_image_retries = 1
                
                if not self.ensure_driver_running():
                    gemini_logger.error("❌ Cannot ensure driver")
                    
                    wait_time = min(10 * self.current_image_retries, 45)
                    gemini_logger.info(f"⏳ Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    
                    if self.current_image_retries >= self.max_image_retries:
                        gemini_logger.error("⚠️ Too many driver attempts, system failure")
                        self._enter_system_failure_mode()
                        continue
                    
                    continue
                
                # ========== KIỂM TRA VÀ ĐẢM BẢO CHẾ ĐỘ PRO NGHIÊM NGẶT ==========
                gemini_logger.info("🔒 KIỂM TRA ĐIỀU KIỆN BẮT BUỘC: CHẾ ĐỘ PRO")
                
                if not self._ensure_pro_mode_strict(max_retries=2):
                    gemini_logger.critical("🚫 KHÔNG THỂ ĐẢM BẢO CHẾ ĐỘ PRO - TẠM DỪNG XỬ LÝ")
                    
                    # Thử phương pháp reset mạnh
                    gemini_logger.info("🔄 Thử phương pháp reset mạnh để chuyển sang Pro...")
                    if not self._force_pro_mode_with_reset():
                        gemini_logger.error("❌ Không thể chuyển sang Pro sau reset mạnh")
                    
                    # Tạm dừng và reset
                    wait_time = min(30 * self.current_image_retries, 120)
                    gemini_logger.info(f"⏳ Tạm dừng {wait_time}s và reset driver...")
                    time.sleep(wait_time)
                    
                    # Reset hoàn toàn
                    self._reset_driver_hard(save_position=True)
                    
                    # Tăng retry count
                    self.current_image_retries += 1
                    if self.current_image_retries >= self.max_image_retries:
                        gemini_logger.error("⚠️ Quá nhiều lỗi Pro mode, vào chế độ failure")
                        self._enter_system_failure_mode()
                        continue
                    
                    # Quay lại đầu vòng lặp để thử lại
                    continue
                
                # ========== CHỈ TIẾP TỤC KHI ĐÃ Ở PRO ==========
                gemini_logger.info("✅ ĐÃ Ở CHẾ ĐỘ PRO - TIẾN HÀNH XỬ LÝ ẢNH")
                
                try:
                    temp_dir = os.path.join(TEMP_IMAGES_DIR, "current")
                    os.makedirs(temp_dir, exist_ok=True)
                    
                    for old_file in os.listdir(temp_dir):
                        try:
                            os.remove(os.path.join(temp_dir, old_file))
                        except:
                            pass
                    
                    temp_path = os.path.join(temp_dir, filename[:100])
                    with open(temp_path, 'wb') as f:
                        f.write(image_data)
                    
                    self.current_temp_image_path = temp_path
                    
                    if ocr_results is not None:
                        ocr_temp_path = temp_path + "_ocr.json"
                        try:
                            with open(ocr_temp_path, 'w', encoding='utf-8') as f:
                                ocr_serializable = []
                                for block in ocr_results:
                                    if isinstance(block, dict):
                                        ocr_serializable.append(block)
                                    else:
                                        try:
                                            ocr_serializable.append({
                                                'text': getattr(block, 'text', ''),
                                                'bbox': getattr(block, 'bbox', []),
                                                'confidence': getattr(block, 'confidence', 0.0)
                                            })
                                        except:
                                            ocr_serializable.append({'text': str(block)})
                                json.dump(ocr_serializable, f, ensure_ascii=False, indent=2)
                        except Exception as e:
                            gemini_logger.debug(f"⚠️ Cannot save OCR temp: {e}")
                    
                    gemini_logger.info("⏳ Waiting before upload...")
                    time.sleep(self.STABLE_WAIT_TIME)
                    
                    if not self._upload_single_image(temp_path):
                        gemini_logger.error("❌ Upload failed")
                        os.remove(temp_path)
                        self.current_temp_image_path = None
                        
                        retry_wait = min(5 * self.current_image_retries, 25)
                        gemini_logger.info(f"⏳ Waiting {retry_wait}s before retry upload...")
                        time.sleep(retry_wait)
                        
                        if self.current_image_retries >= self.max_image_retries:
                            gemini_logger.error(f"⚠️ {self.max_image_retries} upload failures")
                            self._enter_system_failure_mode()
                        else:
                            self._handle_error(f"Upload failed - Attempt {self.current_image_retries}")
                        
                        continue
                    
                    gemini_logger.info("✅ Upload successful, waiting...")
                    time.sleep(self.STABLE_WAIT_TIME)
                    
                    has_image, has_prompt = self._check_work_area_content()
                    
                    if not has_prompt:
                        gemini_logger.info("💬 Entering prompt...")
                        if not self._enter_prompt():
                            gemini_logger.error("❌ Cannot enter prompt")
                            os.remove(temp_path)
                            self.current_temp_image_path = None
                            
                            error_wait = min(4 * self.current_image_retries, 20)
                            gemini_logger.info(f"⏳ Waiting {error_wait}s after prompt error...")
                            time.sleep(error_wait)
                            
                            if self.current_image_retries >= self.max_image_retries:
                                gemini_logger.error(f"⚠️ {self.max_image_retries} prompt failures")
                                self._enter_system_failure_mode()
                            else:
                                self._handle_error(f"Prompt failed - Attempt {self.current_image_retries}")
                            
                            continue
                    
                    # Gọi phương thức workflow chính
                    result = self.send_prompt_with_image_generation_mode()
                    gemini_logger.info(f"Gemini result: {result}")
                    
                    if result == "quota_reset":
                        gemini_logger.info("🔄 Quota wait finished. Refreshing and retrying...")
                        try:
                            self.driver.refresh()
                            time.sleep(5)
                        except:
                            self.ensure_driver_running()
                        
                        self.current_image_retries = 0
                        continue

                    elif result == "clean":
                        os.remove(temp_path)
                        self.current_temp_image_path = None
                        self.consecutive_errors = 0
                        self.last_success_time = time.time()
                        self.system_failure_mode = False
                        gemini_logger.info("✅ Gemini: IMAGE IS CLEAN")
                        return "clean"
                        
                    elif result == "delete":
                        os.remove(temp_path)
                        self.current_temp_image_path = None
                        self.consecutive_errors = 0
                        self.last_success_time = time.time()
                        self.system_failure_mode = False
                        gemini_logger.info("❌ Gemini: DELETE THIS IMAGE")
                        return "delete"

                    elif result == "fallback_policy":
                        gemini_logger.warning("🚫 Gemini Policy Violation Detected - Switching to Local Fallback")
                        
                        fallback_data = None
                        if ocr_results is not None and os.path.exists(temp_path):
                             fallback_data = self.get_fallback_data(temp_path, filename, image_url, ocr_results)
                             if fallback_data:
                                 fallback_data['gemini_error'] = False
                        
                        os.remove(temp_path)
                        self.current_temp_image_path = None
                        self.consecutive_errors = 0
                        self.last_success_time = time.time()
                        
                        if fallback_data:
                            return fallback_data
                        else:
                            gemini_logger.error("❌ Could not create fallback data for policy violation")
                            return "error"
                        
                    elif result == "processed":
                        downloaded = self._download_processed_image()
                        os.remove(temp_path)
                        self.current_temp_image_path = None
                        
                        if downloaded:
                            self.consecutive_errors = 0
                            self.last_success_time = time.time()
                            self.system_failure_mode = False
                            gemini_logger.info(f"✅ Gemini processing complete: {downloaded}")
                            return downloaded
                        else:
                            gemini_logger.error("❌ Download failed")
                            
                            download_retry_wait = min(4 * self.current_image_retries, 20)
                            gemini_logger.info(f"⏳ Waiting {download_retry_wait}s before retry download...")
                            time.sleep(download_retry_wait)
                            
                            if self.current_image_retries >= self.max_image_retries:
                                gemini_logger.error(f"⚠️ {self.max_image_retries} download failures")
                                self._enter_system_failure_mode()
                            else:
                                self._handle_error(f"Download failed - Attempt {self.current_image_retries}")
                            
                            continue
                            
                    elif result == "timeout":
                        gemini_logger.warning(f"⚠️ Timeout attempt {self.current_image_retries}")
                        os.remove(temp_path)
                        self.current_temp_image_path = None
                        
                        timeout_wait = min(8 * self.current_image_retries, 35)
                        gemini_logger.info(f"⏳ Waiting {timeout_wait}s after timeout...")
                        time.sleep(timeout_wait)
                        
                        if self.current_image_retries >= self.max_image_retries:
                            gemini_logger.error(f"⚠️ {self.max_image_retries} timeouts")
                            self._enter_system_failure_mode()
                        else:
                            self._handle_error(f"Timeout - Attempt {self.current_image_retries}")
                        
                        continue
                            
                    elif result == "error":
                        gemini_logger.error(f"❌ Gemini error attempt {self.current_image_retries}")
                        os.remove(temp_path)
                        self.current_temp_image_path = None
                        
                        if ocr_results is not None:
                            gemini_logger.info("🔄 Gemini error, returning fallback data...")
                            
                            img_np = cv2.imread(temp_path) if os.path.exists(temp_path) else None
                            
                            if img_np is not None:
                                fallback_data = {
                                    'type': 'fallback_local',
                                    'ocr_results': ocr_results,
                                    'image_data': img_np,
                                    'filename': filename,
                                    'original_url': image_url,
                                    'processed_blocks': processed_blocks,
                                    'ignore_blocks': ignore_blocks,
                                    'gemini_error': True
                                }
                                os.remove(temp_path)
                                return fallback_data
                        
                        error_wait = min(6 * self.current_image_retries, 30)
                        gemini_logger.info(f"⏳ Waiting {error_wait}s after error...")
                        time.sleep(error_wait)
                        
                        if self.current_image_retries >= self.max_image_retries:
                            gemini_logger.error(f"⚠️ {self.max_image_retries} Gemini errors")
                            self._enter_system_failure_mode()
                        else:
                            self._handle_error(f"Gemini error - Attempt {self.current_image_retries}")
                        
                        continue
                            
                    else:
                        gemini_logger.error(f"❌ Unknown result: {result}")
                        os.remove(temp_path)
                        self.current_temp_image_path = None
                        
                        if self.current_image_retries >= self.max_image_retries:
                            gemini_logger.error(f"⚠️ {self.max_image_retries} unknown errors")
                            self._enter_system_failure_mode()
                        else:
                            self._handle_error(f"Unknown result - Attempt {self.current_image_retries}")
                            time.sleep(3)
                        
                        continue
                            
                except Exception as e:
                    gemini_logger.error(f"❌ Attempt {self.current_image_retries} exception: {e}")
                    try:
                        if 'temp_path' in locals() and os.path.exists(temp_path):
                            os.remove(temp_path)
                        self.current_temp_image_path = None
                    except:
                        pass
                    
                    exception_wait = min(7 * self.current_image_retries, 40)
                    gemini_logger.info(f"⏳ Waiting {exception_wait}s after exception...")
                    time.sleep(exception_wait)
                    
                    if self.current_image_retries >= self.max_image_retries:
                        gemini_logger.error(f"⚠️ {self.max_image_retries} exceptions")
                        self._enter_system_failure_mode()
                    else:
                        self._handle_error(f"Exception: {str(e)[:100]} - Attempt {self.current_image_retries}")
                    
                    continue
            
            return "error"
            
        except Exception as e:
            gemini_logger.critical(f"❌ CRITICAL ERROR: {e}")
            self._enter_system_failure_mode()
            
            gemini_logger.info("⏳ Waiting 60s after critical error...")
            time.sleep(60)
            
            gemini_logger.info("🔄 Retrying after critical error...")
            return self.process_single_image(image_data, filename, image_url, 
                                            ocr_results, processed_blocks, ignore_blocks)
    
    def close(self):
        """Đóng khi kết thúc"""
        if self.driver:
            try:
                gemini_logger.info("🔒 Saving window position...")
                
                try:
                    window_info = {
                        'width': self.driver.get_window_size()['width'],
                        'height': self.driver.get_window_size()['height'],
                        'x': self.driver.get_window_position()['x'],
                        'y': self.driver.get_window_position()['y']
                    }
                    self._save_window_state(**window_info)
                except Exception as e:
                    gemini_logger.debug(f"⚠️ Cannot save window: {e}")
                
                self.driver.quit()
                gemini_logger.info("✅ Browser closed")
            except Exception as e:
                gemini_logger.warning(f"⚠️ Close error: {e}")
            finally:
                self.driver = None
                self.is_logged_in = False
        
        self._force_kill_chrome_processes()
        self.original_width = None
        self.consecutive_errors = 0
        self.current_image_retries = 0
        self.system_failure_mode = False
        
        self.current_temp_image_path = None
        
        # Log final upload statistics
        gemini_logger.info(f"📊 FINAL UPLOAD STATISTICS: {self.upload_stats}")
        
        self.clipboard_manager.release_clipboard(self.program_id)
    
    def reset_window_position(self):
        """Reset vị trí cửa sổ"""
        try:
            if os.path.exists(self.window_state_file):
                os.remove(self.window_state_file)
                gemini_logger.info("✅ Window position file deleted")
            
            gemini_logger.info("🗑️ Window position reset")
            return True
        except Exception as e:
            gemini_logger.error(f"❌ Reset window error: {e}")
            return False
    
    def get_clipboard_status(self):
        """Lấy trạng thái clipboard"""
        return self.clipboard_manager.get_clipboard_status()
    
    def force_clear_clipboard(self):
        """Xóa clipboard"""
        return self.clipboard_manager.force_clear_clipboard(self.program_id)
    
    def reset_clipboard_state(self):
        """Reset clipboard"""
        return self.clipboard_manager.reset_clipboard_state()
    
    def get_upload_statistics(self):
        """Lấy thống kê upload methods"""
        return self.upload_stats.copy()