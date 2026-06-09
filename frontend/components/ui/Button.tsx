'use client';

import type { ButtonHTMLAttributes, ReactNode } from 'react';
import ButtonSpinner from './ButtonSpinner';

type ButtonVariant = 'primary' | 'secondary' | 'outline' | 'ghost';
type ButtonSize = 'default' | 'sm' | 'inline';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  loading?: boolean;
  variant?: ButtonVariant;
  size?: ButtonSize;
  spinnerPosition?: 'start' | 'end';
  children: ReactNode;
};

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    'bg-[#ea580c] text-white hover:bg-[#c2410c] border border-transparent shadow-sm disabled:opacity-60',
  secondary:
    'bg-gray-600 text-white hover:bg-gray-700 border border-transparent disabled:opacity-60',
  outline:
    'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50 disabled:opacity-60',
  ghost: 'bg-transparent text-[#ea580c] hover:bg-orange-50 disabled:opacity-60',
};

const sizeClasses: Record<ButtonSize, string> = {
  default: 'min-h-[44px] px-4 py-2 text-sm',
  sm: 'min-h-[36px] px-3 py-1.5 text-xs',
  inline: 'min-h-0 h-auto px-0 py-0 text-sm',
};

export default function Button({
  loading = false,
  disabled,
  variant = 'outline',
  size = 'default',
  spinnerPosition = 'start',
  className = '',
  children,
  type = 'button',
  ...props
}: ButtonProps) {
  const isDisabled = disabled || loading;

  return (
    <button
      type={type}
      disabled={isDisabled}
      data-loading={loading ? 'true' : undefined}
      aria-busy={loading || undefined}
      className={`btn-interactive inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors disabled:cursor-not-allowed ${variantClasses[variant]} ${sizeClasses[size]} ${className}`.trim()}
      {...props}
    >
      {loading && spinnerPosition === 'start' ? <ButtonSpinner size="sm" /> : null}
      <span className={loading ? 'inline-flex items-center gap-2' : undefined}>{children}</span>
      {loading && spinnerPosition === 'end' ? <ButtonSpinner size="sm" /> : null}
    </button>
  );
}
