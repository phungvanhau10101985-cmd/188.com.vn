# backend/app/services/zalo_otp_service.py - PRODUCTION VERSION
import requests
import logging
import json
import time
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from app.core.config import settings

logger = logging.getLogger(__name__)

# Singleton instance
_zalo_otp_instance = None

class ZaloOTPService:
    def __new__(cls):
        global _zalo_otp_instance
        if _zalo_otp_instance is None:
            _zalo_otp_instance = super(ZaloOTPService, cls).__new__(cls)
            _zalo_otp_instance._initialized = False
        return _zalo_otp_instance

    def __init__(self):
        # Chỉ khởi tạo một lần
        if getattr(self, '_initialized', False):
            return
            
        self._initialized = True
        self.base_url = settings.ZALO_API_BASE_URL
        self.access_token = settings.ZALO_OA_ACCESS_TOKEN
        self.oa_id = settings.ZALO_OA_ID
        self.app_secret = settings.ZALO_OA_SECRET
        
        # Template IDs - DÙNG TEMPLATE THẬT 303744
        self.templates = {
            "register": settings.ZALO_TEMPLATE_REGISTER or "303744",
            "reset_password": settings.ZALO_TEMPLATE_RESET_PASSWORD or "303744",
            "verify_phone": settings.ZALO_TEMPLATE_VERIFY_PHONE or "303744",
            "login": settings.ZALO_TEMPLATE_LOGIN or "303744",
        }
        
        # Cache để tránh gọi API nhiều lần
        self._oa_info_cache = None
        self._cache_expiry = None
        
        logger.info(f"✅ Zalo OTP Service initialized. OA ID: {self.oa_id}, Template: 303744")
        
    def _refresh_access_token_if_needed(self) -> bool:
        """Refresh access token nếu cần (token có hạn 1 tháng)"""
        # Zalo access token có hạn 1 tháng, cần refresh định kỳ
        # Trong thực tế nên implement refresh logic
        return True
    
    def is_production_ready(self) -> bool:
        """Kiểm tra service có sẵn sàng cho production không"""
        # Kiểm tra access token hợp lệ
        if not self.access_token or len(self.access_token) < 100:
            logger.warning("Zalo access token too short")
            return False
        
        # Kiểm tra OA ID
        if not self.oa_id or len(self.oa_id) < 5:
            logger.warning("Zalo OA ID invalid")
            return False
            
        # Kiểm tra app secret
        if not self.app_secret or len(self.app_secret) < 10:
            logger.warning("Zalo app secret invalid")
            return False
            
        return True
    
    def get_oa_info(self, force_refresh: bool = False) -> Optional[Dict]:
        """Lấy thông tin OA từ Zalo API"""
        if not force_refresh and self._oa_info_cache and self._cache_expiry and datetime.now() < self._cache_expiry:
            return self._oa_info_cache
        
        try:
            headers = {"access_token": self.access_token}
            response = requests.get(
                f"{self.base_url}/getoa",
                headers=headers,
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("error") == 0:
                    self._oa_info_cache = data.get("data", {})
                    self._cache_expiry = datetime.now() + timedelta(minutes=30)  # Cache 30 phút
                    return self._oa_info_cache
                else:
                    logger.error(f"Zalo OA info error: {data.get('message')}")
            else:
                logger.error(f"Zalo OA info HTTP error: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Failed to get OA info: {str(e)}")
        
        return None
    
    def check_health(self) -> bool:
        """Kiểm tra kết nối Zalo API"""
        if not self.is_production_ready():
            logger.warning("Zalo not configured for production")
            return False
        
        oa_info = self.get_oa_info()
        if oa_info:
            logger.info(f"✅ Zalo OA healthy: {oa_info.get('name', 'Unknown')} - {oa_info.get('followers', 0)} followers")
            return True
        else:
            logger.error("❌ Zalo OA not healthy")
            return False
    
    def _format_phone_number(self, phone: str) -> str:
        """Format số điện thoại cho Zalo (E.164 format)"""
        phone = str(phone).strip()
        
        # Xóa khoảng trắng và ký tự đặc biệt
        import re
        phone = re.sub(r'[^\d+]', '', phone)
        
        # Chuyển đổi định dạng Việt Nam
        if phone.startswith('0'):
            return '+84' + phone[1:]
        elif phone.startswith('84'):
            return '+' + phone
        elif not phone.startswith('+'):
            return '+84' + phone
        
        return phone
    
    def check_user_follow_status(self, phone: str) -> Dict[str, Any]:
        """Kiểm tra user có follow OA chưa"""
        try:
            formatted_phone = self._format_phone_number(phone)
            
            headers = {"access_token": self.access_token}
            payload = {"user_id": formatted_phone}
            
            response = requests.post(
                f"{self.base_url}/getprofile",
                headers=headers,
                json=payload,
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                error_code = data.get("error", -1)
                
                if error_code == 0:
                    is_follower = data.get("data", {}).get("is_follow", False)
                    user_id = data.get("data", {}).get("user_id", "")
                    
                    return {
                        "success": True,
                        "is_follower": is_follower,
                        "user_id": user_id,
                        "can_send_message": is_follower,
                        "error_code": error_code
                    }
                else:
                    # User chưa từng tương tác với OA
                    return {
                        "success": False,
                        "is_follower": False,
                        "user_id": "",
                        "can_send_message": False,
                        "error_code": error_code,
                        "message": data.get("message", "User not found or never interacted")
                    }
            else:
                return {
                    "success": False,
                    "error": f"HTTP error: {response.status_code}",
                    "is_follower": False,
                    "can_send_message": False
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "is_follower": False,
                "can_send_message": False
            }
    
    def send_otp(self, phone: str, otp_code: str, purpose: str = "register") -> Dict[str, Any]:
        """
        GỬI OTP QUA ZALO OA - PRODUCTION VERSION
        Sử dụng template thật 303744
        """
        print("\n" + "="*60)
        print("🔢 PRODUCTION ZALO OTP FLOW")
        print("="*60)
        print(f"📱 Phone: {phone}")
        print(f"🔢 OTP Code: {otp_code}")
        print(f"🎯 Purpose: {purpose}")
        print(f"⏱️  Valid for: {settings.OTP_EXPIRE_MINUTES} minutes")
        print(f"🆔 Template ID: 303744")
        print("="*60)
        
        logger.info(f"🔄 Zalo OTP request for {phone}, purpose: {purpose}, OTP: {otp_code}")
        
        # Kiểm tra production readiness
        if not self.is_production_ready():
            logger.error("❌ Zalo not production ready")
            return self._simulate_send_otp(phone, otp_code, purpose)
        
        try:
            formatted_phone = self._format_phone_number(phone)
            
            # Kiểm tra user có follow OA không
            follow_status = self.check_user_follow_status(phone)
            
            if not follow_status.get("success"):
                logger.warning(f"⚠️ Cannot check follow status for {phone}: {follow_status.get('error')}")
                # Vẫn thử gửi, không block
                
            if follow_status.get("is_follower"):
                logger.info(f"✅ User {phone} is following OA")
            else:
                logger.warning(f"⚠️ User {phone} not following OA, error code: {follow_status.get('error_code')}")
                # Zalo vẫn có thể gửi tin nhắn template cho user không follow
                # nhưng cần user đã từng tương tác với OA
            
            # Lấy template ID
            template_id = self.templates.get(purpose, self.templates["register"])
            
            headers = {
                "access_token": self.access_token,
                "Content-Type": "application/json"
            }
            
            # Tạo payload theo template 303744
            payload = self._create_zalo_payload(formatted_phone, otp_code, template_id, purpose)
            
            logger.info(f"📤 Sending Zalo OTP to {formatted_phone}, template: {template_id}")
            logger.debug(f"Zalo payload: {json.dumps(payload, ensure_ascii=False)}")
            
            # Gửi request đến Zalo API
            start_time = time.time()
            response = requests.post(
                f"{self.base_url}/message/template",
                headers=headers,
                json=payload,
                timeout=10
            )
            response_time = time.time() - start_time
            
            # Xử lý response
            response_data = {}
            try:
                response_data = response.json()
            except:
                response_data = {"raw_text": response.text}
            
            logger.info(f"📥 Zalo response in {response_time:.2f}s: HTTP {response.status_code}")
            
            if response.status_code == 200:
                if response_data.get("error") == 0:
                    # THÀNH CÔNG: OTP đã gửi qua Zalo
                    message_id = response_data.get("data", {}).get("message_id", "")
                    
                    print(f"\n✅ ZALO OTP SENT SUCCESSFULLY!")
                    print(f"   📱 To: {phone}")
                    print(f"   📨 Message ID: {message_id}")
                    print(f"   ⚡ Response time: {response_time:.2f}s")
                    print(f"   📝 User should receive OTP via Zalo app")
                    
                    logger.info(f"✅ Zalo OTP sent successfully to {phone}, message_id: {message_id}")
                    
                    return {
                        "success": True,
                        "provider": "zalo",
                        "message": "OTP đã được gửi qua Zalo",
                        "phone": phone,
                        "formatted_phone": formatted_phone,
                        "message_id": message_id,
                        "template_used": template_id,
                        "otp_code": otp_code,  # Vẫn trả về để debug
                        "simulated": False,
                        "zalo_sent": True,
                        "response_time": response_time,
                        "requires_zalo_app": True,
                        "note": "Check Zalo app for OTP message"
                    }
                else:
                    # Zalo API lỗi
                    error_code = response_data.get("error", -1)
                    error_msg = response_data.get("message", "Unknown Zalo error")
                    
                    print(f"\n❌ ZALO API ERROR: {error_msg} (Code: {error_code})")
                    
                    logger.error(f"Zalo API error {error_code}: {error_msg}")
                    
                    # Phân tích lỗi phổ biến
                    error_analysis = self._analyze_zalo_error(error_code, error_msg)
                    
                    return {
                        "success": False,
                        "provider": "zalo",
                        "message": f"Zalo error: {error_msg}",
                        "phone": phone,
                        "otp_code": otp_code,
                        "error_code": error_code,
                        "error_message": error_msg,
                        "error_analysis": error_analysis,
                        "simulated": False,
                        "zalo_sent": False,
                        "response_time": response_time
                    }
            else:
                # HTTP lỗi
                error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                
                print(f"\n❌ HTTP ERROR: {response.status_code}")
                print(f"   Response: {response.text[:200]}")
                
                logger.error(f"Zalo HTTP error {response.status_code}: {response.text}")
                
                return {
                    "success": False,
                    "provider": "zalo",
                    "message": f"Không kết nối được đến Zalo: {response.status_code}",
                    "phone": phone,
                    "otp_code": otp_code,
                    "error": error_msg,
                    "simulated": False,
                    "zalo_sent": False,
                    "response_time": response_time
                }
                
        except requests.exceptions.Timeout:
            logger.error(f"Zalo API timeout for {phone}")
            return {
                "success": False,
                "provider": "zalo",
                "message": "Zalo API timeout, vui lòng thử lại",
                "phone": phone,
                "otp_code": otp_code,
                "error": "timeout",
                "simulated": False,
                "zalo_sent": False
            }
        except Exception as e:
            logger.error(f"Zalo OTP exception: {str(e)}", exc_info=True)
            return {
                "success": False,
                "provider": "zalo",
                "message": f"Lỗi hệ thống Zalo: {str(e)[:100]}",
                "phone": phone,
                "otp_code": otp_code,
                "error": str(e),
                "simulated": False,
                "zalo_sent": False
            }
    
    def _create_zalo_payload(self, phone: str, otp_code: str, template_id: str, purpose: str) -> Dict:
        """Tạo payload cho Zalo template message - FIXED cho template 303744"""
        
        # Template 303744 có thể có các variables:
        # otp_code, expire_minutes, app_name, purpose, time
        # Kiểm tra trong Zalo Console để biết chính xác
        
        payload = {
            "phone": phone,
            "template_id": template_id,
            "template_data": {
                "otp_code": otp_code,  # Biến chính: mã OTP
                "expire_minutes": str(settings.OTP_EXPIRE_MINUTES),  # Thời gian hiệu lực
                "app_name": settings.PROJECT_NAME,  # Tên ứng dụng
                "purpose": self._get_purpose_vietnamese(purpose),  # Mục đích tiếng Việt
                "time": datetime.now().strftime("%H:%M %d/%m/%Y")  # Thời gian gửi
            },
            "tracking_id": f"{purpose}_{phone}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        }
        
        return payload
    
    def _get_purpose_vietnamese(self, purpose: str) -> str:
        """Chuyển mục đích sang tiếng Việt"""
        purposes = {
            "register": "đăng ký tài khoản",
            "reset_password": "khôi phục mật khẩu",
            "verify_phone": "xác thực số điện thoại",
            "login": "đăng nhập"
        }
        return purposes.get(purpose, "xác thực")
    
    def _analyze_zalo_error(self, error_code: int, error_msg: str) -> Dict[str, str]:
        """Phân tích lỗi Zalo và đề xuất giải pháp"""
        error_analysis = {
            "error_code": error_code,
            "error_message": error_msg,
            "possible_causes": [],
            "solutions": []
        }
        
        # Phân tích lỗi phổ biến
        if error_code == -201:  # Invalid template
            error_analysis["possible_causes"].append("Template ID không hợp lệ")
            error_analysis["possible_causes"].append("Template chưa được duyệt")
            error_analysis["solutions"].append("Kiểm tra Template ID trong Zalo Console")
            error_analysis["solutions"].append("Đảm bảo template đã được approved")
        
        elif error_code == -213:  # User not follower
            error_analysis["possible_causes"].append("Người dùng chưa follow OA")
            error_analysis["possible_causes"].append("User chưa từng tương tác với OA")
            error_analysis["solutions"].append("Yêu cầu user follow OA trước")
            error_analysis["solutions"].append("User cần gửi tin nhắn cho OA ít nhất 1 lần")
        
        elif error_code == -124:  # Invalid phone
            error_analysis["possible_causes"].append("Số điện thoại không hợp lệ")
            error_analysis["possible_causes"].append("Số điện thoại chưa đăng ký Zalo")
            error_analysis["solutions"].append("Kiểm tra định dạng số điện thoại")
            error_analysis["solutions"].append("Đảm bảo số điện thoại đã đăng ký Zalo")
        
        elif error_code == -401:  # Invalid access token
            error_analysis["possible_causes"].append("Access token hết hạn")
            error_analysis["possible_causes"].append("Access token không hợp lệ")
            error_analysis["solutions"].append("Refresh access token trong Zalo Console")
            error_analysis["solutions"].append("Tạo access token mới")
        
        else:
            error_analysis["possible_causes"].append("Lỗi không xác định từ Zalo")
            error_analysis["solutions"].append("Kiểm tra Zalo Developer Console")
            error_analysis["solutions"].append("Xem tài liệu: https://developers.zalo.me/docs/api/official-account-api/tin-nhan-mau/post-tin-nhan-mau")
        
        return error_analysis
    
    def _simulate_send_otp(self, phone: str, otp_code: str, purpose: str) -> Dict[str, Any]:
        """Simulation mode cho development"""
        logger.info(f"SIMULATION - Zalo OTP for {phone}: {otp_code}")
        
        print(f"\n🎭 ZALO OTP SIMULATION MODE (Production not ready):")
        print(f"   📱 Phone: {phone}")
        print(f"   🔢 OTP: {otp_code}")
        print(f"   🎯 Purpose: {purpose}")
        print(f"   ⏱️  Expire: {settings.OTP_EXPIRE_MINUTES} minutes")
        print(f"   💡 Note: System in simulation mode")
        
        return {
            "success": True,
            "provider": "zalo_simulation",
            "message": "OTP simulation mode - configure for production",
            "phone": phone,
            "otp_code": otp_code,
            "expire_minutes": settings.OTP_EXPIRE_MINUTES,
            "simulated": True,
            "zalo_sent": False,
            "note": "Need valid Zalo OA config for production"
        }
    
    def get_service_info(self) -> Dict[str, Any]:
        """Lấy thông tin service"""
        oa_info = self.get_oa_info()
        
        return {
            "oa_id": self.oa_id,
            "base_url": self.base_url,
            "templates": self.templates,
            "production_ready": self.is_production_ready(),
            "healthy": self.check_health(),
            "token_length": len(self.access_token) if self.access_token else 0,
            "oa_info": oa_info,
            "current_template": "303744"
        }

# Helper functions
def get_zalo_otp_service():
    """Get Zalo OTP service singleton"""
    global _zalo_otp_instance
    if _zalo_otp_instance is None:
        _zalo_otp_instance = ZaloOTPService()
    return _zalo_otp_instance

def test_zalo_production():
    """Test Zalo service in production mode"""
    print("🔥 TESTING ZALO OTP PRODUCTION")
    print("=" * 60)
    
    service = ZaloOTPService()
    
    info = service.get_service_info()
    print(f"🔧 CONFIGURATION:")
    print(f"   OA ID: {info['oa_id']}")
    print(f"   Production ready: {info['production_ready']}")
    print(f"   Healthy: {info['healthy']}")
    print(f"   Token length: {info['token_length']}")
    print(f"   Current template: {info['current_template']}")
    
    if info['oa_info']:
        print(f"\n📊 OA INFORMATION:")
        print(f"   Name: {info['oa_info'].get('name')}")
        print(f"   Followers: {info['oa_info'].get('followers')}")
        print(f"   Avatar: {info['oa_info'].get('avatar')}")
    
    # Test send OTP
    print(f"\n📤 TEST SEND PRODUCTION OTP:")
    result = service.send_otp("0983244395", "999888", "register")
    
    print(f"\n📋 RESULT:")
    print(f"   Success: {result['success']}")
    print(f"   Provider: {result['provider']}")
    print(f"   Message: {result['message']}")
    print(f"   Simulated: {result.get('simulated', False)}")
    print(f"   Zalo Sent: {result.get('zalo_sent', False)}")
    
    if 'error_code' in result:
        print(f"   Error Code: {result['error_code']}")
        print(f"   Error Message: {result.get('error_message')}")
        
        if 'error_analysis' in result:
            print(f"\n🔍 ERROR ANALYSIS:")
            analysis = result['error_analysis']
            print(f"   Possible causes: {', '.join(analysis.get('possible_causes', []))}")
            print(f"   Solutions: {', '.join(analysis.get('solutions', []))}")
    
    if 'otp_code' in result:
        print(f"\n🔢 OTP CODE (for testing): {result['otp_code']}")
    
    return result

if __name__ == "__main__":
    test_zalo_production()