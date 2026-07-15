'use client';

import { useEffect, useState } from 'react';
import AdminStepUpOtpModal from '@/components/auth/AdminStepUpOtpModal';
import {
  clearAdminStepUp,
  registerAdminStepUpPromptHandler,
  unregisterAdminStepUpPromptHandler,
} from '@/lib/admin-step-up';

type PendingRetry<T = unknown> = {
  retry: () => Promise<T>;
  resolve: (value: T) => void;
  reject: (reason?: unknown) => void;
};

export default function AdminDestructiveStepUpProvider({ children }: { children: React.ReactNode }) {
  const [pending, setPending] = useState<PendingRetry | null>(null);

  useEffect(() => {
    registerAdminStepUpPromptHandler(<T,>(retry: () => Promise<T>) => {
      return new Promise<T>((resolve, reject) => {
        setPending({
          retry: retry as () => Promise<unknown>,
          resolve: resolve as (value: unknown) => void,
          reject,
        });
      });
    });
    return () => unregisterAdminStepUpPromptHandler();
  }, []);

  const closeModal = () => {
    setPending((current) => {
      if (current) current.reject(new Error('Đã hủy xác minh OTP.'));
      return null;
    });
  };

  const completeVerified = async () => {
    const current = pending;
    if (!current) return;
    setPending(null);
    try {
      const result = await current.retry();
      current.resolve(result);
    } catch (err) {
      clearAdminStepUp();
      current.reject(err);
    }
  };

  return (
    <>
      {children}
      {pending ? (
        <AdminStepUpOtpModal onClose={closeModal} onVerified={() => void completeVerified()} />
      ) : null}
    </>
  );
}
