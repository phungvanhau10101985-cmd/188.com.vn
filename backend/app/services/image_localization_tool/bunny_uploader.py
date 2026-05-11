# bunny_uploader.py
import requests
import os
import hashlib
from urllib.parse import urlparse, unquote
from typing import List, Tuple, Dict, Optional, Any
import time
import cv2
import numpy as np
from pathlib import Path
import re
import logging
import unicodedata
import random
import uuid

from config import BUNNY_API_KEY, STORAGE_ZONE_NAME, BUNNY_STORAGE_HOSTNAME, BUNNY_CDN_PUBLIC_BASE, SIZE_PATTERN, CACHE_DIR

logger = logging.getLogger(__name__)

def slugify_vietnamese(text: str) -> str:
    """Chuyển tiếng Việt có dấu thành không dấu chuẩn SEO."""
    if not text: return "san-pham"
    text = text.replace("đ", "d").replace("Đ", "d")
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ascii', 'ignore').decode('utf-8')
    text = text.lower()
    text = re.sub(r'[^a-z0-9]', '-', text)
    text = re.sub(r'-+', '-', text).strip('-')
    return text if text else "san-pham"

class BunnyUploader:
    def __init__(self, api_key: str, storage_zone_name: str, storage_hostname: str = "storage.bunnycdn.com"):
        self.api_key = api_key
        self.storage_zone_name = storage_zone_name
        self.storage_hostname = storage_hostname
        self.base_url = f"https://{storage_hostname}/{storage_zone_name}/"
        self.cdn_base_url = f"{BUNNY_CDN_PUBLIC_BASE.rstrip('/')}/"
        
        self.session = requests.Session()
        retry_strategy = requests.adapters.Retry(
            total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = requests.adapters.HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        
        self.headers = {
            "AccessKey": api_key, 
            "Content-Type": "application/octet-stream"
        }
        
        self.cache_dir = Path(CACHE_DIR)
        os.makedirs(self.cache_dir, exist_ok=True)
        
        self.processed_urls_map = {}
    
    def is_188_domain(self, url: str) -> bool:
        if not url or not isinstance(url, str): return False
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            return '188.com.vn' in domain or '188comvn.b' in domain or domain.endswith('.188.com.vn')
        except: return False
    
    def has_size_in_filename(self, url: str) -> bool:
        if not url: return False
        filename = os.path.basename(urlparse(url).path)
        return bool(SIZE_PATTERN.search(filename))
    
    def generate_custom_filename(self, product_name: str, product_code: str, 
                               is_split_part: bool, part_index: int, total_parts: int, original_ext: str) -> str:
        """
        Tạo tên file chuẩn SEO: TenSP-MaSP-Suffix.ext
        FIX: Suffix thêm Random để đảm bảo DUY NHẤT tuyệt đối
        """
        safe_name = slugify_vietnamese(product_name)
        safe_code = slugify_vietnamese(product_code) if product_code else "no-code"
        
        # Tạo suffix duy nhất bằng timestamp + random hex
        unique_suffix = f"{int(time.time() * 1000) % 1000000}_{uuid.uuid4().hex[:4]}"
        
        if is_split_part and total_parts > 1:
            suffix = f"part{part_index+1}_of_{total_parts}_{unique_suffix}"
        else:
            suffix = f"{unique_suffix}"
            
        ext = original_ext.lower() if original_ext and original_ext.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.webp'] else '.jpg'
        
        # Ghép tên file
        final_name = f"{safe_name}-{safe_code}-{suffix}{ext}"
        
        # Giới hạn độ dài tối đa
        if len(final_name) > 120:
            trim_len = 120 - len(safe_code) - len(suffix) - 10
            if trim_len > 10:
                safe_name = safe_name[:trim_len].strip('-')
                final_name = f"{safe_name}-{safe_code}-{suffix}{ext}"
                
        return final_name

    def sanitize_filename_for_cdn(self, filename: str, is_split_part: bool = False, 
                                 part_index: int = 0, total_parts: int = 1) -> str:
        """FIX: Thêm Random vào tên file để tránh trùng lặp khi không có tên SP"""
        try:
            name, ext = os.path.splitext(filename)
            name = re.sub(r'_part\d+_of_\d+$', '', name)
            name = re.sub(r'_part\d+$', '', name)
            safe_name = re.sub(r'[^a-zA-Z0-9\-_.]', '_', name)
            
            if len(safe_name) > 80: safe_name = safe_name[:80]
            
            ext = ext.lower() if ext and ext.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.webp'] else '.jpg'
            
            # Thêm random vào timestamp
            unique_id = f"{int(time.time() % 10000)}_{random.randint(1000, 9999)}"
            
            if is_split_part and total_parts > 1:
                final_filename = f"{safe_name}_p{part_index+1}_{unique_id}{ext}"
            else:
                final_filename = f"{safe_name}_{unique_id}{ext}"
            return final_filename
        except Exception:
            return f"image_{int(time.time())}_{uuid.uuid4().hex[:6]}.jpg"
            
    def get_image_hash(self, image_data: bytes) -> str:
        return hashlib.md5(image_data).hexdigest()

    def upload_to_bunny(self, image_bytes: bytes, filename: str) -> Optional[str]:
        try:
            upload_url = f"{self.base_url}{filename}"
            response = self.session.put(upload_url, headers=self.headers, data=image_bytes, timeout=30)
            if response.status_code in (200, 201, 409):
                return f"{self.cdn_base_url}{filename}"
            return None
        except: return None
    
    def mark_image_processed_and_uploaded(self, image_hash: str, cdn_url: str):
        if cdn_url and cdn_url.startswith(self.cdn_base_url):
            with open(self.cache_dir / f"{image_hash}.cache", 'w', encoding='utf-8') as f: f.write(cdn_url)

    def upload_image(self, image_data: np.ndarray, filename: str, 
                    original_url: str, is_split_part: bool = False,
                    part_index: int = 0, total_parts: int = 1,
                    product_name: str = None, product_code: str = None) -> Dict[str, Any]:
        try:
            # Check domain 188 -> Bỏ qua upload
            if not is_split_part and self.is_188_domain(original_url):
                logger.info(f"  ⏭️ Bỏ qua upload (domain 188): {original_url[:50]}...")
                return {'success': True, 'cdn_url': original_url, 'filename': filename, 'skipped': True}
            
            # Check size pattern -> Xóa nếu là ảnh size
            if self.has_size_in_filename(original_url):
                return {'success': False, 'cdn_url': "DELETED", 'filename': filename, 'deleted': True}
            
            # Encode ảnh
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, 95]
            if filename.lower().endswith('.png'): encode_params = [cv2.IMWRITE_PNG_COMPRESSION, 3]
            
            file_ext = os.path.splitext(filename)[1] or '.jpg'
            _, encoded_img = cv2.imencode(file_ext, image_data, encode_params)
            image_bytes = encoded_img.tobytes()
            
            # TẠO TÊN FILE DUY NHẤT (QUAN TRỌNG)
            if product_name:
                safe_filename = self.generate_custom_filename(
                    product_name, product_code, is_split_part, part_index, total_parts, file_ext
                )
            else:
                safe_filename = self.sanitize_filename_for_cdn(filename, is_split_part, part_index, total_parts)
            
            # Upload
            cdn_url = self.upload_to_bunny(image_bytes, safe_filename)
            
            if not cdn_url: raise Exception("Upload failed")

            # Cache hash
            image_hash = self.get_image_hash(image_bytes)
            self.mark_image_processed_and_uploaded(image_hash, cdn_url)
            
            # Lưu map URL
            self.processed_urls_map[original_url] = cdn_url
            
            return {
                'success': True, 'cdn_url': cdn_url, 'filename': safe_filename,
                'is_split_part': is_split_part
            }
        except Exception as e:
            logger.error(f"    ❌ Lỗi upload: {e}")
            return {'success': False, 'error': str(e), 'filename': filename}