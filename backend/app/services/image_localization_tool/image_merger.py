# image_merger.py
import cv2
import numpy as np
import os
from pathlib import Path
from typing import List, Tuple, Dict, Optional, Any
import hashlib
from urllib.parse import urlparse, unquote
import requests
import time
import json
import re
import logging 
from io import BytesIO
from PIL import Image, ImageSequence

# Import từ config
from config import (
    TEMP_DIR,
    MERGE_SPACING,
    BACKGROUND_COLOR,
    SAVE_QUALITY,
    MAX_IMAGE_WIDTH,
    MIN_IMAGE_WIDTH,
    BATCH_SIZE,
    MERGE_MAX_PIXELS,
)

# Khởi tạo Logger
logger = logging.getLogger(__name__)

class ImageMerger:
    def __init__(self):
        self.session = requests.Session()
        retry_strategy = requests.adapters.Retry(
            total=3, backoff_factor=1, 
            status_forcelist=[403, 429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        adapter = requests.adapters.HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        
        self.temp_dir = Path(TEMP_DIR)
        self.max_image_width = MAX_IMAGE_WIDTH
        self.min_image_width = MIN_IMAGE_WIDTH
        self.batch_size = max(1, int(BATCH_SIZE or 10))
        self.merge_max_pixels = max(1, int(MERGE_MAX_PIXELS or 70_000_000))
        self.small_images_found = set()
        
        os.makedirs(self.temp_dir, exist_ok=True)
        logger.info(f"📁 ImageMerger initialized | Temp: {self.temp_dir}")
        
    def is_188_domain(self, url: str) -> bool:
        if not url or not isinstance(url, str): return False
        try:
            return '188.com.vn' in urlparse(url).netloc.lower() or '188comvn.b' in url
        except: return False

    def is_junk_thumbnail(self, url: str) -> bool:
        """
        Kiểm tra xem URL có phải là ảnh thumbnail rác không.
        Trả về True nếu phát hiện kích thước nhỏ (220x220, 100x100...)
        """
        if not url: return False
        
        # Regex bắt các pattern kích thước rác
        junk_patterns = [
            r'[._-]\d{2,4}x\d{2,4}[._-]',   # VD: .220x220. hoặc _50x50.
            r'[._-]\d{2,4}x\d{2,4}\.jpg$',  # VD: .220x220.jpg (cuối dòng)
            r'[._-]\d{2,4}x\d{2,4}$',       # VD: ...image.jpg_220x220
            r'\.search\.', 
            r'_sum\.jpg'
        ]
        
        for pattern in junk_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return True
        return False
    
    def fix_url(self, url: str) -> str:
        """Sửa lỗi format URL cơ bản"""
        if not url: return url
        url = unquote(url)
        
        replacements = {
            '//i98.com.vn': '//188.com.vn', '//i88.com.vn': '//188.com.vn',
            'cbw01.alicdn.com': 'cbu01.alicdn.com', 'cbue1.allcdn.com': 'cbu01.alicdn.com',
            'cbugl.alcdn.com': 'cbu01.alicdn.com'
        }
        for wrong, correct in replacements.items():
            if wrong in url: url = url.replace(wrong, correct)
            
        if url.startswith('//'): url = 'https:' + url
        elif not url.startswith(('http://', 'https://')): url = 'https://' + url
        return url
    
    def convert_gif_to_jpg(self, gif_data: bytes) -> Optional[np.ndarray]:
        """
        Chuyển đổi ảnh GIF sang JPG bằng cách lấy frame đầu tiên.
        """
        try:
            # Mở GIF bằng PIL
            gif = Image.open(BytesIO(gif_data))
            
            # Lấy frame đầu tiên
            first_frame = None
            for frame in ImageSequence.Iterator(gif):
                first_frame = frame.copy()
                break
            
            if first_frame is None:
                logger.error("      ❌ Không thể lấy frame từ GIF")
                return None
            
            # Chuyển đổi mode nếu cần
            if first_frame.mode == 'P':
                # Chuyển palette sang RGB
                if 'transparency' in first_frame.info:
                    first_frame = first_frame.convert('RGBA')
                else:
                    first_frame = first_frame.convert('RGB')
            elif first_frame.mode == 'RGBA':
                # Tạo nền trắng cho ảnh có alpha channel
                bg = Image.new('RGB', first_frame.size, (255, 255, 255))
                bg.paste(first_frame, mask=first_frame.split()[-1])
                first_frame = bg
            elif first_frame.mode not in ('RGB', 'L'):
                # Chuyển sang RGB cho các mode khác
                first_frame = first_frame.convert('RGB')
            
            # Chuyển PIL Image sang numpy array
            img_array = np.array(first_frame)
            
            # Xử lý grayscale (1 channel)
            if len(img_array.shape) == 2:
                # Grayscale -> BGR
                img_array = cv2.cvtColor(img_array, cv2.COLOR_GRAY2BGR)
            elif len(img_array.shape) == 3 and img_array.shape[2] == 3:
                # RGB -> BGR
                img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
            elif len(img_array.shape) == 3 and img_array.shape[2] == 4:
                # RGBA -> BGR (đã xử lý alpha ở trên)
                img_array = cv2.cvtColor(img_array, cv2.COLOR_RGBA2BGR)
            
            logger.info(f"      🔄 Đã chuyển GIF -> JPG ({img_array.shape[1]}x{img_array.shape[0]})")
            return img_array
            
        except Exception as e:
            logger.error(f"      ❌ Lỗi chuyển đổi GIF: {e}")
            return None
    
    def download_single_image(self, url: str) -> Optional[Tuple[np.ndarray, str, str]]:
        """
        Tải ảnh đơn lẻ với hỗ trợ GIF.
        """
        # --- CHẶN NGAY TẠI CỬA ---
        if self.is_junk_thumbnail(url):
            logger.warning(f"      🗑️ [AUTO-BLOCK] Ảnh thumbnail rác: {url[-40:]} -> BỎ QUA")
            self.small_images_found.add(url)
            return None
        # -------------------------

        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://s.1688.com/'
            }
            fixed_url = self.fix_url(url)
            
            for attempt in range(3):
                try:
                    resp = self.session.get(fixed_url, headers=headers, timeout=20)
                    if resp.status_code == 404: 
                        logger.warning(f"      ❌ Ảnh 404: {fixed_url}")
                        return None
                    resp.raise_for_status()
                    
                    # Kiểm tra content-type
                    content_type = resp.headers.get('content-type', '').lower()
                    content_bytes = resp.content
                    
                    img = None
                    
                    # Xử lý GIF - KHÔNG BỎ QUA NỮA
                    if 'gif' in content_type or url.lower().endswith('.gif'):
                        logger.info(f"      🔄 Phát hiện GIF, đang chuyển đổi: {fixed_url[-40:]}")
                        img = self.convert_gif_to_jpg(content_bytes)
                        if img is None:
                            logger.warning(f"      ⚠️ Không thể chuyển đổi GIF, thử decode bình thường: {fixed_url[-40:]}")
                            # Thử decode bình thường như ảnh thường
                            nparr = np.frombuffer(content_bytes, np.uint8)
                            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    else:
                        # Xử lý các định dạng ảnh khác
                        nparr = np.frombuffer(content_bytes, np.uint8)
                        
                        # Thử decode với các flag khác nhau
                        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        if img is None:
                            # Thử với flag bỏ qua orientation
                            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
                        if img is None:
                            # Thử với flag ANYDEPTH
                            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR | cv2.IMREAD_ANYCOLOR)
                    
                    if img is None: 
                        logger.warning(f"      ⚠️ Không thể decode ảnh: {fixed_url[-40:]}")
                        continue
                    
                    h, w = img.shape[:2]
                    
                    # Check ảnh trống
                    if w == 0 or h == 0:
                        logger.warning(f"      ⚠️ Ảnh có kích thước 0: {fixed_url[-40:]}")
                        continue
                    
                    # Check kích thước vật lý
                    if w < self.min_image_width:
                        logger.warning(f"      🗑️ Ảnh tải về quá nhỏ ({w}px) -> XÓA")
                        self.small_images_found.add(url)
                        return None 
                    
                    # Kiểm tra ảnh toàn một màu (có thể bị hỏng)
                    if img.size > 0:
                        img_std = np.std(img)
                        if img_std < 1.0:  # Ảnh gần như một màu
                            logger.warning(f"      ⚠️ Ảnh có vẻ bị hỏng (độ lệch chuẩn thấp): {fixed_url[-40:]}")
                    
                    # Tạo tên file
                    parsed = urlparse(fixed_url)
                    fname = os.path.basename(parsed.path)
                    if not fname or '.' not in fname: 
                        fname = "image.jpg"
                    else: 
                        fname = re.sub(r'[<>:"/\\|?*]', '_', fname)
                    
                    # Đổi extension .gif thành .jpg
                    if fname.lower().endswith('.gif'):
                        fname = fname[:-4] + '.jpg'
                    
                    # Kiểm tra extension
                    if not fname.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp')):
                        fname += ".jpg"
                    
                    ts = int(time.time() * 1000)
                    uhash = hashlib.md5(fixed_url.encode()).hexdigest()[:8]
                    unique_name = f"orig_{ts}_{uhash}_{fname[-30:]}" 
                    
                    # Đảm bảo có extension jpg
                    if not unique_name.lower().endswith(('.jpg', '.jpeg')):
                        unique_name += ".jpg"
                        
                    path = self.temp_dir / unique_name
                    
                    # Lưu ảnh
                    success = cv2.imwrite(str(path), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
                    if not success or not path.exists() or path.stat().st_size == 0:
                        logger.warning(f"      ⚠️ Không thể lưu ảnh: {unique_name}")
                        if path.exists():
                            try: os.remove(path)
                            except: pass
                        continue
                    
                    logger.info(f"      ✅ Đã tải: {unique_name} ({w}x{h})")
                    return img, unique_name, str(path)
                    
                except requests.exceptions.RequestException as e:
                    logger.warning(f"      ⚠️ Lỗi mạng (attempt {attempt+1}): {e}")
                    if attempt < 2: time.sleep(1)
                except Exception as e:
                    logger.warning(f"      ⚠️ Lỗi xử lý ảnh (attempt {attempt+1}): {e}")
                    if attempt < 2: time.sleep(1)
            
            logger.error(f"   ❌ Tải thất bại sau 3 lần thử: {url[:80]}...")
            return None
            
        except Exception as e:
            logger.error(f"   ❌ Lỗi không xác định khi tải {url[:80]}: {e}")
            return None
    
    def resize_if_too_wide(self, img: np.ndarray) -> Tuple[np.ndarray, float]:
        if img is None or img.size == 0:
            return img, 1.0
        h, w = img.shape[:2]
        if w <= self.max_image_width: return img, 1.0
        ratio = self.max_image_width / w
        new_w, new_h = self.max_image_width, int(h * ratio)
        if new_h < 10: return img, 1.0
        return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4), ratio

    def estimate_merged_pixel_count(self, images: List[np.ndarray]) -> int:
        """Ước lượng width×height canvas sau resize_if_too_wide (trước khi ghép dọc)."""
        valid = [img for img in images if img is not None and getattr(img, "size", 0) > 0]
        if not valid:
            return 0
        resized = [self.resize_if_too_wide(img)[0] for img in valid]
        widths = [im.shape[1] for im in resized]
        heights = [im.shape[0] for im in resized]
        max_w = max(widths) if widths else 0
        total_h = sum(heights) + max(0, len(heights) - 1) * MERGE_SPACING
        return int(max_w) * int(total_h)

    def plan_merge_batch_indices(self, images: List[np.ndarray]) -> List[List[int]]:
        """
        Chia indices ảnh thành các batch: không quá batch_size và không vượt merge_max_pixels.
        """
        if not images:
            return []
        batches: List[List[int]] = []
        current: List[int] = []
        for i, img in enumerate(images):
            if img is None or getattr(img, "size", 0) == 0:
                continue
            if not current:
                current = [i]
                solo_px = self.estimate_merged_pixel_count([img])
                if solo_px > self.merge_max_pixels:
                    logger.warning(
                        "   ⚠️ Ảnh đơn lẻ ~%.1f MP vượt MERGE_MAX_PIXELS=%.1f MP — vẫn OCR riêng (có thể lỗi Vision).",
                        solo_px / 1e6,
                        self.merge_max_pixels / 1e6,
                    )
                continue
            trial = current + [i]
            trial_px = self.estimate_merged_pixel_count([images[j] for j in trial])
            if len(trial) > self.batch_size or trial_px > self.merge_max_pixels:
                batches.append(current)
                current = [i]
            else:
                current = trial
        if current:
            batches.append(current)
        return batches

    def merge_batch_of_images(self, images: List[np.ndarray], filenames: List[str],
                             original_urls: List[str], original_paths: List[str],
                             batch_index: int) -> Tuple[np.ndarray, Dict[str, dict]]:
        if not images: raise ValueError("Empty images list")
        
        # Lọc bỏ ảnh None
        valid_data = []
        for img, fname, url, path in zip(images, filenames, original_urls, original_paths):
            if img is not None and img.size > 0:
                valid_data.append((img, fname, url, path))
        
        if not valid_data:
            raise ValueError("No valid images to merge")
        
        resized_images = []
        scales = []
        valid_filenames = []
        valid_urls = []
        valid_paths = []
        
        for img, fname, url, path in valid_data:
            r_img, s = self.resize_if_too_wide(img)
            resized_images.append(r_img)
            scales.append(s)
            valid_filenames.append(fname)
            valid_urls.append(url)
            valid_paths.append(path)
        
        widths = [i.shape[1] for i in resized_images]
        heights = [i.shape[0] for i in resized_images]
        max_w = max(widths) if widths else 0
        total_h = sum(heights) + (len(heights) - 1) * MERGE_SPACING
        
        merged = np.full((total_h, max_w, 3), BACKGROUND_COLOR, dtype=np.uint8)
        pos_dict = {}
        curr_y = 0
        
        for idx, (img, fname, url, path, scale) in enumerate(zip(resized_images, valid_filenames, valid_urls, valid_paths, scales)):
            h, w = img.shape[:2]
            off_x = (max_w - w) // 2
            merged[curr_y:curr_y+h, off_x:off_x+w] = img
            pos_dict[fname] = {
                'x': off_x, 'y': curr_y, 'width': w, 'height': h,
                'index': idx, 'batch_index': batch_index,
                'original_url': url, 'original_path': path, 'scale_factor': scale
            }
            curr_y += h + MERGE_SPACING
            
        logger.info(f"   ✅ [MERGE] Đã ghép BATCH {batch_index + 1} ({len(resized_images)} ảnh hợp lệ)")
        return merged, pos_dict
    
    def save_merged_batch(self, merged_image: np.ndarray, urls: List[str], batch_index: int) -> Tuple[str, str]:
        """Lưu batch đã merge và trả về đường dẫn thực tế"""
        if merged_image is None or merged_image.size == 0:
            raise ValueError("Merged image is empty")
            
        urls_str = ''.join(sorted(urls)) + str(batch_index)
        ihash = hashlib.md5(urls_str.encode()).hexdigest()[:12]
        ts = int(time.time() % 1000000)
        fname = f"merged_batch{batch_index + 1}_{ts}_{ihash}.jpg"
        path = self.temp_dir / fname
        
        try:
            success = cv2.imwrite(str(path), merged_image, [cv2.IMWRITE_JPEG_QUALITY, 95])
            if not success or not path.exists() or path.stat().st_size == 0:
                raise IOError(f"Failed to save merged image: {path}")
            logger.info(f"   💾 Đã lưu batch: {fname} ({merged_image.shape[1]}x{merged_image.shape[0]})")
            return str(path), ihash
        except Exception as e:
            logger.error(f"❌ Lỗi lưu batch {batch_index}: {e}")
            raise
    
    def save_batch_positions_info(self, image_hash: str, positions_dict: Dict, original_urls: List[str], batch_index: int) -> str:
        ts = int(time.time() % 1000000)
        fname = f"positions_batch{batch_index + 1}_{ts}_{image_hash}.json"
        path = self.temp_dir / fname
        info = {'hash': image_hash, 'batch_index': batch_index, 'positions': positions_dict, 'max_images_per_batch': self.batch_size}
        with open(path, 'w', encoding='utf-8') as f: json.dump(info, f, ensure_ascii=False, indent=2)
        return str(path)
    
    def merge_all_images_in_batches(self, col_b_data, col_c_data, col_d_data, row_index, sheets_handler) -> Dict:
        self.small_images_found = set()
        
        raw_urls = []
        raw_urls.extend(sheets_handler.extract_urls_from_data(col_b_data))
        raw_urls.extend(sheets_handler.extract_urls_from_data(col_c_data))
        raw_urls.extend(sheets_handler.extract_urls_from_data(col_d_data))
        
        all_urls = []
        seen = set()
        for u in raw_urls:
            if u and isinstance(u, str) and u.strip():  # Chỉ lấy URL không rỗng
                if u not in seen: 
                    seen.add(u); all_urls.append(u)
        
        logger.info(f"📋 Tổng số URL: {len(all_urls)}")
        
        if not all_urls: 
            return {'success': False, 'message': 'No images', 'batches': [], 'column_mapping': {}}
            
        url_to_columns = {}
        b_urls = set(sheets_handler.extract_urls_from_data(col_b_data))
        c_urls = set(sheets_handler.extract_urls_from_data(col_c_data))
        d_urls = set(sheets_handler.extract_urls_from_data(col_d_data))
        
        for url in all_urls:
            cols = []
            if url in b_urls: cols.append('B')
            if url in c_urls: cols.append('C')
            if url in d_urls: cols.append('D')
            url_to_columns[url] = cols

        batches_result = {
            'batches': [], 
            'column_mapping': {}, 
            'total_images': 0, 
            'small_images_urls': [], 
            'success': True, 
            'batch_size': self.batch_size,
            'error': None
        }
        urls_to_download = []
        skipped_188_urls = []
        
        for url in all_urls:
            if self.is_188_domain(url):
                skipped_188_urls.append(url)
                logger.info(f"   ⏭️ Skip 188 domain: {url[:60]}...")
            else:
                urls_to_download.append(url)
        
        for url in skipped_188_urls:
            if url in url_to_columns:
                batches_result['column_mapping'][url] = {'source_columns': url_to_columns[url], 'status': 'SKIPPED_188'}

        if not urls_to_download and not self.small_images_found and not skipped_188_urls:
            logger.warning("⚠️ Không có ảnh nào để xử lý")
            return {'success': False, 'message': 'No processable images', 'batches': [], 'column_mapping': {}}
             
        all_images = []
        all_filenames = []
        all_original_paths = []
        loaded_urls = []
        failed_urls = []
        
        if urls_to_download:
            logger.info(f"📥 Đang tải {len(urls_to_download)} ảnh về máy...")
            
            for i, url in enumerate(urls_to_download):
                # LỚP BẢO VỆ 1: Kiểm tra ở vòng lặp
                if self.is_junk_thumbnail(url):
                    logger.warning(f"   🗑️ [LOOP SKIP] Link ảnh rác: {url[-40:]} -> XÓA")
                    self.small_images_found.add(url)
                    continue 

                logger.info(f"   ⬇️ [{i+1}/{len(urls_to_download)}] Tải: {url[:80]}...")
                res = self.download_single_image(url)
                if res:
                    img, fname, orig_path = res
                    all_images.append(img)
                    all_filenames.append(fname)
                    all_original_paths.append(orig_path)
                    loaded_urls.append(url)
                    logger.info(f"   ✅ Thành công: {fname}")
                else:
                    logger.warning(f"   ❌ Thất bại: {url[-50:]}")
                    failed_urls.append(url)
        
        logger.info(f"📊 Kết quả tải: {len(loaded_urls)} thành công, {len(failed_urls)} thất bại")
        
        batches_result['total_images'] = len(all_images) + len(self.small_images_found) + len(skipped_188_urls)
        batches_result['small_images_urls'] = list(self.small_images_found)
        
        if all_images:
            num_images = len(all_images)
            batch_plans = self.plan_merge_batch_indices(all_images)
            total_batches = len(batch_plans)
            logger.info(
                "📊 Đã tải thành công %s ảnh -> Chia %s batch(es) "
                "(tối đa %s ảnh/batch, ≤%.1f MP/batch).",
                num_images,
                total_batches,
                self.batch_size,
                self.merge_max_pixels / 1e6,
            )

            for batch_idx, indices in enumerate(batch_plans):
                b_imgs = [all_images[i] for i in indices]
                b_fnames = [all_filenames[i] for i in indices]
                b_urls = [loaded_urls[i] for i in indices]
                b_paths = [all_original_paths[i] for i in indices]
                est_mp = self.estimate_merged_pixel_count(b_imgs) / 1e6

                try:
                    merged_img, pos_dict = self.merge_batch_of_images(b_imgs, b_fnames, b_urls, b_paths, batch_idx)
                    merged_path, img_hash = self.save_merged_batch(merged_img, b_urls, batch_idx)
                    pos_file = self.save_batch_positions_info(img_hash, pos_dict, b_urls, batch_idx)
                    logger.info(
                        "   📦 Batch %s: %s ảnh, ~%.1f MP (giới hạn %.1f MP)",
                        batch_idx + 1,
                        len(b_imgs),
                        est_mp,
                        self.merge_max_pixels / 1e6,
                    )

                    for i, url in enumerate(b_urls):
                        if url in url_to_columns:
                            batches_result['column_mapping'][url] = {
                                'batch_index': batch_idx, 'source_columns': url_to_columns[url],
                                'original_path': b_paths[i], 'status': 'PROCESSED'
                            }
                    
                    batches_result['batches'].append({
                        'batch_index': batch_idx, 'merged_path': merged_path,
                        'positions_file': pos_file, 'image_count': len(b_imgs),
                        'batch_size': self.batch_size,
                        'estimated_megapixels': round(est_mp, 2),
                    })
                except Exception as e:
                    logger.error(f"❌ Lỗi xử lý batch {batch_idx}: {e}")
                    batches_result['success'] = False
                    batches_result['error'] = str(e)
                    # Vẫn tiếp tục với các batch khác
                    continue
            
        for url in self.small_images_found:
             if url in url_to_columns:
                batches_result['column_mapping'][url] = {'source_columns': url_to_columns[url], 'status': 'TOO_SMALL'}
        
        for url in failed_urls:
            if url in url_to_columns:
                batches_result['column_mapping'][url] = {'source_columns': url_to_columns[url], 'status': 'DOWNLOAD_FAILED'}
        
        logger.info(f"✅ Hoàn thành merge với {len(batches_result.get('batches', []))} batch")
        return batches_result