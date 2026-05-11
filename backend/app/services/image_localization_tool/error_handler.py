# error_handler.py
import time
import requests
from typing import Callable, Any, Tuple
from datetime import datetime, timedelta
from config import *

class ErrorHandler:
    """
    Quản lý lỗi với chiến thuật KIÊN TRÌ TUYỆT ĐỐI (Infinite Retry):
    - Nếu lỗi mạng/server: Thử lại mãi mãi (3 phút/lần) cho đến khi thành công.
    - Nếu lỗi Fatal (Key/Tiền): Dừng chương trình.
    """
    
    def __init__(self):
        # Danh sách các lỗi bắt buộc phải dừng chương trình ngay
        self.fatal_errors = {
            'insufficient_balance': ['insufficient', 'balance', 'payment required', '402'],
            'invalid_api_key': ['invalid api key', 'unauthorized', '401', 'authentication failed'],
            'account_suspended': ['suspended', 'terminated', 'disabled'],
            'quota_exceeded': ['quota exceeded', 'rate limit exceeded'] # Google Vision hết quota
        }
        self.error_stats = {}
    
    def is_fatal_error(self, error_msg: str) -> Tuple[bool, str]:
        """Kiểm tra xem lỗi có thuộc nhóm không thể cứu vãn không"""
        error_lower = error_msg.lower()
        for error_type, keywords in self.fatal_errors.items():
            if any(keyword in error_lower for keyword in keywords):
                return True, error_type
        return False, ""
    
    def smart_retry(self, func: Callable, *args, max_immediate_retries: int = 3, 
                   long_wait_minutes: int = 3, **kwargs) -> Any:
        """
        Thực hiện retry VÔ TẬN:
        1. Chạy hàm `func`.
        2. Nếu lỗi Fatal -> Raise Exception (Dừng tool).
        3. Nếu lỗi thường -> Retry ngay 3 lần (5s/lần).
        4. Nếu vẫn lỗi -> Chờ 3 phút -> Quay lại bước 1.
        """
        immediate_retry_count = 0
        
        while True:
            try:
                return func(*args, **kwargs)
                
            except Exception as e:
                error_msg = str(e)
                
                # 1. Kiểm tra Fatal Error
                is_fatal, error_type = self.is_fatal_error(error_msg)
                if is_fatal:
                    print(f"\n❌ LỖI FATAL ({error_type}): {error_msg}")
                    print("🚫 Chương trình buộc phải DỪNG LẠI.")
                    raise e
                
                # 2. Logic Retry
                if immediate_retry_count < max_immediate_retries:
                    # Retry nhanh
                    immediate_retry_count += 1
                    print(f"  ⚠️ Lỗi tạm thời: {error_msg}")
                    print(f"  🔄 Thử lại ngay ({immediate_retry_count}/{max_immediate_retries}) sau 5s...")
                    time.sleep(5)
                else:
                    # Retry chậm (Chế độ kiên trì)
                    print(f"  ⚠️ Vẫn lỗi sau {max_immediate_retries} lần thử nhanh: {error_msg}")
                    print(f"  ⏳ ĐANG CHỜ {long_wait_minutes} PHÚT để mạng/server hồi phục...")
                    print(f"  (Hệ thống sẽ thử lại MÃI MÃI cho đến khi thành công, không bỏ qua ảnh này)")
                    
                    time.sleep(long_wait_minutes * 60)
                    
                    # Reset lại bộ đếm để bắt đầu chu kỳ thử mới
                    immediate_retry_count = 0
                    print("  🔄 Hết thời gian chờ, đang thử lại kết nối...")
    
    def log_error(self, service: str, error_type: str):
        if service not in self.error_stats:
            self.error_stats[service] = {}
        if error_type not in self.error_stats[service]:
            self.error_stats[service][error_type] = 0
        self.error_stats[service][error_type] += 1
    
    def get_stats(self):
        return self.error_stats