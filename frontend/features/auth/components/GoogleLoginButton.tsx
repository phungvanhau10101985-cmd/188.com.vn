'use client';

import { useEffect, useRef } from 'react';

interface GoogleLoginButtonProps {
  onCredential: (idToken: string) => void;
  onError?: (message: string) => void;
}

declare global {
  interface Window {
    google?: any;
  }
}

export default function GoogleLoginButton({ onCredential, onError }: GoogleLoginButtonProps) {
  const buttonRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID?.trim();
    if (!clientId) {
      onError?.(
        'Thiếu NEXT_PUBLIC_GOOGLE_CLIENT_ID ở frontend (.env.local). Phải cùng giá trị với GOOGLE_CLIENT_ID trên backend — sau đó khởi động lại Next.',
      );
      return;
    }

    const initialize = () => {
      if (!window.google || !buttonRef.current) return;
      window.google.accounts.id.initialize({
        client_id: clientId,
        callback: (response: { credential?: string }) => {
          if (!response.credential) {
            onError?.('Không nhận được token từ Google.');
            return;
          }
          onCredential(response.credential);
        },
      });
      window.google.accounts.id.renderButton(buttonRef.current, {
        theme: 'outline',
        size: 'large',
        width: 360,
        text: 'signin_with',
        shape: 'rectangular',
      });
    };

    if (window.google) {
      initialize();
      return;
    }

    const failFinal = () =>
      onError?.(
        'Không tải được script Google. Thử mạng khác / tắt VPN–AdBlock; với ngrok thêm URL site vào Authorized JavaScript origins (OAuth Web client).'
      );

    const loadScript = (isRetry: boolean) => {
      const script = document.createElement('script');
      script.src = `https://accounts.google.com/gsi/client${isRetry ? `?retry=${Date.now()}` : ''}`;
      script.async = true;
      script.defer = true;
      script.onload = initialize;
      script.onerror = () => {
        if (!isRetry) {
          window.setTimeout(() => loadScript(true), 1500);
          return;
        }
        failFinal();
      };
      document.body.appendChild(script);
    };

    loadScript(false);
  }, [onCredential, onError]);

  return <div ref={buttonRef} className="flex justify-center" />;
}
