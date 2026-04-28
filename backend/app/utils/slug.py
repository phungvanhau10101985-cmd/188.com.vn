
import re
import unicodedata

def create_slug(text: str) -> str:
    """
    Tạo slug từ text cho URL thân thiện SEO với hỗ trợ tiếng Việt đầy đủ
    """
    if not text:
        return ""
    
    # Map các ký tự tiếng Việt có dấu sang không dấu
    vietnamese_map = {
        'à': 'a', 'á': 'a', 'ả': 'a', 'ã': 'a', 'ạ': 'a',
        'ă': 'a', 'ằ': 'a', 'ắ': 'a', 'ẳ': 'a', 'ẵ': 'a', 'ặ': 'a',
        'â': 'a', 'ầ': 'a', 'ấ': 'a', 'ẩ': 'a', 'ẫ': 'a', 'ậ': 'a',
        'è': 'e', 'é': 'e', 'ẻ': 'e', 'ẽ': 'e', 'ẹ': 'e',
        'ê': 'e', 'ề': 'e', 'ế': 'e', 'ể': 'e', 'ễ': 'e', 'ệ': 'e',
        'ì': 'i', 'í': 'i', 'ỉ': 'i', 'ĩ': 'i', 'ị': 'i',
        'ò': 'o', 'ó': 'o', 'ỏ': 'o', 'õ': 'o', 'ọ': 'o',
        'ô': 'o', 'ồ': 'o', 'ố': 'o', 'ổ': 'o', 'ỗ': 'o', 'ộ': 'o',
        'ơ': 'o', 'ờ': 'o', 'ớ': 'o', 'ở': 'o', 'ỡ': 'o', 'ợ': 'o',
        'ù': 'u', 'ú': 'u', 'ủ': 'u', 'ũ': 'u', 'ụ': 'u',
        'ư': 'u', 'ừ': 'u', 'ứ': 'u', 'ử': 'u', 'ữ': 'u', 'ự': 'u',
        'ỳ': 'y', 'ý': 'y', 'ỷ': 'y', 'ỹ': 'y', 'ỵ': 'y',
        'đ': 'd',
        'À': 'a', 'Á': 'a', 'Ả': 'a', 'Ã': 'a', 'Ạ': 'a',
        'Ă': 'a', 'Ằ': 'a', 'Ắ': 'a', 'Ẳ': 'a', 'Ẵ': 'a', 'Ặ': 'a',
        'Â': 'a', 'Ầ': 'a', 'Ấ': 'a', 'Ẩ': 'a', 'Ẫ': 'a', 'Ậ': 'a',
        'È': 'e', 'É': 'e', 'Ẻ': 'e', 'Ẽ': 'e', 'Ẹ': 'e',
        'Ê': 'e', 'Ề': 'e', 'Ế': 'e', 'Ể': 'e', 'Ễ': 'e', 'Ệ': 'e',
        'Ì': 'i', 'Í': 'i', 'Ỉ': 'i', 'Ĩ': 'i', 'Ị': 'i',
        'Ò': 'o', 'Ó': 'o', 'Ỏ': 'o', 'Õ': 'o', 'Ọ': 'o',
        'Ô': 'o', 'Ồ': 'o', 'Ố': 'o', 'Ổ': 'o', 'Ỗ': 'o', 'Ộ': 'o',
        'Ơ': 'o', 'Ờ': 'o', 'Ớ': 'o', 'Ở': 'o', 'Ỡ': 'o', 'Ợ': 'o',
        'Ù': 'u', 'Ú': 'u', 'Ủ': 'u', 'Ũ': 'u', 'Ụ': 'u',
        'Ư': 'u', 'Ừ': 'u', 'Ứ': 'u', 'Ử': 'u', 'Ữ': 'u', 'Ự': 'u',
        'Ỳ': 'y', 'Ý': 'y', 'Ỷ': 'y', 'Ỹ': 'y', 'Ỵ': 'y',
        'Đ': 'd'
    }
    
    # Chuyển về unicode decomposition
    text = unicodedata.normalize('NFKD', text)
    
    # Thay thế ký tự tiếng Việt
    result = []
    for char in text:
        if char in vietnamese_map:
            result.append(vietnamese_map[char])
        else:
            result.append(char)
    
    text = ''.join(result)
    
    # Loại bỏ dấu combining characters (giữ nguyên logic gốc)
    text = ''.join([c for c in text if not unicodedata.combining(c)])
    
    # Chuyển thành chữ thường (giữ nguyên logic gốc)
    text = text.lower()
    
    # Thay thế ký tự không phải chữ cái, số bằng dấu gạch ngang (giữ nguyên logic gốc)
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    
    # Thay thế khoảng trắng và dấu gạch ngang liên tiếp bằng một dấu gạch ngang (giữ nguyên logic gốc)
    text = re.sub(r'[\s-]+', '-', text)
    
    # Loại bỏ dấu gạch ngang ở đầu và cuối (giữ nguyên logic gốc)
    text = text.strip('-')
    
    return text

def create_product_slug(name: str, product_id: str) -> str:
    """
    Tạo slug cho sản phẩm kết hợp tên và ID với hỗ trợ tiếng Việt
    GIỮ NGUYÊN FUNCTION GỐC - chỉ cải thiện xử lý tiếng Việt
    """
    slug_name = create_slug(name)
    return f"{slug_name}-{product_id}"

def test_slug_functions():
    """
    Hàm test để verify slug generation hoạt động đúng
    Có thể xóa sau khi test xong
    """
    test_cases = [
        ("Giày Da Nam Cao Cấp", "giay-da-nam-cao-cap"),
        ("Áo Thun Cotton", "ao-thun-cotton"), 
        ("Quần Âu Công Sở", "quan-au-cong-so"),
        ("Áo Khoác Dù Chống Nắng", "ao-khoac-du-chong-nang"),
        ("Váy Đầm Dự Tiệc", "vay-dam-du-tiec"),
        ("Mũ Bảo Hiểm", "mu-bao-hiem"),
        ("Đồng Hồ Thể Thao", "dong-ho-the-thao"),
        ("Ốp Lưng Điện Thoại", "op-lung-dien-thoai"),
        ("Pin Sạc Dự Phòng", "pin-sac-du-phong"),
        ("Tai Nghe Bluetooth", "tai-nghe-bluetooth"),
    ]
    
    print("🧪 TESTING SLUG FUNCTIONS")
    print("=" * 50)
    
    all_passed = True
    for input_text, expected in test_cases:
        result = create_slug(input_text)
        status = "✅" if result == expected else "❌"
        print(f"{status} '{input_text}' → '{result}'")
        if result != expected:
            all_passed = False
            print(f"   Expected: '{expected}'")
    
    # Test product slug
    print("\n🧪 TESTING PRODUCT SLUG")
    product_result = create_product_slug("Giày Da Nam", "A744673124729a188b0013")
    expected_product = "giay-da-nam-A744673124729a188b0013"
    status = "✅" if product_result == expected_product else "❌"
    print(f"{status} Product slug: '{product_result}'")
    
    if all_passed and product_result == expected_product:
        print("\n🎉 ALL TESTS PASSED! Slug generation is working perfectly.")
    else:
        print("\n❌ SOME TESTS FAILED! Please check the implementation.")
    
    return all_passed

if __name__ == "__main__":
    # Chạy test khi execute file trực tiếp
    test_slug_functions()
