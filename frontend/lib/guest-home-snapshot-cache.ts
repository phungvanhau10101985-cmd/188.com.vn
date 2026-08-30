'use client';

import { getGuestSessionId } from '@/lib/guest-session';
import type { HomeRecommendationSnapshotResponse } from '@/types/api';

/**
 * Cache đề xuất trang chủ cho khách chưa login — IndexedDB trên máy họ.
 * Cùng vòng đời với `188_guest_browser_id`; hết hạn 7 ngày.
 */
const DB_NAME = '188-guest-home';
const DB_VERSION = 1;
const STORE = 'snapshots';
const RECORD_KEY = 'v1';
export const GUEST_HOME_SNAPSHOT_TTL_MS = 7 * 24 * 60 * 60 * 1000;

type GuestHomeSnapshotRecord = {
  guestSessionId: string;
  savedAt: number;
  snapshot: HomeRecommendationSnapshotResponse;
};

function openDb(): Promise<IDBDatabase | null> {
  if (typeof window === 'undefined' || !window.indexedDB) return Promise.resolve(null);
  return new Promise((resolve) => {
    try {
      const req = window.indexedDB.open(DB_NAME, DB_VERSION);
      req.onerror = () => resolve(null);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(STORE)) {
          db.createObjectStore(STORE);
        }
      };
      req.onsuccess = () => resolve(req.result);
    } catch {
      resolve(null);
    }
  });
}

async function withStore<T>(
  mode: IDBTransactionMode,
  run: (store: IDBObjectStore) => IDBRequest<T>
): Promise<T | undefined> {
  const db = await openDb();
  if (!db) return undefined;
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, mode);
      const req = run(tx.objectStore(STORE));
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  } catch {
    return undefined;
  } finally {
    db.close();
  }
}

export async function readGuestHomeSnapshot(): Promise<HomeRecommendationSnapshotResponse | null> {
  const sid = getGuestSessionId();
  if (!sid) return null;
  const row = await withStore('readonly', (store) => store.get(RECORD_KEY));
  const rec = row as GuestHomeSnapshotRecord | undefined;
  if (!rec?.snapshot?.found || rec.guestSessionId !== sid) return null;
  if (Date.now() - (rec.savedAt || 0) > GUEST_HOME_SNAPSHOT_TTL_MS) return null;
  if (!rec.snapshot.recommendation) return null;
  return rec.snapshot;
}

export async function writeGuestHomeSnapshot(
  snapshot: HomeRecommendationSnapshotResponse
): Promise<void> {
  const sid = getGuestSessionId();
  if (!sid || !snapshot.found || !snapshot.recommendation) return;
  const rec: GuestHomeSnapshotRecord = {
    guestSessionId: sid,
    savedAt: Date.now(),
    snapshot,
  };
  await withStore('readwrite', (store) => store.put(rec, RECORD_KEY));
}

export async function clearGuestHomeSnapshot(): Promise<void> {
  await withStore('readwrite', (store) => store.delete(RECORD_KEY));
}
