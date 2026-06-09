type ButtonSpinnerProps = {
  size?: 'xs' | 'sm' | 'md';
  className?: string;
};

const sizeClasses: Record<NonNullable<ButtonSpinnerProps['size']>, string> = {
  xs: 'h-3.5 w-3.5 border',
  sm: 'h-4 w-4 border-2',
  md: 'h-5 w-5 border-2',
};

export default function ButtonSpinner({ size = 'sm', className = '' }: ButtonSpinnerProps) {
  return (
    <span
      className={`inline-block shrink-0 animate-spin rounded-full border-current border-t-transparent ${sizeClasses[size]} ${className}`.trim()}
      aria-hidden
    />
  );
}
