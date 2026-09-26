'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { isAdminBrowserHost } from '@/lib/admin-origin';

/** Link về shop. Trên admin host, `/` bị proxy sang `/admin` nên phải ra 188.com.vn. Không tự redirect. */
export default function NotFoundHomeLink() {
  const [homeHref, setHomeHref] = useState('/');

  useEffect(() => {
    if (isAdminBrowserHost()) setHomeHref('https://188.com.vn/');
  }, []);

  if (homeHref.startsWith('http')) {
    return (
      <a href={homeHref} className="text-[#ea580c] font-semibold hover:underline">
        Về trang chủ
      </a>
    );
  }

  return (
    <Link href={homeHref} className="text-[#ea580c] font-semibold hover:underline">
      Về trang chủ
    </Link>
  );
}
