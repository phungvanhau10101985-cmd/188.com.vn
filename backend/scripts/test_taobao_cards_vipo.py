import os
import sys
import json

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.listing_import_queue import _execute_one_import
from app.db.session import SessionLocal
from app.crud import product_import_draft as draft_crud

def main():
    url = "https://vipomall.vn/san-pham/645058158951?platform_type=10"
    source = "vipomall"
    admin_id = 1
    overlay = {
        "price": 474848,
        "chinese_name": "夏季走秀新款精美荷花刺绣短袖衬衫男式休闲上衣欧美跨境亚马逊款",
        "shop_name_chinese": "广州亿文服饰有限公司",
        "pro_lower_price": "132.6391",
        "pro_high_price": "132.6391"
    }
    
    print(f"Testing URL via _execute_one_import: {url}")
    print(f"Overlay data: {json.dumps(overlay, ensure_ascii=False)}")
    
    try:
        result = _execute_one_import(url, source, admin_id, overlay)
        print("\n--- EXECUTION RESULT ---")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        
        if result.get("draft_id"):
            db = SessionLocal()
            try:
                draft = draft_crud.get_by_id(db, result["draft_id"])
                if draft:
                    print("\n--- DRAFT CATEGORY DATA ---")
                    cat_data = {
                        "category": draft.product_data.get("category"),
                        "subcategory": draft.product_data.get("subcategory"),
                        "sub_subcategory": draft.product_data.get("sub_subcategory"),
                        "sizes": draft.product_data.get("sizes"),
                        "colors": draft.product_data.get("colors"),
                        "deepseek_warnings": draft.errors,
                        "product_info": draft.product_data.get("product_info"),
                        "vipomall_rows": draft.product_data.get("variants", {}).get("vipomall_rows")
                    }
                    print(json.dumps(cat_data, ensure_ascii=False, indent=2))
            finally:
                db.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
