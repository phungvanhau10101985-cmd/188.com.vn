/** Ném khi người dùng chưa đăng nhập cố thêm vào giỏ — UI bắt và chuyển sang /auth/login. */

export class CartRequiresLoginError extends Error {
  constructor(message = 'Vui lòng đăng nhập để thêm vào giỏ hàng') {
    super(message);
    this.name = 'CartRequiresLoginError';
  }
}

export function isCartRequiresLoginError(e: unknown): e is CartRequiresLoginError {
  return e instanceof CartRequiresLoginError;
}
