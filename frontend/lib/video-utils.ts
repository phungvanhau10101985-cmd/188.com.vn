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
