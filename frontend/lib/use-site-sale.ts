'use client';

import { useCallback, useEffect, useState } from 'react';
import type { SiteSaleCalendarState } from '@/types/api';
import { apiClient } from '@/lib/api-client';

export function useSiteSale() {
  const [state, setState] = useState<SiteSaleCalendarState | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    try {
      const data = await apiClient.getSiteSaleCalendar();
      setState(data);
    } catch {
      setState(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    if (!state?.countdown_to) return;
    const id = window.setInterval(() => {
      setState((prev) => (prev ? { ...prev } : prev));
    }, 1000);
    return () => window.clearInterval(id);
  }, [state?.countdown_to, state?.phase]);

  return { state, loading, reload };
}
