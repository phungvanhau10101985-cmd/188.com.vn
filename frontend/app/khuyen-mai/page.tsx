import { redirect } from 'next/navigation';

/** URL cũ — chuyển vào mục Tài khoản */
export default function KhuyenMaiRedirectPage() {
  redirect('/account/khuyen-mai');
}
