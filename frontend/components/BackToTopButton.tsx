// frontend/components/BackToTopButton.tsx
'use client';

import { useEffect, useState } from 'react';

export default function BackToTopButton() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const onScroll = () => {
      setVisible(window.scrollY > 400);
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  if (!visible) return null;

  return (
    <button
      type="button"
      data-188-skip-draggable
      onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
      aria-label="Lên đầu trang"
      className="fixed bottom-24 right-6 z-50 inline-flex h-11 w-11 items-center justify-center rounded-full bg-[#ea580c] text-white shadow-lg hover:bg-[#c2410c] transition-colors"
    >
      ↑
    </button>
  );
}
