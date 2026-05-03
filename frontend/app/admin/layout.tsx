'use client';

import { usePathname } from 'next/navigation';
import AdminLayout from '@/components/admin/AdminLayout';

export default function AdminRouteLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  if (pathname === '/admin/login') {
    return <>{children}</>;
  }
  return <AdminLayout>{children}</AdminLayout>;
}
