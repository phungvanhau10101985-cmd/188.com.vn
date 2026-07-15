'use client';

import { usePathname } from 'next/navigation';
import AdminLayout from '@/components/admin/AdminLayout';
import AdminDestructiveStepUpProvider from '@/components/admin/AdminDestructiveStepUpProvider';

export default function AdminRouteLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  if (pathname === '/admin/login') {
    return <>{children}</>;
  }
  return (
    <AdminDestructiveStepUpProvider>
      <AdminLayout>{children}</AdminLayout>
    </AdminDestructiveStepUpProvider>
  );
}
