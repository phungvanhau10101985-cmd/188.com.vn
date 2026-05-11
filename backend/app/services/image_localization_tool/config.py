# config.py - SỬA LỖI IMPORT CV2 - THÊM CẤU HÌNH CHIA ẢNH DÀI VÀ TỪ KHÓA XÓA NĂM SẢN XUẤT
import os
import sys
import re
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, Any, List, Tuple

# Load environment variables from backend/.env when available. Secrets must stay
# outside this package; service code injects runtime overrides before use.
load_dotenv()

# ==================== PATH CONFIGURATION ====================
BASE_DIR = Path(__file__).parent.absolute()

# Đường dẫn chính
LOGO_PATH = str(BASE_DIR / "logo188.png")
FONT_PATH = str(BASE_DIR / "arial.ttf") if (BASE_DIR / "arial.ttf").exists() else "arial.ttf"
GCP_KEY_FILE = os.getenv("IMAGE_LOCALIZATION_GCP_KEY_FILE", os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")).strip()

# Thư mục làm việc
_DEFAULT_RUNTIME_DIR = BASE_DIR.parent.parent.parent / "runtime" / "image_localization"
_RUNTIME_DIR = Path(os.getenv("IMAGE_LOCALIZATION_RUNTIME_DIR", str(_DEFAULT_RUNTIME_DIR))).resolve()
TEMP_DIR = str(_RUNTIME_DIR / "temp_images")
TEMP_IMAGES_DIR = str(_RUNTIME_DIR / "temp_images")
DOWNLOADS_DIR = str(_RUNTIME_DIR / "downloads")
LOGS_DIR = str(_RUNTIME_DIR / "logs")
CACHE_DIR = str(_RUNTIME_DIR / "processed_images_cache")
CHROME_PROFILE_PATH = os.getenv("IMAGE_LOCALIZATION_CHROME_PROFILE_PATH", str(_RUNTIME_DIR / "chrome-profile")).strip()

# ==================== BATCH PROCESSING CONFIG ====================
BATCH_SIZE = 10  # Số lượng ảnh mỗi batch

# ==================== API KEYS & SERVICES ====================
BUNNY_API_KEY = os.getenv("BUNNY_STORAGE_ACCESS_KEY", os.getenv("BUNNY_API_KEY", "")).strip()
STORAGE_ZONE_NAME = os.getenv("BUNNY_STORAGE_ZONE_NAME", os.getenv("STORAGE_ZONE_NAME", "")).strip()
BUNNY_STORAGE_HOSTNAME = os.getenv("BUNNY_STORAGE_HOSTNAME", "storage.bunnycdn.com")
BUNNY_CDN_PUBLIC_BASE = os.getenv("BUNNY_CDN_PUBLIC_BASE", "https://188comvn.b-cdn.net").strip().rstrip("/")

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_URL = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions").strip()

# ==================== GEMINI CONFIGURATION ====================
GEMINI_URL = "https://gemini.google.com/app"

# PROMPT MỚI: Đã thêm xử lý từ khóa giặt tẩy
GEMINI_PROMPT = """ROLE: E-commerce Image Localization Agent

Please use Nano Banana to translate the images I send into 100% Vietnamese. The images are high quality, with large, easily readable text on mobile phones, professional product photography, studio lighting, ultra-sharp detail, and 4K resolution. All product details are preserved; any vandalism or alteration of original product details is strictly prohibited.

MAIN OBJECTIVE: Translate ALL Chinese text to Vietnamese and remove ALL Chinese text from the image, including proper names, into natural Vietnamese. Carefully analyze the image, find all Chinese text, translate it into Vietnamese, and remove all Chinese text from the image; analyze it very carefully. Strictly preserve the original text color. Translate all the Chinese text in this image into Vietnamese, including detailed descriptions, and preserve the original formatting. Convert Chinese weight units to the international weight unit kg.
Pay special attention to translating and completely removing small footnotes, measurement instructions, and formulas located beside or below tables. Do not overlook any Chinese characters, even the smallest ones. If the image violates the policy, return the text 'Policy violation'.

TASK: Process the attached image and execute the following translation logic:

ACTION: Generate a new image with the following edits:

1. **TRANSLATE:** Convert ABSOLUTELY ALL Chinese characters and Chinese text found anywhere on the image into Vietnamese. There are NO exceptions; every piece of Chinese text must be translated to Vietnamese 100%.

2. **REMOVE:** Erase all Website URLs/Domains (e.g., .com, .cn, www, .vn, .net, .org) and inpaint the background seamlessly.

3. **UNIT CONVERSION:** If Chinese weight units are found within the text, convert them during translation:
   - 1斤 -> 0.5kg
   - 1两 -> 50g

4. **PRESERVE STRUCTURE:** Maintain the original layout, fonts, text positioning, and formatting as closely as possible.

5. **QUALITY CONTROL:**
   - STRICTLY maintain the original image resolution and dimensions
   - DO NOT resize, crop, or alter the aspect ratio
   - Preserve original image quality - high resolution, sharp details
   - Keep all product details and specifications intact
   - Only translate text, do not alter product images

6. **COMPOSITION LABEL DISCLAIMER:** If and ONLY IF the image is identified as a **material composition label** (listing ingredients, fabric percentages, material content, etc.), you MUST add the following specific Vietnamese text clearly on the image (e.g., at the bottom or in an empty space):
   - **"Thông tin được dịch sát nghĩa từ nhãn gốc. Mác áo thực tế là tiếng Trung."**

IMPORTANT NOTES:
- This image has ALREADY been pre-filtered and approved for translation
- NO need to check for price information, contact details, or other blocking content
- NO need to analyze if the image contains Chinese text - it does
- NO need to check if the image is "clean" - it's ready for processing
- Your ONLY task is to translate all Chinese text to Vietnamese

TRANSLATION GUIDELINES:
- Product names: Translate meaningfully, not literally
- Technical specifications: Keep accuracy, use Vietnamese technical terms
- Color names: Use common Vietnamese color terms
- Size charts: Translate completely, maintain table structure
- Measurements: Convert Chinese units to metric where applicable
- Marketing text: Make it sound natural in Vietnamese

FINAL OUTPUT: Return ONLY the PROCESSED IMAGE FILE (Do not describe it, do not add text, just show the translated image)."""

HEADLESS = False
GEMINI_PROCESS_TIMEOUT = 300

# ==================== GEMINI POST-CHECK CONFIG ====================
GEMINI_POST_CHECK_ENABLED = True  # Bật kiểm tra ảnh sau Gemini
GEMINI_BATCH_CHECK_SIZE = 10  # Số ảnh mỗi batch kiểm tra
GEMINI_ERROR_THRESHOLD = 0.3  # Ngưỡng cảnh báo lỗi (30%)
GEMINI_CHECK_TIMEOUT = 30  # Timeout kiểm tra (giây)
GEMINI_MAX_WORKERS = 3  # Số worker threads cho xử lý song song

# ==================== IMAGE PROCESSING CONFIG ====================
MAX_IMAGE_SIZE = (2000, 2000)
MIN_IMAGE_SIZE = 500
MIN_IMAGE_WIDTH = 500
MAX_IMAGE_WIDTH = 5000
MERGE_SPACING = 10
BACKGROUND_COLOR = (255, 255, 255)
SAVE_QUALITY = 100

# Font configuration (SỬA: Không dùng cv2 ở đây, sẽ set trong code xử lý)
FONT_SCALE_FACTOR = 0.035  # Factor for calculating font scale
MIN_FONT_SCALE = 0.3
MAX_FONT_SCALE = 2.0
TEXT_PADDING = 2  # Padding around text when redrawing
BACKGROUND_EXPAND = 5  # Expand area for background color sampling

# ==================== IMAGE SPLITTING CONFIG (MỚI) ====================
# Cấu hình chia ảnh dài thành nhiều phần
IMAGE_SPLITTING_ENABLED = True  # Bật tính năng chia ảnh dài
MAX_IMAGE_HEIGHT = 1100  # Chiều cao tối đa trước khi chia (pixels)
MIN_IMAGE_HEIGHT = 700  # Chiều cao tối thiểu mỗi phần sau khi chia (pixels)
SPLIT_SAFE_MARGIN = 25  # Khoảng cách an toàn từ text khi chia (pixels)
SPLIT_MIN_GAP_SIZE = 50  # Khoảng trống tối thiểu giữa text để chia (pixels)
SPLIT_MIN_PART_HEIGHT = 800  # Chiều cao tối thiểu mỗi phần sau khi chia (pixels)

# Quyết định chia 2 hay 3 phần
SPLIT_3_PARTS_THRESHOLD = 2400  # Nếu ảnh > 1500px, xem xét chia 3 phần
SPLIT_MIN_BLOCKS_FOR_3 = 4  # Cần ít nhất 4 text blocks để chia 3 phần an toàn
# --- THÊM DÒNG NÀY ---
SPLIT_MIN_CHINESE_BLOCKS = 5  # Chỉ chia nếu đếm được ít nhất 5 khối chữ Hán
# ---------------------

# ==================== TỪ KHÓA HƯỚNG DẪN GIẶT TẨY ====================
LAUNDRY_CARE_KEYWORDS = [
    # Tiếng Trung - Từ khóa chính
    '洗涤', '清洗', '保养', '护理', '清洁',
    '水洗', '干洗', '手洗', '机洗',
    '水温', '温度', '冷水', '温水', '热水',
    '晾干', '风干', '阴干', '烘干',
    '熨烫', '烫斗', '低温烫', '中温烫',
    '漂白', '不可漂白',
    '拧干', '不可拧干',
    '分开洗涤', '单独洗涤',
    '洗水唛', '洗涤标识', '洗标',
    '衣物护理', '面料保养', '清洗保养',
    '洗涤说明', '洗涤方式', '洗涤建议', '洗涤小贴士',
    
    # Tiếng Anh
    'WASHING', 'CARE', 'MAINTENANCE', 'CLEANING',
    'WASH', 'DRY', 'IRON', 'BLEACH',
    'HAND WASH', 'MACHINE WASH', 'DRY CLEAN',
    'COLD WATER', 'WARM WATER', 'HOT WATER',
    'AIR DRY', 'LINE DRY', 'TUMBLE DRY',
    'DO NOT BLEACH', 'DO NOT IRON', 'DO NOT DRY CLEAN',
    'SEPARATE WASH', 'GENTLE CYCLE', 'DELICATE CYCLE',
    'CARE LABEL', 'WASHING LABEL', 'INSTRUCTION',
    
    # Loại vải cụ thể
    '棉质', 'COTTON',
    '聚酯纤维', 'POLYESTER',
    '皮衣', 'FURCLOTHING',
    '羊毛', 'WOOL', 'WOOLEN',
    '牛仔裤', 'JEANS',
    '太空棉', 'SPACE COTTON',
    '羽绒服', 'DOWN JACKET',
    '锦纶', 'NYLON',
    '丝绸', 'SILK',
    '麻质', 'LINEN',
    '氨纶', 'SPANDEX',
    '莱卡', 'LYCRA',
    
    # Biểu tượng giặt
    '符号', '图标', '标识',
    '可机洗', '不可机洗',
    '可干洗', '不可干洗',
    '可漂白', '不可漂白',
    '可拧干', '不可拧干',
    '可烘干', '不可烘干',
    '可熨烫', '不可熨烫',
    '低温熨烫', '中温熨烫', '高温熨烫',
    '平铺晾干', '悬挂晾干',
    
    # Nhiệt độ
    '30℃', '40℃', '50℃', '60℃',
    '30°C', '40°C', '50°C', '60°C',
    '低温', '中温', '高温',
]

# ==================== IMAGE CLASSIFICATION ====================
IMAGE_CLASSIFICATION = {
    'MAX_SIMPLE_TEXT_BLOCKS': 3,
    'OVERLAP_THRESHOLD': 0.05,
    'COMPLEX_KEYWORDS': [
        '规格', '参数', '尺寸表', '型号', '技术参数',
        'table', 'chart', 'diagram', 'specification',
        # Thêm từ khóa giặt tẩy vào phức tạp để gửi Gemini
        '洗涤说明', '洗涤方式', '洗涤标识', '洗水唛',
        '衣物护理', '面料保养', 'WASHING INSTRUCTION'
    ],
    'SIZE_TABLE_KEYWORDS': [
        '尺寸', '尺码', '大小', '规格', 'size',
        '身长', '胸围', '腰围', '臀围', '肩宽',
        '衣长', '袖长', '裤长', '裙长', '围度',
        '厘米', 'cm', '毫米', 'mm', '英寸', 'inch',
        '长', '宽', '高', '厚', '直径', '半径'
    ],
    'PRODUCT_INFO_KEYWORDS': [
        # Thông tin sản phẩm chung
        '产品', '商品', '物品', '货品', 'product',
        '型号', '款号', '货号', 'model', 'type',
        '品牌', '牌子', '商标', 'brand',
        '材质', '材料', '面料', '原料', 'material',
        '颜色', '色彩', '色号', 'colour', 'color',
        '重量', '质量', 'weight',
        
        # Thông số kỹ thuật
        '规格', '参数', 'technical', 'specification',
        '功能', '性能', 'feature', 'function',
        '用途', '使用', 'purpose', 'use',
        '产地', '生产地', 'made in', 'origin',
        '保质期', '有效期', 'expiry', 'shelf life',
        
        # Phụ kiện & thành phần
        '配件', '附件', 'accessory',
        '成分', '组成', 'composition',
        '含量', '成分含量', 'content',
        
        # Đơn vị & giá trị
        '元', '￥', '¥', 'RMB', 'USD', '$',
        '克', 'g', '千克', 'kg', '公斤',
        '升', 'L', '毫升', 'ml',
        '件', '个', '套', '盒', '包'
    ],
    # TỪ KHÓA HƯỚNG DẪN GIẶT TẨY - GỬI CHO GEMINI XỬ LÝ
    'LAUNDRY_CARE_KEYWORDS': LAUNDRY_CARE_KEYWORDS,
    
    # Từ khóa giặt tẩy chỉ xóa khi kết hợp với thông tin bán hàng
    'CONDITIONAL_DELETE_KEYWORDS': {
        'LAUNDRY_CARE_WITH_SALES': [
            ('洗涤说明', '价格'), ('洗涤方式', '批发'), ('洗水唛', '微信'),
            ('洗涤保养', '电话'), ('护理说明', '公司'), ('洗涤建议', '代理'),
            ('洗涤小贴士', '代发'), ('洗涤标识', '货源'), ('洗水唛', '现货'),
            ('洗涤说明', '优惠'), ('护理说明', '购买')
        ],
        'LAUNDRY_CARE_KEYWORDS': [
            '洗涤说明', '洗涤方式', '洗涤建议', '洗涤小贴士',
            '洗涤标识', '洗水唛', '洗涤保养', '护理说明'
        ],
        'SALES_KEYWORDS': [
            '价格', '批发', '微信', '电话', '公司', '代理',
            '代发', '货源', '现货', '优惠', '购买', '点击进入', '立即购买'
        ]
    },
    
    # TỪ KHÓA XÓA MỚI - ƯU TIÊN CAO NHẤT
    # 4 CHỮ QUAN TRỌNG + SỐ NĂM ĐƠN LẺ: XÓA NGAY CẢ KHI XUẤT HIỆN ĐƠN LẺ
    'URGENT_DELETE_KEYWORDS': [
        # === 4 CHỮ QUAN TRỌNG - XÓA NGAY KHI CÓ 1 CHỮ ===
        '荐',      # Ký hiệu đề xuất - RẤT NGUY HIỂM
        '退',      # Hoàn tiền/trả hàng - RẤT NGUY HIỂM  
        '价',      # Giá cả - RẤT NGUY HIỂM
        '换',      # Đổi trả - RẤT NGUY HIỂM
        
        # === CÁC CHỮ MỚI CẦN XÓA ===
        'Click',   # Yêu cầu thêm
        '推',      # Yêu cầu thêm
        '热卖',    # Yêu cầu thêm
        
        # === SỐ NĂM ĐƠN LẺ - XÓA NGAY (2019-2030) ===
        '2019', '2020', '2021', '2022', '2023', '2024', 
        '2025', '2026', '2027', '2028', '2029', '2030',
        
        # 1. Nguồn hàng & bán buôn (cụm từ)
        '一件代发', '一手货源', '货源充足', '大量现货',
        '批发现货', '批发价', '批发商',
        '清仓处理', 'xả kho', 'thanh lý',
        
        # 2. Tuyển đại lý & hợp tác (cụm từ)
        '大量招实体', '招网店', '招微商', '招代理',
        '网店代理', '微商代理', '实体店代理',
        
        # 3. Thông tin công ty & bản quyền (cụm từ)
        '未经授权', '盗用图片', '投诉原图',
        '我公司', '本公司', '公司投诉',
        
        # 4. Thông tin cửa hàng (cụm từ)
        '本店所有', '本店货源', '本店产品',
        
        # 5. Giá cả & chiết khấu (cụm từ)
        '价格优惠', '量大从优', '量大价优',
        '价格表', 'báo giá', '报价单', '价目表',
        '批发价格', '优惠价格',
        
        # 6. Chính sách & tuyên bố (cụm từ)
        '关于退换', '拒收货物', '签收须知',
        '概不负责', '特此声明', '郑重声明',
        '七天退换', '7天退换',
        
        # 7. Đảm bảo chất lượng (cụm từ)
        '品质保证', '当天发货', '当天发出',
        
        # 8. Liên hệ cá nhân (cụm từ)
        '微信联系', 'QQ联系', '电话联系',
        '手机号码', '热线电话',
        
        # 9. Miễn phí & khuyến mãi (cụm từ)
        '免费送货', 'miễn phí', 'free ship',
        
        # 10. Domain & website (cụm từ)
        'www.', '.com', '.cn', '.net', '.org', '.vn',
        
        # 11. Nút kêu gọi hành động trên ảnh (cụm từ)
        '点击进入', '立即购买', 'BUY NOW', '购买链接',
        
        # 12. Ký hiệu đề xuất/sản phẩm nổi bật (cụm từ hoặc ký tự đặc biệt)
        '热卖推荐', '爆款推荐', '新品推荐',
        
        # 13. Từ khóa tiếng Anh marketing (cụm từ)
        'ON SALE', 'BIG SALE', 'HOT SALE',
        'DISCOUNT', 'PROMOTION', 'SPECIAL OFFER',
        'NEW ARRIVAL', 'BEST SELLER', 'TOP SELLER',
        
        # 14. NĂM SẢN XUẤT/HÀNG TỒN KHO (cụm từ)
        '2019年', '2020年', '2021年', '2022年', '2023年', '2024年', 
        '2025年', '2026年', '2027年', '2028年', '2029年', '2030年',
        '生产日期', '出厂日期', '生产年份', '年份标注',
        '库存处理', '积压库存', '尾货清仓', '清库存',
        '老款式', '旧款式', '过季款', '下架款',
        '停产款', '停售款', '不再生产',
        
        # 15. Kết hợp năm với từ khóa (cụm từ đầy đủ)
        '2019库存', '2020尾货', '2021清仓',
        '老款2019', '旧款2020', '过季2021',
        
        # 16. Các từ khóa mới thêm
        'Click to buy', 'Click here', '推荐购买', '热门推荐',
    ],
    
    # Từ khóa xóa cũ (giữ lại cho tương thích)
    'DELETE_KEYWORDS': [
        # 4 CHỮ QUAN TRỌNG
        '荐', '退', '价', '换',
        # CÁC CHỮ MỚI
        'Click', '推', '热卖',
        # SỐ NĂM ĐƠN LẺ
        '2019', '2020', '2021', '2022', '2023', '2024',
        # Các từ khác
        '价格表', 'báo giá', '报价单', '价目表',
        '微信联系', 'QQ号码', '电话号码',
        '批发价格', '优惠价格', '清仓处理',
        '免费送货', 'BUY NOW', '热卖推荐',
        # NĂM SẢN XUẤT (cụm từ)
        '2019年', '2020年', '2021年', '2022年', '2023年', '2024年',
        '生产日期', '库存处理', '尾货清仓',
        '老款式', '停产款',
    ],
    
    # === THÊM: DANH SÁCH TỪ ĐƠN PHÂN LOẠI ===
    'SINGLE_CHAR_RULES': {
        # 4 CHỮ NGUY HIỂM + SỐ NĂM - XÓA NGAY
        'DANGEROUS_SINGLE_ITEMS': ['荐', '退', '价', '换', '推',
                                  '2019', '2020', '2021', '2022', '2023', '2024',
                                  '2025', '2026', '2027', '2028', '2029', '2030'],
        
        # CÁC TỪ TIẾNG ANH CẦN XÓA
        'DANGEROUS_ENGLISH_ITEMS': ['Click'],
        
        # TỪ ĐƠN THÔNG THƯỜNG - KHÔNG XÓA
        'SAFE_SINGLE_CHARS': ['产', '销', '售', '品', '牌', '色', '码', '货', '型', '号'],
    }
}

# ==================== OCR CONFIG ====================
PAID_OCR_PROVIDER = "google_vision"
OCR_CONFIDENCE_THRESHOLD = 0.15
# Gọi text_detection bổ sung khi paragraph-level không ra CJK (tránh chỉ đọc được số "230" khi vẫn có chữ Trung).
OCR_WORD_CJK_SUPPLEMENT = True
CHINESE_CHAR_REGEX = re.compile(r'[\u4E00-\u9FFF\u3400-\u4DBF\uF900-\uFAFF\u20000-\u2A6DF\u2A700-\u2B73F\u2B740-\u2B81F\u2B820-\u2CEAF\u2CEB0-\u2EBEF]')

# OCR batch optimization
OCR_BATCH_ENABLED = True
OCR_MAX_BATCH_SIZE = 15  # Max images per OCR batch
OCR_MIN_BATCH_SIZE = 3   # Min images to use batch processing

# ==================== URGENT DELETE PATTERNS ====================
# ĐẶC BIỆT: THÊM PATTERN CHO 4 CHỮ QUAN TRỌNG + SỐ NĂM (XÓA NGAY CẢ ĐƠN LẺ)
URGENT_DELETE_PATTERNS = [
    # === 4 CHỮ QUAN TRỌNG - XÓA NGAY KHI XUẤT HIỆN ===
    r'荐',      # Ký hiệu đề xuất
    r'退',      # Hoàn tiền/trả hàng  
    r'价',      # Giá cả
    r'换',      # Đổi trả
    
    # === CÁC CHỮ MỚI CẦN XÓA ===
    r'Click',   # Yêu cầu thêm (tiếng Anh)
    r'推',      # Yêu cầu thêm (chữ Hán)
    r'热卖',    # Yêu cầu thêm (chữ Hán)
    
    # === SỐ NĂM ĐƠN LẺ - XÓA NGAY ===
    r'2019', r'2020', r'2021', r'2022', r'2023', r'2024',
    r'2025', r'2026', r'2027', r'2028', r'2029', r'2030',
    
    # 1. Nguồn hàng & bán buôn (cụm từ)
    r'一件代发',
    r'一手货源',
    r'货源[充足丰满]',
    r'大量现货',
    r'批发现货',
    r'批发[价商]',
    
    # 2. Tuyển đại lý & hợp tác (cụm từ)
    r'大量招[实体网店微商代理代发]{2,}',
    r'招[实体网店微商代理代发]{2,}',
    
    # 3. Thông tin công ty & bản quyền (cụm từ)
    r'未经[我]?公司授权',
    r'擅自盗用[我]?公司图片',
    r'投诉原图',
    r'我公司',
    r'本公司',
    
    # 4. Thông tin cửa hàng (cụm từ)
    r'本店所有产品均是一手货源',
    r'本店货源',
    r'本店产品',
    
    # 5. Giá cả & chiết khấu (cụm từ)
    r'价格优惠',
    r'量大从优',
    r'量大价优',
    
    # 6. Chính sách & tuyên bố (cụm từ)
    r'关于退换',
    r'概不负责',
    r'特此声明',
    r'7天[无理由退换]{2,}',
    
    # 7. Nút kêu gọi hành động (cụm từ)
    r'点击进入',
    r'立即购买',
    r'BUY\s+NOW',
    r'Click\s+(to|here|for)',  # Pattern mới cho Click
    r'Click\s+buy',            # Pattern mới cho Click
    
    # 8. Ký hiệu đề xuất (cụm từ)
    r'热卖推荐',
    r'爆款推荐',
    r'新品推荐',
    r'热门推荐',  # Pattern mới
    
    # 9. Kết hợp từ khóa giặt tẩy với thông tin bán hàng
    r'(洗涤[说明方式建议保养]{2,}).*(价格|批发|微信|电话|公司|代理|代发|货源|现货|优惠|购买|点击进入|立即购买|BUY\s+NOW|Click)',
    r'(洗水唛|护理说明).*(价格|批发|微信|电话|公司|代理|代发|货源|现货|优惠|购买|点击进入|立即购买|BUY\s+NOW|Click)',
    r'(价格|批发|微信|电话|公司|代理|代发|货源|现货|优惠|购买|点击进入|立即购买|BUY\s+NOW|Click).*(洗涤[说明方式建议保养]{2,}|洗水唛|护理说明)',
    
    # 10. Kết hợp từ khóa nguy hiểm
    r'(一手货源.*一件代发)',
    r'(未经授权.*盗用图片)',
    r'(本店所有.*一手货源)',
    r'(大量招.*代发)',
    
    # 11. Các từ khóa tiếng Anh marketing
    r'(ON|BIG|HOT)\s+SALE',
    r'SPECIAL\s+OFFER',
    r'NEW\s+ARRIVAL',
    r'BEST\s+SELLER',
    r'TOP\s+SELLER',
    
    # 12. NĂM SẢN XUẤT/HÀNG TỒN KHO (cụm từ)
    r'20(19|20|21|22|23|24|25|26|27|28|29|30)年',
    r'生产日期[：:]?\s*20[0-9]{2}',
    r'出厂日期[：:]?\s*20[0-9]{2}',
    r'生产年份[：:]?\s*20[0-9]{2}',
    r'有效期至[：:]?\s*20[0-9]{2}',
    r'保质期至[：:]?\s*20[0-9]{2}',
    r'库存[积压尾货清仓处理]{2,}',
    r'[积压尾货清仓]{2,}库存',
    r'[老旧过时下架]{2,}款',
    r'[停产停售下架]{2,}',
    
    # 13. Kết hợp năm với thông tin bán hàng
    r'(20(19|20|21|22|23|24|25|26|27|28|29|30)).*(清仓|处理|特价|优惠|甩卖)',
    r'(清仓|处理|特价|优惠|甩卖).*(20(19|20|21|22|23|24|25|26|27|28|29|30))',
    r'(库存|尾货).*(20(19|20|21|22|23|24|25|26|27|28|29|30))',
    r'(20(19|20|21|22|23|24|25|26|27|28|29|30)).*(库存|尾货)',
    
    # 14. Kết hợp năm với sản phẩm cũ
    r'20(19|20|21|22|23|24).*(老款|旧款|过季|下架|停产)',
    r'(老款|旧款|过季|下架|停产).*20(19|20|21|22|23|24)',
    
    # 15. Pattern cho "荐" kết hợp
    r'荐.*(价格|批发|微信|电话|购买|BUY\s+NOW|Click)',
    r'(价格|批发|微信|电话|购买|BUY\s+NOW|Click).*荐',
    r'(热卖|爆款|新品).*荐',
    r'荐.*(热卖|爆款|新品)',
    
    # 16. Pattern cho các từ mới
    r'推.*(荐|销|介)',
    r'(热卖|热门).*(推荐|促销|活动)',
    r'Click.*(here|now|to buy|for more)',
]

URGENT_DELETE_REGEX = re.compile("|".join(URGENT_DELETE_PATTERNS), re.IGNORECASE)

# ==================== CONTENT FILTERING ====================
# ĐẶC BIỆT: THÊM 4 CHỮ QUAN TRỌNG + SỐ NĂM VÀO SKIP PATTERNS
SKIP_PATTERNS = [
    # === 4 CHỮ QUAN TRỌNG - XÓA NGAY ===
    r'荐',      # Ký hiệu đề xuất
    r'退',      # Hoàn tiền/trả hàng  
    r'价',      # Giá cả
    r'换',      # Đổi trả
    
    # === CÁC CHỮ MỚI CẦN XÓA ===
    r'Click',   # Yêu cầu thêm
    r'推',      # Yêu cầu thêm
    r'热卖',    # Yêu cầu thêm
    
    # === SỐ NĂM ĐƠN LẺ - XÓA NGAY ===
    r'2019', r'2020', r'2021', r'2022', r'2023', r'2024',
    r'2025', r'2026', r'2027', r'2028', r'2029', r'2030',
    
    # 1. CHỈ XÓA KHI CÓ GIÁ TIỀN CỤ THỂ VÀ ĐƠN VỊ
    r"价格[表目单]",
    r"报价[单表]",
    r"\d+\s*[元¥￥\$人民币]",
    r"[¥￥\$]\s*\d+",
    r"RMB\s*\d+",
    r"USD\s*\d+",
    
    # 2. LIÊN HỆ CÁ NHÂN/NHÀ CUNG CẤP
    r"微信[号：:]?\s*[a-zA-Z0-9]{6,}",
    r"QQ[号：:]?\s*\d{6,}",
    r"电话[：:]\s*\d{8,}",
    r"手机[：:]\s*\d{10,}",
    
    # 3. THÔNG TIN CÔNG TY/NHÀ MÁY
    r"[公司工厂][\u4e00-\u9fff\s]{2,}[地址厂址]",
    r"批发[价商]?",
    r"批发现货",
    
    # 4. Nguồn hàng & drop shipping
    r"一手货源",
    r"一件代发",
    r"货源充足",
    r"大量现货",
    r"大量招[实体网店微商代发代理]{2,}",
    r"未经我公司授权",
    r"擅自盗用我公司图片",
    
    # 5. Giá cả & chiết khấu
    r"价格优惠",
    r"量大从优",
    
    # 6. Chính sách & tuyên bố
    r"关于退换",
    r"概不负责",
    r"特此声明",
    
    # 7. Nút kêu gọi hành động
    r"点击进入",
    r"立即购买",
    r"BUY\s+NOW",
    r"Click\s+(to|here|for|buy)",  # Pattern mới cho Click
    
    # 8. Ký hiệu đề xuất
    r"热卖推荐",
    r"爆款推荐",
    r"热门推荐",  # Pattern mới
    
    # 9. DOMAIN/WEBSITE
    r"[a-zA-Z0-9-]+\.[a-z]{2,}(?:/\S*)?",
    r"www\.[a-zA-Z0-9-]+\.[a-z]{2,}",
    
    # 10. THÔNG TIN HẬU MÃI
    r"7天[无理由退换]{2,}",
    r"包邮服务",
    r"保修[期服务]{2,}",
    
    # 11. Từ khóa marketing tiếng Anh
    r"(ON|BIG|HOT)\s+SALE",
    r"SPECIAL\s+OFFER",
    r"NEW\s+ARRIVAL",
    r"BEST\SELLER",
    
    # 12. NĂM SẢN XUẤT/HÀNG TỒN KHO (cụm từ)
    r'20(19|20|21|22|23|24|25|26|27|28|29|30)年',
    r'生产日期[：:]\s*20[0-9]{2}',
    r'出厂日期[：:]\s*20[0-9]{2}',
    r'生产年份[：:]\s*20[0-9]{2}',
    r'有效期至[：:]\s*20[0-9]{2}',
    r'保质期至[：:]\s*20[0-9]{2}',
    r'库存[积压尾货]{2,}',
    r'积压库存',
    r'尾货处理',
    r'清库存',
    r'老款式', r'旧款式', r'过季款', r'下架款',
    r'停产款', r'停售款', r'不再生产',
]

SKIP_REGEX = re.compile("|".join(SKIP_PATTERNS), re.IGNORECASE)
DOMAIN_REGEX = re.compile(r"(https?://|www\.[a-z0-9\-]+\.[a-z]{2,})|[a-z0-9\-]+\.(com|cn|net|org|vn)", re.IGNORECASE)
SIZE_PATTERN = re.compile(r'\d{2,4}[x×]\d{2,4}\.(jpg|jpeg|png|webp|bmp|gif)', re.IGNORECASE)

# ==================== PERFORMANCE CONFIG ====================
MAX_WORKERS = 3
DOWNLOAD_TIMEOUT = 30
UPLOAD_TIMEOUT = 30
WAIT_BETWEEN_ROWS = 2
WAIT_BETWEEN_IMAGES = 1
WAIT_BETWEEN_CONVERSATIONS = 2
PAGE_LOAD_TIMEOUT = 30
GEMINI_NAVIGATION_TIMEOUT = 15

# Multi-threading config
THREAD_POOL_MAX_WORKERS = 4
THREAD_TIMEOUT = 60

# ==================== LOGGING CONFIG ====================
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_FILE = os.path.join(LOGS_DIR, "image_processor.log")

# ==================== ERROR HANDLING ====================
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds
FATAL_ERROR_COOLDOWN = 300  # 5 minutes for fatal errors

# Gemini specific error handling
GEMINI_MAX_CONSECUTIVE_ERRORS = 5
GEMINI_SYSTEM_FAILURE_COOLDOWN = 1800  # 30 minutes

# ==================== QUALITY CONTROL ====================
QUALITY_CHECK_ENABLED = True
MIN_QUALITY_SCORE = 0.7  # Minimum quality score to accept image
QUALITY_CHECK_SAMPLE_SIZE = 5  # Number of images to sample for quality check

# Text redrawing quality
TEXT_CONTRAST_THRESHOLD = 128  # Brightness threshold for text color selection
TEXT_THICKNESS = 1

# ==================== COLOR CONFIG ====================
COLOR_WHITE = (255, 255, 255)
COLOR_BLACK = (0, 0, 0)
COLOR_RED = (0, 0, 255)
COLOR_GREEN = (0, 255, 0)
COLOR_BLUE = (255, 0, 0)
COLOR_YELLOW = (0, 255, 255)

# Background color detection
BG_SAMPLE_EXPAND = 10  # Pixels to expand for background sampling
BG_MEDIAN_FILTER = True  # Use median filter for background color

# ==================== CREATE DIRECTORIES ====================
def setup_directories():
    """Tạo tất cả thư mục cần thiết"""
    directories = [
        TEMP_DIR,
        TEMP_IMAGES_DIR,
        os.path.join(TEMP_IMAGES_DIR, "current"),
        os.path.join(TEMP_IMAGES_DIR, "gemini_batches"),
        os.path.join(TEMP_IMAGES_DIR, "split_images"),
        DOWNLOADS_DIR,
        os.path.join(DOWNLOADS_DIR, "temp_download"),
        LOGS_DIR,
        CACHE_DIR,
        CHROME_PROFILE_PATH,
        os.path.join(CHROME_PROFILE_PATH, "Default"),
        os.path.join(CHROME_PROFILE_PATH, "Default", "Extensions"),
        *([os.path.dirname(GCP_KEY_FILE)] if GCP_KEY_FILE else []),
    ]
    
    created = []
    errors = []
    
    for directory in directories:
        try:
            os.makedirs(directory, exist_ok=True)
            created.append(directory)
        except Exception as e:
            errors.append(f"{directory}: {e}")
    
    return created, errors

# Tạo thư mục ngay khi import
created_dirs, dir_errors = setup_directories()

# ==================== UTILITY FUNCTIONS ====================
def validate_config():
    """Validate configuration and return any issues"""
    issues = []
    
    # Check required files
    if not os.path.exists(GCP_KEY_FILE):
        issues.append(f"❌ Google Cloud Vision key not found: {GCP_KEY_FILE}")
    
    # Check API keys
    if not BUNNY_API_KEY:
        issues.append("⚠️  BunnyCDN API key is not configured")
    
    if not DEEPSEEK_API_KEY:
        issues.append("⚠️  DeepSeek API key is not configured")
    
    # Check directories
    for directory in [TEMP_DIR, DOWNLOADS_DIR, LOGS_DIR, CACHE_DIR]:
        if not os.path.exists(directory):
            try:
                os.makedirs(directory, exist_ok=True)
            except:
                issues.append(f"❌ Cannot create directory: {directory}")
    
    return issues

def get_image_processing_stats() -> Dict[str, Any]:
    """Get statistics about image processing configuration"""
    return {
        'batch_size': BATCH_SIZE,
        'min_image_width': MIN_IMAGE_WIDTH,
        'max_image_width': MAX_IMAGE_WIDTH,
        'gemini_check_enabled': GEMINI_POST_CHECK_ENABLED,
        'gemini_batch_size': GEMINI_BATCH_CHECK_SIZE,
        'ocr_batch_enabled': OCR_BATCH_ENABLED,
        'ocr_max_batch_size': OCR_MAX_BATCH_SIZE,
        'max_workers': MAX_WORKERS,
        'thread_pool_workers': THREAD_POOL_MAX_WORKERS,
        'quality_check_enabled': QUALITY_CHECK_ENABLED,
        'laundry_keywords_count': len(LAUNDRY_CARE_KEYWORDS),
        'urgent_delete_patterns_count': len(URGENT_DELETE_PATTERNS),
        'skip_patterns_count': len(SKIP_PATTERNS),
        'image_splitting_enabled': IMAGE_SPLITTING_ENABLED,
        'max_image_height': MAX_IMAGE_HEIGHT,
        'min_image_height': MIN_IMAGE_HEIGHT,
    }

def get_cv2_font_constants():
    """Get OpenCV font constants safely"""
    try:
        import cv2
        return {
            'FONT_HERSHEY_SIMPLEX': cv2.FONT_HERSHEY_SIMPLEX,
            'FONT_HERSHEY_COMPLEX_SMALL': cv2.FONT_HERSHEY_COMPLEX_SMALL,
            'FONT_HERSHEY_DUPLEX': cv2.FONT_HERSHEY_DUPLEX,
            'LINE_AA': cv2.LINE_AA,
        }
    except ImportError:
        return {
            'FONT_HERSHEY_SIMPLEX': 0,
            'FONT_HERSHEY_COMPLEX_SMALL': 1,
            'FONT_HERSHEY_DUPLEX': 2,
            'LINE_AA': 16,
        }

# ==================== SMART DELETE CHECK FUNCTION ====================
def should_delete_image_urgent(text_content: str) -> bool:
    """
    KIỂM TRA THÔNG MINH: 
    - 4 CHỮ QUAN TRỌNG (荐, 退, 价, 换): XÓA NGAY KHI CÓ 1 CHỮ
    - CÁC CHỮ MỚI (Click, 推, 热卖): XÓA NGAY KHI CÓ 1 CHỮ/TỪ
    - SỐ NĂM ĐƠN LẺ (2019-2030): XÓA NGAY
    - Các từ khác: Chỉ xóa khi là cụm từ 2+ chữ có ý nghĩa
    
    Args:
        text_content: Nội dung text từ OCR
    
    Returns:
        bool: True nên xóa, False giữ lại
    """
    if not text_content or not text_content.strip():
        return False
    
    # CHUẨN HÓA TEXT
    normalized_text = text_content.strip()
    
    # === 1. KIỂM TRA 4 CHỮ QUAN TRỌNG - XÓA NGAY ===
    DANGEROUS_CHARS = ['荐', '退', '价', '换', '推']
    for char in DANGEROUS_CHARS:
        if char in normalized_text:
            print(f"⚠️  PHÁT HIỆN CHỮ NGUY HIỂM '{char}' trong: {normalized_text[:50]}...")
            return True
    
    # === 2. KIỂM TRA CÁC TỪ TIẾNG ANH NGUY HIỂM - XÓA NGAY ===
    DANGEROUS_ENGLISH = ['Click']
    for word in DANGEROUS_ENGLISH:
        # Tìm từ đầy đủ, không phải phần của từ khác
        if re.search(r'\b' + re.escape(word) + r'\b', normalized_text, re.IGNORECASE):
            print(f"⚠️  PHÁT HIỆN TỪ NGUY HIỂM '{word}' trong: {normalized_text[:50]}...")
            return True
    
    # === 3. KIỂM TRA TỪ "热卖" - XÓA NGAY ===
    if '热卖' in normalized_text:
        print(f"⚠️  PHÁT HIỆN TỪ NGUY HIỂM '热卖' trong: {normalized_text[:50]}...")
        return True
    
    # === 4. KIỂM TRA SỐ NĂM ĐƠN LẺ (2019-2030) - XÓA NGAY ===
    # Tạo pattern cho năm 2019-2030
    import re
    year_pattern = r'(?<!\d)20(19|20|21|22|23|24|25|26|27|28|29|30)(?!\d)'
    year_matches = re.findall(year_pattern, normalized_text)
    
    if year_matches:
        print(f"⚠️  PHÁT HIỆN SỐ NĂM {year_matches} trong: {normalized_text[:50]}...")
        return True
    
    # === 5. KIỂM TRA CÁC TỪ ĐƠN THÔNG THƯỜNG - KHÔNG XÓA ===
    SAFE_SINGLE_CHARS = ['产', '销', '售', '品', '牌', '色', '码', '货', '型', '号']
    
    # Kiểm tra nếu text chỉ có 1-2 ký tự và là từ an toàn
    if len(normalized_text) <= 2:
        for char in SAFE_SINGLE_CHARS:
            if normalized_text == char:
                return False
    
    # === 6. KIỂM TRA CÁC CỤM TỪ CÓ ÍT NHẤT 2 CHỮ ===
    URGENT_PHRASES_2PLUS = [
        # Nguồn hàng & bán buôn
        '一件代发', '一手货源', '货源充足', '大量现货',
        '批发现货', '批发价', '批发商',
        # Liên hệ
        '微信联系', 'QQ联系', '电话联系',
        # Giá cả
        '价格优惠', '量大从优', '价格表',
        # Năm sản xuất (dạng đầy đủ)
        '2019年', '2020年', '2021年', '2022年',
        '生产日期', '出厂日期', '生产年份',
        # Hàng tồn
        '库存处理', '尾货清仓', '清库存',
        # Hàng cũ
        '老款式', '旧款式', '停产款',
        # Các từ mới
        '热卖推荐', 'Click here', 'Click to buy',
    ]
    
    found_count = 0
    for phrase in URGENT_PHRASES_2PLUS:
        if phrase in normalized_text:
            found_count += 1
    
    # Chỉ xóa nếu tìm thấy ít nhất 1 cụm từ đầy đủ
    if found_count >= 1:
        print(f"⚠️  Phát hiện {found_count} cụm từ urgent trong: {normalized_text[:50]}...")
        return True
    
    # === 7. KIỂM TRA REGEX (chỉ cho các pattern phức tạp) ===
    if URGENT_DELETE_REGEX.search(normalized_text):
        # Lưu ý: các chữ/từ nguy hiểm đã được xử lý ở trên
        match = URGENT_DELETE_REGEX.search(normalized_text)
        if match:
            matched_text = match.group()
            # Kiểm tra không phải là từ đơn an toàn
            if matched_text not in SAFE_SINGLE_CHARS:
                # Kiểm tra không phải là Click trong từ lớn hơn (ví dụ: Clickable)
                if 'Click' in matched_text and len(matched_text) > 5:
                    # Nếu Click là phần của từ dài hơn, kiểm tra kỹ hơn
                    if re.search(r'\bClick\b', matched_text):
                        return True
                    else:
                        return False
                return True
    
    return False

# ==================== EXPORT ALL VARIABLES ====================
__all__ = [
    # Paths
    'BASE_DIR', 'LOGO_PATH', 'FONT_PATH', 'GCP_KEY_FILE',
    'TEMP_DIR', 'TEMP_IMAGES_DIR', 'DOWNLOADS_DIR', 'LOGS_DIR', 'CACHE_DIR',
    'CHROME_PROFILE_PATH',
    
    # Batch Processing
    'BATCH_SIZE',
    
    # API Keys
    'BUNNY_API_KEY', 'STORAGE_ZONE_NAME', 'BUNNY_STORAGE_HOSTNAME', 'BUNNY_CDN_PUBLIC_BASE',
    'DEEPSEEK_API_KEY', 'DEEPSEEK_URL',
    
    # Gemini
    'GEMINI_URL', 'GEMINI_PROMPT', 'HEADLESS', 'GEMINI_PROCESS_TIMEOUT',
    
    # Gemini Post-Check
    'GEMINI_POST_CHECK_ENABLED', 'GEMINI_BATCH_CHECK_SIZE',
    'GEMINI_ERROR_THRESHOLD', 'GEMINI_CHECK_TIMEOUT', 'GEMINI_MAX_WORKERS',
    
    # Image Processing
    'MAX_IMAGE_SIZE', 'MIN_IMAGE_SIZE', 'MIN_IMAGE_WIDTH', 'MAX_IMAGE_WIDTH', 
    'MERGE_SPACING', 'BACKGROUND_COLOR', 'SAVE_QUALITY',
    'FONT_SCALE_FACTOR', 'MIN_FONT_SCALE', 'MAX_FONT_SCALE',
    'TEXT_PADDING', 'BACKGROUND_EXPAND',
    
    # Image Splitting
    'IMAGE_SPLITTING_ENABLED', 'MAX_IMAGE_HEIGHT', 'MIN_IMAGE_HEIGHT',
    'SPLIT_SAFE_MARGIN', 'SPLIT_MIN_GAP_SIZE', 'SPLIT_MIN_PART_HEIGHT',
    'SPLIT_3_PARTS_THRESHOLD', 'SPLIT_MIN_BLOCKS_FOR_3',
    
    # Classification
    'IMAGE_CLASSIFICATION', 'URGENT_DELETE_REGEX', 'LAUNDRY_CARE_KEYWORDS',
    
    # OCR
    'PAID_OCR_PROVIDER', 'OCR_CONFIDENCE_THRESHOLD', 'OCR_WORD_CJK_SUPPLEMENT', 'CHINESE_CHAR_REGEX',
    'OCR_BATCH_ENABLED', 'OCR_MAX_BATCH_SIZE', 'OCR_MIN_BATCH_SIZE',
    
    # Content Filtering
    'SKIP_PATTERNS', 'SKIP_REGEX', 'DOMAIN_REGEX', 'SIZE_PATTERN',
    'URGENT_DELETE_PATTERNS',
    
    # Performance
    'MAX_WORKERS', 'DOWNLOAD_TIMEOUT', 'UPLOAD_TIMEOUT', 'WAIT_BETWEEN_ROWS',
    'WAIT_BETWEEN_IMAGES', 'WAIT_BETWEEN_CONVERSATIONS', 'PAGE_LOAD_TIMEOUT',
    'GEMINI_NAVIGATION_TIMEOUT', 'THREAD_POOL_MAX_WORKERS', 'THREAD_TIMEOUT',
    
    # Logging
    'LOG_LEVEL', 'LOG_FORMAT', 'LOG_FILE',
    
    # Error Handling
    'MAX_RETRIES', 'RETRY_DELAY', 'FATAL_ERROR_COOLDOWN',
    'GEMINI_MAX_CONSECUTIVE_ERRORS', 'GEMINI_SYSTEM_FAILURE_COOLDOWN',
    
    # Quality Control
    'QUALITY_CHECK_ENABLED', 'MIN_QUALITY_SCORE', 'QUALITY_CHECK_SAMPLE_SIZE',
    'TEXT_CONTRAST_THRESHOLD', 'TEXT_THICKNESS',
    
    # Colors
    'COLOR_WHITE', 'COLOR_BLACK', 'COLOR_RED', 'COLOR_GREEN',
    'COLOR_BLUE', 'COLOR_YELLOW', 'BG_SAMPLE_EXPAND', 'BG_MEDIAN_FILTER',
    
    # Functions
    'setup_directories', 'validate_config', 'get_image_processing_stats',
    'get_cv2_font_constants', 'should_delete_image_urgent',
]

# ==================== DEBUG INFO ====================
if __name__ == "__main__":
    print("=" * 80)
    print("✅ CONFIG.PY ĐÃ TẢI THÀNH CÔNG")
    print("🚀 ĐẶC BIỆT: 4 CHỮ QUAN TRỌNG + SỐ NĂM ĐƠN LẺ XÓA NGAY")
    print("✨ MỚI: ĐÃ THÊM TỪ KHÓA Click, 推, 热卖 VÀO DANH SÁCH XÓA")
    print("=" * 80)
    
    print(f"\n📍 PATH CONFIGURATION:")
    print(f"  BASE_DIR: {BASE_DIR}")
    print(f"  TEMP_DIR: {TEMP_DIR}")
    print(f"  DOWNLOADS_DIR: {DOWNLOADS_DIR}")
    
    print(f"\n⚙️  MAIN CONFIGURATION:")
    print(f"  BATCH_SIZE: {BATCH_SIZE}")
    
    print(f"\n🎯 QUY TẮC XÓA ẢNH MỚI:")
    print(f"  ⚠️  4 CHỮ NGUY HIỂM - XÓA NGAY:")
    print(f"     • 荐 - Ký hiệu đề xuất")
    print(f"     • 退 - Hoàn tiền/trả hàng")
    print(f"     • 价 - Giá cả")
    print(f"     • 换 - Đổi trả")
    print(f"  ⚠️  TỪ KHÓA MỚI - XÓA NGAY:")
    print(f"     • Click - Các từ tiếng Anh kêu gọi hành động")
    print(f"     • 推 - Đẩy/giới thiệu")
    print(f"     • 热卖 - Bán chạy/hot sale")
    print(f"  ⚠️  SỐ NĂM ĐƠN LẺ - XÓA NGAY:")
    print(f"     • 2019, 2020, 2021, 2022, 2023, 2024")
    print(f"     • 2025, 2026, 2027, 2028, 2029, 2030")
    print(f"  ✅ Các từ đơn an toàn - KHÔNG xóa:")
    print(f"     • 产, 销, 品, 牌, 色, 码, 货, 型, 号")
    print(f"  🔥 Cụm từ urgent - XÓA: 一件代发, 价格表, 微信联系, Click here")
    
    print(f"\n✂️  IMAGE SPLITTING CONFIG:")
    print(f"  IMAGE_SPLITTING_ENABLED: {IMAGE_SPLITTING_ENABLED}")
    print(f"  MAX_IMAGE_HEIGHT: {MAX_IMAGE_HEIGHT}px")
    
    # Test hàm thông minh
    print(f"\n🧪 TEST HÀM THÔNG MINH (should_delete_image_urgent):")
    test_cases = [
        # 4 CHỮ QUAN TRỌNG - XÓA NGAY
        ("荐", True, "荐 - XÓA NGAY"),
        ("退", True, "退 - XÓA NGAY"),
        ("价", True, "价 - XÓA NGAY"),
        ("换", True, "换 - XÓA NGAY"),
        
        # TỪ KHÓA MỚI - XÓA NGAY
        ("Click", True, "Click - XÓA NGAY"),
        ("推", True, "推 - XÓA NGAY"),
        ("热卖", True, "热卖 - XÓA NGAY"),
        ("Click here", True, "Click here - XÓA"),
        ("热卖推荐", True, "热卖推荐 - XÓA"),
        ("推荐商品", True, "Có '推' - XÓA"),
        
        # SỐ NĂM ĐƠN LẺ - XÓA NGAY
        ("2019", True, "2019 - XÓA NGAY"),
        ("2020", True, "2020 - XÓA NGAY"),
        ("2021", True, "2021 - XÓA NGAY"),
        ("2022", True, "2022 - XÓA NGAY"),
        ("2023", True, "2023 - XÓA NGAY"),
        ("2024", True, "2024 - XÓA NGAY"),
        ("2019年", True, "2019年 - XÓA"),
        ("库存2020", True, "库存2020 - XÓA"),
        
        # TỪ ĐƠN AN TOÀN - KHÔNG XÓA
        ("产", False, "产 - KHÔNG xóa"),
        ("产品", False, "产品 - từ thông thường"),
        ("销", False, "销 - KHÔNG xóa"),
        ("售", False, "售 - KHÔNG xóa"),
        
        # CỤM TỪ URGENT
        ("一件代发", True, "一件代发 - XÓA"),
        ("价格表", True, "价格表 - XÓA"),
        ("微信联系", True, "微信联系 - XÓA"),
        ("Click to buy", True, "Click to buy - XÓA"),
        
        # TỪ THÔNG THƯỜNG
        ("产品规格", False, "产品规格 - KHÔNG xóa"),
        ("颜色选择", False, "颜色选择 - KHÔNG xóa"),
        ("尺寸表", False, "尺寸表 - KHÔNG xóa"),
        
        # KẾT HỢP
        ("2021清仓处理", True, "2021清仓处理 - XÓA"),
        ("荐2022热卖", True, "荐2022热卖 - XÓA"),
        ("Click 2023", True, "Click 2023 - XÓA"),
        ("推荐2024", True, "推荐2024 - XÓA"),
    ]
    
    for text, expected, description in test_cases:
        result = should_delete_image_urgent(text)
        status = "✅" if result == expected else "❌"
        print(f"  {status} '{text}' -> {result} ({description})")
    
    # Validate config
    print(f"\n🔍 VALIDATING CONFIGURATION...")
    issues = validate_config()
    
    if issues:
        print(f"⚠️  CONFIGURATION ISSUES FOUND:")
        for issue in issues:
            print(f"  • {issue}")
    else:
        print(f"✅ Configuration validation passed!")
    
    # Show processing stats
    stats = get_image_processing_stats()
    print(f"\n📈 PROCESSING STATISTICS:")
    print(f"  • Batch size: {stats['batch_size']}")
    print(f"  • Image splitting: {'ENABLED' if stats['image_splitting_enabled'] else 'DISABLED'}")
    print(f"  • Max image height: {stats['max_image_height']}px")
    print(f"  • Gemini check: {'ENABLED' if stats['gemini_check_enabled'] else 'DISABLED'}")
    print(f"  • Urgent delete patterns: {stats['urgent_delete_patterns_count']}")
    print(f"  • Skip patterns: {stats['skip_patterns_count']}")
    
    # Check OpenCV availability
    try:
        import cv2
        print(f"  • OpenCV version: {cv2.__version__}")
        print(f"✅ OpenCV is available")
    except ImportError:
        print(f"⚠️  OpenCV (cv2) is NOT installed.")
    
    print(f"\n🚀 HỆ THỐNG ĐÃ SẴN SÀNG!")
    print("   ⚠️  荐, 退, 价, 换 + Click, 推, 热卖 + 2019-2030 - XÓA NGAY KHI PHÁT HIỆN")
    print("=" * 80)
