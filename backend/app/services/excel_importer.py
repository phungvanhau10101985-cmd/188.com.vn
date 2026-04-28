# backend/app/services/excel_importer.py - FIXED FOR 36-37 COLUMNS
import pandas as pd
from sqlalchemy.orm import Session
from typing import List, Dict, Any
import json
import logging
import os
import re
from datetime import datetime
import traceback

from app.crud.product import (
    excel_row_to_product,
    bulk_import_products,
    get_all_products_for_export,
    get_category_final_mappings,
    apply_category_final_mapping_to_product
)

logger = logging.getLogger(__name__)

class ExcelImporter:
    def __init__(self, db: Session):
        self.db = db
    
    def import_from_excel(self, file_path: str, overwrite: bool = False) -> Dict[str, Any]:
        """
        Import sản phẩm từ file Excel 36 cột A-AJ
        Slug được tự động tạo
        """
        try:
            logger.info(f"📥 BẮT ĐẦU IMPORT: {file_path}")
            
            if not os.path.exists(file_path):
                return {"error": f"File không tồn tại: {file_path}"}
            
            df = self._read_excel_with_detection(file_path)
            
            if df.empty:
                return {"error": "File Excel trống hoặc không có dữ liệu"}
            
            logger.info(f"✅ Đọc được {len(df)} dòng, {len(df.columns)} cột")
            
            df.columns = [str(col).strip() for col in df.columns]
            logger.info(f"📋 Các cột trong file: {list(df.columns)}")
            
            required_columns = ['id', 'name']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                logger.error(f"❌ Thiếu cột bắt buộc: {missing_columns}")
                return {"error": f"Thiếu cột bắt buộc: {missing_columns}"}
            
            products_data = []
            errors = []
            warnings = []
            
            mappings = get_category_final_mappings(self.db)

            for idx, row in df.iterrows():
                try:
                    row_number = idx + 2
                    row_dict = row.to_dict()
                    
                    if idx < 5:
                        logger.debug(f"📄 Dòng {row_number}: id={row_dict.get('id')}, name={row_dict.get('name', '')[:30]}...")
                    
                    product_dict = excel_row_to_product(row_dict)
                    product_dict = apply_category_final_mapping_to_product(product_dict, mappings)
                    
                    if product_dict and product_dict.get("product_id"):
                        products_data.append(product_dict)
                        
                        if idx < 10:
                            logger.info(f"✅ Dòng {row_number}: {product_dict.get('product_id')} - {product_dict.get('slug')}")
                    else:
                        error_msg = f"Dòng {row_number}: Không thể convert dữ liệu"
                        errors.append(error_msg)
                        logger.warning(error_msg)
                        
                except Exception as e:
                    error_msg = f"Dòng {idx + 2}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(f"❌ {error_msg}")
                    logger.error(traceback.format_exc())
            
            logger.info(f"📊 ĐÃ CHUẨN BỊ: {len(products_data)} sản phẩm hợp lệ, {len(errors)} lỗi")
            
            if products_data:
                logger.info("🔄 ĐANG IMPORT VÀO DATABASE...")
                result = bulk_import_products(self.db, products_data)
                
                all_errors = errors + result.get("errors", [])
                all_warnings = warnings + result.get("warnings", [])
                
                result["errors"] = all_errors
                result["warnings"] = all_warnings
                
                logger.info(f"📦 KẾT QUẢ IMPORT:")
                logger.info(f"   ➕ Tạo mới: {result.get('created', 0)}")
                logger.info(f"   🔄 Cập nhật: {result.get('updated', 0)}")
                logger.info(f"   ⚠️  Cảnh báo: {len(all_warnings)}")
                logger.info(f"   ❌ Lỗi: {len(all_errors)}")
                logger.info(f"   📈 Tỷ lệ thành công: {result.get('success_rate', '0%')}")
                
                return result
            else:
                return {
                    "error": "Không có dữ liệu hợp lệ để import",
                    "errors": errors,
                    "total_rows": len(df)
                }
                
        except Exception as e:
            logger.error(f"❌ LỖI IMPORT EXCEL: {str(e)}")
            logger.error(traceback.format_exc())
            return {"error": f"Lỗi import: {str(e)}"}
    
    def _read_excel_with_detection(self, file_path: str) -> pd.DataFrame:
        try:
            xls = pd.ExcelFile(file_path)
            sheet_name = xls.sheet_names[0] if xls.sheet_names else None
            
            methods = [
                self._try_read_method_1,
                self._try_read_method_2,
                self._try_read_method_3,
            ]
            
            for method in methods:
                df = method(file_path, sheet_name)
                if df is not None and not df.empty and self._is_valid_dataframe(df):
                    return df
            
            logger.warning("⚠️  Không phát hiện header rõ ràng, đọc raw data")
            return pd.read_excel(file_path, header=None)
            
        except Exception as e:
            logger.error(f"Lỗi đọc Excel: {e}")
            raise
    
    def _try_read_method_1(self, file_path: str, sheet_name: str = None) -> pd.DataFrame:
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name, header=0)
            if not df.empty and len(df.columns) >= 10:
                first_col = str(df.columns[0]).strip().lower() if len(df.columns) > 0 else ""
                if first_col in ['id', 'product_id', 'id sản phẩm']:
                    logger.info("✅ Phát hiện header tiếng Anh ở dòng 1")
                    return df
        except:
            pass
        return None
    
    def _try_read_method_2(self, file_path: str, sheet_name: str = None) -> pd.DataFrame:
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name, header=1)
            if not df.empty and len(df.columns) >= 10:
                first_col = str(df.columns[0]).strip().lower() if len(df.columns) > 0 else ""
                if any(keyword in first_col for keyword in ['id', 'mã', 'product', 'sản phẩm']):
                    logger.info("✅ Phát hiện header tiếng Việt ở dòng 2")
                    return df
        except:
            pass
        return None
    
    def _try_read_method_3(self, file_path: str, sheet_name: str = None) -> pd.DataFrame:
        try:
            df_raw = pd.read_excel(file_path, sheet_name=sheet_name, header=None, nrows=20)
            
            for i in range(len(df_raw)):
                first_cell = str(df_raw.iloc[i, 0]) if not pd.isna(df_raw.iloc[i, 0]) else ""
                
                if (first_cell.startswith('A') and 
                    len(first_cell) > 10 and 
                    ('188b' in first_cell.lower() or 'a188b' in first_cell.lower())):
                    logger.info(f"✅ Phát hiện dữ liệu bắt đầu ở dòng {i+1}")
                    return pd.read_excel(file_path, sheet_name=sheet_name, skiprows=i)
        except:
            pass
        return None
    
    def _is_valid_dataframe(self, df: pd.DataFrame) -> bool:
        if df.empty:
            return False
        
        if len(df.columns) < 20:
            return False
        
        non_empty_rows = df.dropna(how='all').shape[0]
        if non_empty_rows == 0:
            return False
        
        return True
    
    def export_to_excel(self, products: List[Dict] = None, filename: str = None) -> Dict[str, Any]:
        """
        Export sản phẩm ra file Excel với 37 cột A-AK (có Slug)
        """
        try:
            if not products:
                products = get_all_products_for_export(self.db)
            
            if not products:
                return {"error": "Không có sản phẩm để export", "filepath": None}
            
            logger.info(f"📤 BẮT ĐẦU EXPORT {len(products)} SẢN PHẨM...")
            
            df = pd.DataFrame(products)
            
            # 38 CỘT EXPORT ORDER (A-AL): ... Weight (AI), product_info (AK), Slug (AL)
            excel_columns_order = [
                'id', 'sku', 'origin', 'brand', 'name', 'pro_content',
                'price', 'shop_name', 'shop_id', 'pro_lower_price', 'pro_high_price',
                'rating_group_id', 'question_group_id', 'sizes', 'Variant',
                'gallery_images', 'detail_images', 'product_url', 'video_url',
                'main_image', 'likes_count', 'purchases_count', 'reviews_count',
                'questions_count', 'rating_score', 'stock_quantity', 'deposit_required',
                'Main Category', 'Subcategory', 'Sub-subcategory', 'Material',
                'Style', 'Color', 'Occasion', 'Features', 'Weight',
                'product_info',  # AK: Thông tin sản phẩm (JSON)
                'Slug'           # AL
            ]
            
            available_columns = [col for col in excel_columns_order if col in df.columns]
            
            if 'product_info' not in df.columns and 'product_info' in excel_columns_order:
                df['product_info'] = ''
                available_columns.append('product_info')
            if 'Slug' not in available_columns:
                logger.warning("⚠️  Không tìm thấy cột Slug trong dữ liệu, thêm cột trống")
                df['Slug'] = ''
                available_columns.append('Slug')
            
            df = df.reindex(columns=available_columns)
            
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"export_products_{timestamp}.xlsx"
            
            export_dir = os.path.join("app", "static", "uploads")
            os.makedirs(export_dir, exist_ok=True)
            filepath = os.path.join(export_dir, filename)
            
            vietnamese_headers = {
                'id': 'Id sản phẩm',
                'sku': 'Mã sản phẩm',
                'origin': 'Xuất xứ',
                'brand': 'Thương hiệu',
                'name': 'Tên',
                'pro_content': 'Mô tả sản phẩm',
                'price': 'Giá',
                'shop_name': 'Tên shop',
                'shop_id': 'Shop id',
                'pro_lower_price': 'Sp giá thấp hơn',
                'pro_high_price': 'Sp giá cao hơn',
                'rating_group_id': 'Nhóm đánh giá',
                'question_group_id': 'Nhóm câu hỏi',
                'sizes': 'Size',
                'Variant': 'Biến thể',
                'gallery_images': 'Thư viện ảnh',
                'detail_images': 'Nội dung',
                'product_url': 'Link mặc định',
                'video_url': 'Link Video',
                'main_image': 'Link img',
                'likes_count': 'Thích',
                'purchases_count': 'Mua',
                'reviews_count': 'Lượt đánh giá',
                'questions_count': 'Lượt hỏi',
                'rating_score': 'Điểm đánh giá',
                'stock_quantity': 'Số lượng có thể mua',
                'deposit_required': 'Cần đặt cọc',
                'Main Category': 'Danh mục cấp 1',
                'Subcategory': 'Danh mục cấp 2',
                'Sub-subcategory': 'Danh mục cấp 3',
                'Material': 'Chất liệu',
                'Style': 'Kiểu dáng',
                'Color': 'màu sắc',
                'Occasion': 'Dịp',
                'Features': 'Tính năng',
                'Weight': 'Trọng lượng',
                'product_info': 'Thông tin sản phẩm',
                'Slug': 'Slug'
            }
            
            with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Products', index=False, startrow=0)
                
                workbook = writer.book
                worksheet = writer.sheets['Products']
                
                for col_idx, col_name in enumerate(available_columns, 1):
                    viet_name = vietnamese_headers.get(col_name, col_name)
                    worksheet.cell(row=2, column=col_idx, value=viet_name)
                
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if cell.value:
                                cell_length = len(str(cell.value))
                                max_length = max(max_length, cell_length)
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 50)
                    worksheet.column_dimensions[column_letter].width = adjusted_width
            
            file_size = os.path.getsize(filepath)
            logger.info(f"✅ EXPORT THÀNH CÔNG: {filename}")
            logger.info(f"   📁 Đường dẫn: {filepath}")
            logger.info(f"   📏 Kích thước: {file_size:,} bytes")
            logger.info(f"   📊 Số cột: {len(available_columns)}")
            logger.info(f"   📈 Số dòng: {len(df) + 2}")
            
            return {
                "success": True,
                "filename": filename,
                "filepath": filepath,
                "download_url": f"/static/uploads/{filename}",
                "file_size": file_size,
                "columns": len(available_columns),
                "rows": len(df),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ LỖI EXPORT EXCEL: {e}")
            logger.error(traceback.format_exc())
            return {
                "error": f"Lỗi export: {str(e)}",
                "success": False
            }
    
    def create_sample_template(self) -> Dict[str, Any]:
        """
        Tạo file Excel mẫu với 37 cột (A-AK): ... Weight (AI), product_info (AK). Không có Slug (tự tạo khi import).
        """
        try:
            sample_product_info = json.dumps({
                "product_info": {"sku": "B0038", "name": "Giày Tây Oxford Nam", "brand": "SHTDC", "origin": "Việt Nam", "category": {"level_1": "Giày dép Nam", "level_2": "Giày tây Nam", "level_3": "Giày Oxford Nam"}},
                "specifications": {"upper_material": "Da bò", "lining_material": "Lót da", "outsole_material": "Cao su", "weight_grams": 500},
                "variants": {"colors": ["Đen", "Nâu"], "sizes": [38, 39, 40, 41, 42, 43, 44, 45]},
                "target_audience": {"gender": "Nam", "age_range": "18-40", "style": "Công sở"},
                "market_info": {"season": "Quanh năm", "lead_time_days": "1-3 ngày", "main_sales_regions": ["Việt Nam"]}
            }, ensure_ascii=False)
            sample_data = [{
                'id': 'A746204251298a188b0038',
                'sku': 'B0038',
                'origin': 'Việt Nam',
                'brand': 'SHTDC',
                'name': 'Giày Tây Oxford Nam Da Thật Mũi Nhọn Chiều Cao Đế Khoảng 3cm Màu Đen, Nâu',
                'pro_content': 'Giày Tây Oxford Nam Da Thật là một lựa chọn hoàn hảo thuộc dòng Giày dép Nam, đặc biệt là Giày tây Nam.',
                'price': 2260000,
                'shop_name': 'giày tây nam shtdc',
                'shop_id': 'nam G05',
                'pro_lower_price': 'giày dép nam G04',
                'pro_high_price': 'giày dép nam G06',
                'rating_group_id': 90,
                'question_group_id': 99,
                'sizes': '["37", "38", "39", "40", "41", "42", "43", "44", "45", "46"]',
                'Variant': '[{"name": "Màu đen", "img": "https://img.alicdn.com/img/ibank/O1CN01q0djJj2LWec6Kkpij_!!3577759700-0-cib.jpg"}, {"name": "Nâu cổ điển", "img": "https://img.alicdn.com/img/ibank/O1CN01bsGpk22LWecAoruAN_!!3577759700-0-cib.jpg"}]',
                'gallery_images': '["https://img.alicdn.com/img/ibank/O1CN017R3Bf62LWeizFVWog_!!3577759700-0-cib.jpg"]',
                'detail_images': '["https://188.com.vn/uploads/size-san-pham/size%20gi%C3%A0y%20nam.jpg"]',
                'product_url': 'https://188.com.vn/product/B0038',
                'video_url': 'https://cloud.video.taobao.com/play/u/3577759700/p/1/e/6/t/1/375400310804.mp4',
                'main_image': '//img.alicdn.com/img/ibank/O1CN017R3Bf62LWeizFVWog_!!3577759700-0-cib.jpg',
                'likes_count': 100,
                'purchases_count': 81,
                'reviews_count': 72,
                'questions_count': 90,
                'rating_score': 4.9,
                'stock_quantity': 500,
                'deposit_required': 1,
                'Main Category': 'Giày dép Nam',
                'Subcategory': 'Giày tây Nam',
                'Sub-subcategory': 'Giày Oxford Nam',
                'Material': 'Da bò',
                'Style': 'Dây buộc',
                'Color': 'Đen, Xanh',
                'Occasion': 'Lễ cưới, dự tiệc',
                'Features': 'Nâng đế, tăng cao',
                'Weight': '500g',
                'product_info': sample_product_info  # Cột AK
            }]
            
            df = pd.DataFrame(sample_data)
            
            template_dir = os.path.join("app", "static", "templates")
            os.makedirs(template_dir, exist_ok=True)
            filepath = os.path.join(template_dir, "sample_import_template.xlsx")
            
            with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Products', index=False, startrow=0)
                
                workbook = writer.book
                worksheet = writer.sheets['Products']
                
                # 37 cột import: A-AK (không Slug)
                vietnamese_headers = [
                    'Id sản phẩm', 'Mã sản phẩm', 'Xuất xứ', 'Thương hiệu', 'Tên',
                    'Mô tả sản phẩm', 'Giá', 'Tên shop', 'Shop id', 'Sp giá thấp hơn',
                    'Sp giá cao hơn', 'Nhóm đánh giá', 'Nhóm câu hỏi', 'Size',
                    'Biến thể', 'Thư viện ảnh', 'Nội dung', 'Link mặc định',
                    'Link Video', 'Link img', 'Thích', 'Mua', 'Lượt đánh giá',
                    'Lượt hỏi', 'Điểm đánh giá', 'Số lượng có thể mua', 'Cần đặt cọc',
                    'Danh mục cấp 1', 'Danh mục cấp 2', 'Danh mục cấp 3', 'Chất liệu',
                    'Kiểu dáng', 'màu sắc', 'Dịp', 'Tính năng', 'Trọng lượng',
                    'Thông tin sản phẩm'  # AK - JSON
                ]
                
                for col_idx, header in enumerate(vietnamese_headers, 1):
                    worksheet.cell(row=2, column=col_idx, value=header)
                
                # Adjust column widths
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if cell.value:
                                max_length = max(max_length, len(str(cell.value)))
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 50)
                    worksheet.column_dimensions[column_letter].width = adjusted_width
            
            logger.info(f"✅ Tạo template mẫu thành công: {filepath}")
            logger.info("📋 Cấu trúc: 37 cột (A-AK), cột AK = Thông tin sản phẩm (JSON). Slug tự tạo khi import.")
            
            return {
                "success": True,
                "filename": "sample_import_template.xlsx",
                "filepath": filepath,
                "download_url": "/static/templates/sample_import_template.xlsx",
                "note": "Template có 37 cột (A-AK). Cột AK = Thông tin sản phẩm (JSON). Slug tự tạo khi import."
            }
            
        except Exception as e:
            logger.error(f"❌ Lỗi tạo template: {e}")
            return {"error": f"Lỗi tạo template: {str(e)}", "success": False}