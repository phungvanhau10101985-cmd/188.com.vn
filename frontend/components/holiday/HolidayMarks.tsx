'use client';

import type { HolidayLook } from '@/lib/holiday-themes';

type Tone = 'light' | 'dark';

function colors(look: HolidayLook, tone: Tone) {
  return tone === 'dark'
    ? { ink: look.goldSoft, accent: look.gold }
    : { ink: look.strong, accent: look.gold };
}

export function HolidayMark({
  look,
  tone = 'light',
  className = 'h-8 w-8 shrink-0',
}: {
  look: HolidayLook;
  tone?: Tone;
  className?: string;
}) {
  const { ink, accent } = colors(look, tone);
  const common = { className, viewBox: '0 0 64 64', 'aria-hidden': true as const };
  switch (look.id) {
    case 'duong-lich':
      return (
        <svg {...common}>
          <circle cx="32" cy="32" r="18" fill="none" stroke={ink} strokeWidth="2.4" />
          <path d="M32 18v16l10 6" fill="none" stroke={accent} strokeWidth="2.4" strokeLinecap="round" />
          <circle cx="32" cy="32" r="3" fill={accent} />
        </svg>
      );
    case 'tao-quan':
      return (
        <svg {...common}>
          <path d="M32 10c8 10 14 16 14 26a14 14 0 0 1-28 0c0-10 6-16 14-26z" fill={accent} />
          <path d="M32 24c4 6 7 9 7 14a7 7 0 0 1-14 0c0-5 3-8 7-14z" fill={ink} />
        </svg>
      );
    case 'tet':
      return (
        <svg {...common}>
          <g fill={accent}>
            <ellipse cx="32" cy="14" rx="6" ry="9" />
            <ellipse cx="32" cy="50" rx="6" ry="9" />
            <ellipse cx="16" cy="32" rx="9" ry="6" />
            <ellipse cx="48" cy="32" rx="9" ry="6" />
          </g>
          <circle cx="32" cy="32" r="6" fill={ink} />
        </svg>
      );
    case 'valentine':
      return (
        <svg {...common}>
          <path d="M32 52C16 40 10 30 16 22c4-5 10-4 16 2 6-6 12-7 16-2 6 8 0 18-16 30z" fill={accent} stroke={ink} strokeWidth="1.5" />
        </svg>
      );
    case 'nguyen-tieu':
      return (
        <svg {...common}>
          <path d="M22 14h20l-3 28H25z" fill={accent} />
          <path d="M24 22h16M23 30h18" stroke={ink} strokeWidth="1.6" />
          <circle cx="32" cy="50" r="2.2" fill={ink} />
        </svg>
      );
    case 'phu-nu-83':
      return (
        <svg {...common}>
          <circle cx="32" cy="28" r="8" fill={accent} />
          <circle cx="18" cy="36" r="7" fill={ink} />
          <circle cx="46" cy="36" r="7" fill={ink} />
          <circle cx="24" cy="48" r="6" fill={accent} />
          <circle cx="40" cy="48" r="6" fill={accent} />
        </svg>
      );
    case 'gio-to':
      return (
        <svg {...common}>
          <path d="M20 46h24l-3 8H23z" fill={ink} />
          <path d="M32 12c6 8 8 14 4 22h-8c-4-8-2-14 4-22z" fill={accent} />
          <path d="M28 34h8" stroke={ink} strokeWidth="2" />
        </svg>
      );
    case 'dai-le':
      return (
        <svg {...common}>
          <path d="M16 14h6v36h-6z" fill={ink} />
          <path d="M22 16h26v16H22z" fill={accent} />
          <circle cx="35" cy="24" r="4" fill={ink} />
        </svg>
      );
    case 'thieu-nhi':
      return (
        <svg {...common}>
          <ellipse cx="32" cy="26" rx="12" ry="14" fill={accent} />
          <path d="M32 40v12" stroke={ink} strokeWidth="2" />
          <path d="M24 50c4 3 12 3 16 0" fill="none" stroke={ink} strokeWidth="2" />
        </svg>
      );
    case 'doan-ngo':
      return (
        <svg {...common}>
          <path d="M32 12c10 8 16 16 12 28-8 2-16 2-24 0C16 28 22 20 32 12z" fill={accent} />
          <path d="M32 18v28" stroke={ink} strokeWidth="1.6" />
        </svg>
      );
    case 'vu-lan':
      return (
        <svg {...common}>
          <path d="M32 46c-12-8-16-16-10-24 6 6 10 6 10 6s4 0 10-6c6 8 2 16-10 24z" fill={accent} />
          <path d="M32 28c-8-10-6-18 0-22 6 4 8 12 0 22z" fill={ink} />
        </svg>
      );
    case 'quoc-khanh':
      return (
        <svg {...common}>
          <circle cx="32" cy="32" r="16" fill="none" stroke={ink} strokeWidth="2.4" />
          <path d="M32 18l3.2 8h8l-6.4 5 2.4 8L32 34l-7.2 5 2.4-8-6.4-5h8z" fill={accent} />
        </svg>
      );
    case 'trung-thu':
      return (
        <svg {...common}>
          <circle cx="30" cy="32" r="14" fill={accent} />
          <circle cx="38" cy="28" r="12" fill={tone === 'dark' ? look.dark : look.paper} />
          <circle cx="24" cy="30" r="2" fill={ink} />
        </svg>
      );
    case 'phu-nu-2010':
      return (
        <svg {...common}>
          <path d="M32 50V28" stroke={ink} strokeWidth="2" />
          <circle cx="32" cy="22" r="8" fill={accent} />
          <path d="M20 34c6 4 18 4 24 0" fill="none" stroke={accent} strokeWidth="2.4" />
        </svg>
      );
    case 'nha-giao':
      return (
        <svg {...common}>
          <path d="M10 28l22-10 22 10-22 10z" fill={accent} />
          <path d="M20 32v10c6 4 18 4 24 0V32" fill="none" stroke={ink} strokeWidth="2" />
          <path d="M54 28v14" stroke={ink} strokeWidth="2" />
        </svg>
      );
    case 'giang-sinh':
      return (
        <svg {...common}>
          <path d="M32 10l8 14h-5l8 12h-6l8 14H19l8-14h-6l8-12h-5z" fill={accent} />
          <rect x="28" y="50" width="8" height="6" fill={ink} />
        </svg>
      );
    default:
      return <span className={className} style={{ background: accent }} aria-hidden />;
  }
}
