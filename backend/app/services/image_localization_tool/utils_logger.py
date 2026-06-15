# utils_logger.py
import logging
import os
import sys
import time
import functools  # Cần thiết cho decorator
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# Thử import LOGS_DIR từ config, nếu không có thì dùng mặc định
try:
    from config import LOGS_DIR
except ImportError:
    LOGS_DIR = "logs"

os.makedirs(LOGS_DIR, exist_ok=True)

class ColorFormatter(logging.Formatter):
    """Formatter với màu sắc cho console output"""
    
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
        'RESET': '\033[0m'        # Reset
    }
    
    def format(self, record):
        # Tạo bản sao để không ảnh hưởng đến các handler khác (file handler)
        record_copy = logging.makeLogRecord(record.__dict__)
        log_color = self.COLORS.get(record_copy.levelname, self.COLORS['RESET'])
        record_copy.levelname = f"{log_color}{record_copy.levelname}{self.COLORS['RESET']}"
        return super().format(record_copy)

def setup_logger(name: str, log_level: int = logging.INFO, log_to_file: bool = True, specific_filename: Optional[str] = None) -> logging.Logger:
    """
    Thiết lập logger với format đẹp
    
    Args:
        name: Tên logger
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_to_file: Ghi log ra file không
        specific_filename: Tên file log cụ thể (nếu None sẽ dùng ngày hiện tại)
    
    Returns:
        Logger object
    """
    # Tạo logger
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    
    # Clear existing handlers để tránh duplicate khi reload module
    if logger.hasHandlers():
        logger.handlers.clear()
    
    # Tạo formatters
    # File log cần chi tiết thời gian và module
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console log gọn gàng hơn
    console_formatter = ColorFormatter(
        '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # Console handler (luôn có)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler (nếu cần)
    if log_to_file:
        if specific_filename:
            # Nếu chỉ định tên file cụ thể (ví dụ cho Gemini)
            log_filename = specific_filename
        else:
            # Mặc định theo ngày
            log_filename = f"{datetime.now().strftime('%Y-%m-%d')}.log"
            
        log_filepath = os.path.join(LOGS_DIR, log_filename)
        
        file_handler = logging.FileHandler(log_filepath, encoding='utf-8')
        file_handler.setLevel(log_level)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    return logger

def get_module_logger(module_name: str) -> logging.Logger:
    """
    Lấy logger cho module cụ thể
    """
    return setup_logger(module_name)

# --- CẤU HÌNH CÁC LOGGER ---

# Logger chính
main_logger = setup_logger("MAIN")

bunny_logger = setup_logger("BUNNY")
sheets_logger = setup_logger("SHEETS")
download_logger = setup_logger("DOWNLOAD")
classifier_logger = setup_logger("CLASSIFIER")

# Utility functions
def log_section(title: str, width: int = 60):
    """Log một section với border"""
    border = "=" * width
    main_logger.info(border)
    main_logger.info(f" {title.center(width-2)} ")
    main_logger.info(border)

def log_stats(stats_dict: Dict[str, Any], title: str = "STATISTICS"):
    """Log thống kê dạng table"""
    log_section(title)
    for key, value in stats_dict.items():
        if isinstance(value, (int, float)):
            if isinstance(value, float):
                main_logger.info(f"  • {key.replace('_', ' ').title()}: {value:.2f}")
            else:
                main_logger.info(f"  • {key.replace('_', ' ').title()}: {value:,}")
        else:
            main_logger.info(f"  • {key.replace('_', ' ').title()}: {value}")

def log_error_with_trace(logger: logging.Logger, error: Exception, context: str = ""):
    """Log error với traceback"""
    import traceback
    if context:
        logger.error(f"{context}: {error}")
    else:
        logger.error(f"Error: {error}")
    
    # Log traceback ở level DEBUG
    logger.debug("Traceback:\n" + traceback.format_exc())

def log_image_process(url: str, status: str, details: str = ""):
    """Log quá trình xử lý ảnh"""
    status_icons = {
        "success": "✅",
        "error": "❌",
        "cached": "⏭️",
        "skipped": "⏸️",
        "uploaded": "☁️",
        "downloaded": "⬇️",
        "processing": "🔄",
        "fallback": "🔄"  # Icon cho fallback
    }
    
    icon = status_icons.get(status, "ℹ️")
    
    # Rút gọn URL nếu quá dài
    display_url = url
    if len(url) > 80:
        display_url = url[:60] + "..." + url[-15:]
    
    main_logger.info(f"{icon} {status.upper():<12} {display_url}")
    if details:
        main_logger.info(f"   ↳ {details}")

# Decorator cho logging
def log_function_call(logger: logging.Logger):
    """Decorator để log function call"""
    def decorator(func):
        @functools.wraps(func)  # QUAN TRỌNG: Giữ nguyên metadata của hàm gốc
        def wrapper(*args, **kwargs):
            logger.debug(f"CALLING: {func.__name__}")
            try:
                result = func(*args, **kwargs)
                logger.debug(f"SUCCESS: {func.__name__} completed")
                return result
            except Exception as e:
                logger.error(f"FAILED: {func.__name__} - {e}")
                raise
        return wrapper
    return decorator

def log_execution_time(logger: logging.Logger):
    """Decorator để log thời gian thực thi"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            logger.debug(f"START: {func.__name__}")
            
            result = func(*args, **kwargs)
            
            end_time = time.time()
            elapsed = end_time - start_time
            logger.debug(f"END: {func.__name__} - Time: {elapsed:.2f}s")
            
            return result
        return wrapper
    return decorator

# Cấu hình logging mặc định cho các thư viện bên ngoài (để tránh nhiễu)
def configure_root_logger():
    """Cấu hình root logger"""
    root_logger = logging.getLogger()
    # Chỉ hiện warning trở lên cho các thư viện như urllib3, playwright
    root_logger.setLevel(logging.WARNING)
    
    # Handler cho warnings
    warning_handler = logging.StreamHandler(sys.stderr)
    warning_handler.setLevel(logging.WARNING)
    warning_formatter = logging.Formatter('%(levelname)s: %(message)s')
    warning_handler.setFormatter(warning_formatter)
    
    # Tránh add nhiều lần
    if not root_logger.handlers:
        root_logger.addHandler(warning_handler)

    # Tắt log nhiễu của Selenium và UrlLib3
    logging.getLogger("playwright").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

# Khởi tạo khi import
configure_root_logger()