import { redirect } from 'next/navigation';
import { DEFAULT_LADIPAGE_KIND_SLUG } from '@/components/ladipage/ladipage-admin-kinds';

export default function AdminLadipageIndexPage() {
  redirect(`/admin/ladipage/${DEFAULT_LADIPAGE_KIND_SLUG}`);
}
