/** Dữ liệu mã nhúng public từ API (SSR layout). */

export type PublicSiteEmbeds = {
  head: string[];
  body_open: string[];
  body_close: string[];
};

const empty: PublicSiteEmbeds = { head: [], body_open: [], body_close: [] };

export async function fetchPublicSiteEmbeds(): Promise<PublicSiteEmbeds> {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, '') || 'http://localhost:8001/api/v1';
  try {
    const res = await fetch(`${base}/embed-codes/public`, {
      next: { revalidate: 120 },
    });
    if (!res.ok) return empty;
    const data = (await res.json()) as Partial<PublicSiteEmbeds>;
    return {
      head: Array.isArray(data.head) ? data.head.filter(Boolean) : [],
      body_open: Array.isArray(data.body_open) ? data.body_open.filter(Boolean) : [],
      body_close: Array.isArray(data.body_close) ? data.body_close.filter(Boolean) : [],
    };
  } catch {
    return empty;
  }
}
