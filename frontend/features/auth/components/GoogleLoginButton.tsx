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
    const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
    if (!clientId) {
      onError?.('Thiếu GOOGLE_CLIENT_ID. Vui lòng cấu hình để đăng nhập Gmail.');
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

    const script = document.createElement('script');
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    script.defer = true;
    script.onload = initialize;
    script.onerror = () => onError?.('Không thể tải Google Identity Services.');
    document.body.appendChild(script);
  }, [onCredential, onError]);

  return <div ref={buttonRef} className="flex justify-center" />;
}
