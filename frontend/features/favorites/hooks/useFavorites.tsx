'use client';

import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { apiClient } from '@/lib/api-client';

interface FavoriteContextType {
  favoriteCount: number;
  refreshFavorites: () => Promise<void>;
}

const FavoriteContext = createContext<FavoriteContextType | undefined>(undefined);

export function FavoriteProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  const [favoriteCount, setFavoriteCount] = useState(0);

  const refreshFavorites = useCallback(async () => {
    try {
      const list = await apiClient.getFavorites();
      setFavoriteCount(Array.isArray(list) ? list.length : 0);
    } catch {
      setFavoriteCount(0);
    }
  }, []);

  useEffect(() => {
    refreshFavorites();
  }, [refreshFavorites, isAuthenticated]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const onAuth = () => {
      void refreshFavorites();
    };
    window.addEventListener('188-auth-session-changed', onAuth);
    return () => window.removeEventListener('188-auth-session-changed', onAuth);
  }, [refreshFavorites]);

  return (
    <FavoriteContext.Provider value={{ favoriteCount, refreshFavorites }}>
      {children}
    </FavoriteContext.Provider>
  );
}

export function useFavorites(): FavoriteContextType {
  const ctx = useContext(FavoriteContext);
  if (ctx === undefined) {
    throw new Error('useFavorites must be used within FavoriteProvider');
  }
  return ctx;
}
