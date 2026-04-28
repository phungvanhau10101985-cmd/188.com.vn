## HƯỚNG DẪN KIỂM TRA GIỎ HÀNG

### 🎯 CÁC TÍNH NĂNG ĐÃ SỬA:

1. **Xử lý chưa đăng nhập:**
   - Khi user chưa login bấm "Thêm vào giỏ" → Hiện popup yêu cầu đăng nhập
   - Có thể chọn OK để chuyển đến trang login hoặc Cancel để hủy

2. **Tích hợp cart hook mới:**
   - Sử dụng useCart() thay vì apiClient.addToCart() cũ
   - Hiển thị trạng thái loading khi đang thêm vào giỏ
   - Xử lý lỗi authentication đúng cách

3. **Thông báo rõ ràng:**
   - Thông báo thành công khi thêm vào giỏ
   - Thông báo lỗi cụ thể khi có vấn đề
   - Xử lý token hết hạn

### 🔧 CÁCH KIỂM TRA:

**Test Case 1: User chưa đăng nhập**
1. Truy cập trang sản phẩm (chưa login)
2. Bấm "Thêm vào giỏ hàng"
3. → Hiện popup "Bạn cần đăng nhập..."
4. Bấm OK → Chuyển đến trang login
5. Bấm Cancel → Ở lại trang sản phẩm

**Test Case 2: User đã đăng nhập**
1. Đăng nhập trước
2. Truy cập trang sản phẩm  
3. Bấm "Thêm vào giỏ hàng"
4. → Hiện thông báo thành công
5. Kiểm tra số lượng giỏ hàng trong header tăng lên

**Test Case 3: Token hết hạn**
1. Xóa token trong localStorage
2. Thử thêm vào giỏ hàng
3. → Hiện popup yêu cầu đăng nhập lại

### 📁 FILE ĐÃ SỬA:
- frontend/app/products/[slug]/page.tsx
- frontend/components/product-detail/ProductInfo.tsx (nếu có)

🚀 Hệ thống giỏ hàng đã hoạt động hoàn chỉnh!