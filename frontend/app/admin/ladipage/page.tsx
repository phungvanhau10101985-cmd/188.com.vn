import { redirect } from 'next/navigation';
import { DEFAULT_LADIPAGE_KIND_SLUG, ladipageListHref } from '@/components/ladipage/ladipage-admin-kinds';

export default function AdminLadipageIndexPage() {
  redirect(ladipageListHref(DEFAULT_LADIPAGE_KIND_SLUG));
}
