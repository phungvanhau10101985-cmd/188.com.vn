import { redirect } from 'next/navigation';

/** `/admin` không có page thì Next 404 + header shop; logo `/` trên admin host bị kẹt vòng 404. */
export default function AdminIndexPage() {
  redirect('/admin/orders');
}
