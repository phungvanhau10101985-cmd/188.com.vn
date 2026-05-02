/**
 * Hỗ trợ nhận diện và xử lý link video sản phẩm.
 * Hỗ trợ 2 loại: YouTube (embed/watch/youtu.be) và CDN .mp4 (vd: 188comvn.b-cdn.net).
 */

export type VideoKind = 'youtube' | 'cdn_mp4' | null;

export interface ParsedVideo {
  kind: VideoKind;
  /** YouTube: video ID. CDN: full URL. */
  urlOrId: string;
  /** Chỉ có với YouTube: thumbnail từ img.youtube.com */
  thumbUrl: string | null;
}

const YOUTUBE_EMBED = /youtube\.com\/embed\/([^&?/]+)/i;
const YOUTUBE_WATCH = /youtube\.com\/watch\?v=([^&]+)/i;
const YOUTUBE_SHORT = /youtu\.be\/([^&?/]+)/i;
const CDN_MP4 = /\.mp4(\?|$)/i;

export function parseVideoLink(link: string | undefined | null): ParsedVideo | null {
  const raw = link?.trim();
  if (!raw) return null;

  // YouTube embed: https://www.youtube.com/embed/mbZVx9tJRYk
  let m = raw.match(YOUTUBE_EMBED);
  if (m) {
    const id = m[1];
    return {
      kind: 'youtube',
      urlOrId: id,
      thumbUrl: `https://img.youtube.com/vi/${id}/maxresdefault.jpg`,
    };
  }
  m = raw.match(YOUTUBE_WATCH) || raw.match(YOUTUBE_SHORT);
  if (m) {
    const id = m[1];
    return {
      kind: 'youtube',
      urlOrId: id,
      thumbUrl: `https://img.youtube.com/vi/${id}/maxresdefault.jpg`,
    };
  }

  // CDN .mp4: https://188comvn.b-cdn.net/...mp4?...
  if (CDN_MP4.test(raw)) {
    return {
      kind: 'cdn_mp4',
      urlOrId: raw,
      thumbUrl: null,
    };
  }

  return null;
}

/** Trả về true nếu sản phẩm có link video hợp lệ (YouTube hoặc CDN .mp4). */
export function hasVideoLink(link: string | undefined | null): boolean {
  return parseVideoLink(link) !== null;
}

/**
 * Origin site cho tham số ?origin= của player YouTube.
 * Trên trình duyệt **ưu tiên `window.location.origin`** để khớp trang đang mở — tránh lỗi 153 khi
 * `NEXT_PUBLIC_SITE_URL` trỏ production nhưng đang xem localhost/staging (YouTube so khớp origin).
 * SSR: dùng env rồi fallback domain production.
 */
export function getSiteOriginForEmbed(): string {
  if (typeof window !== "undefined" && window.location?.origin) {
    return window.location.origin;
  }
  const fromEnv =
    (typeof process !== "undefined" &&
      process.env.NEXT_PUBLIC_SITE_URL?.trim().replace(/\/$/, "")) ||
    "";
  if (fromEnv) return fromEnv;
  return "https://188.com.vn";
}

/**
 * URL nhúng YouTube (privacy-enhanced nocookie + origin + playsinline).
 * Dùng cho iframe src — không dùng link watch trực tiếp.
 */
export function buildYoutubeEmbedSrc(
  videoId: string,
  options?: { autoplay?: boolean; muted?: boolean }
): string {
  const id = encodeURIComponent(videoId);
  const origin = getSiteOriginForEmbed();
  const autoplay = options?.autoplay ? '1' : '0';
  const muted = options?.muted ? '1' : '0';
  const q = new URLSearchParams({
    autoplay,
    mute: muted,
    rel: '0',
    modestbranding: '1',
    playsinline: '1',
    enablejsapi: '1',
    origin,
  });
  return `https://www.youtube-nocookie.com/embed/${id}?${q.toString()}`;
}
