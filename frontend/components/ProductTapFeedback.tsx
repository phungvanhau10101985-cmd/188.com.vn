'use client';

import { useEffect } from 'react';
import { installProductTapFeedback } from '@/lib/product-tap-feedback';

/** Lắng nghe bấm sản phẩm trên toàn site (iOS và Android). */
export default function ProductTapFeedback() {
  useEffect(() => installProductTapFeedback(), []);
  return null;
}
