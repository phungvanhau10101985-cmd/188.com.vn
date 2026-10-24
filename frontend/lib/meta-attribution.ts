/**
 * Meta click ID + Advanced Matching — giữ fbc/fbp 90 ngày và gửi PII cho Pixel/CAPI.
 * Meta: thiếu fbc trên Purchase làm giảm mạnh số chuyển đổi được báo cáo thêm.
 */

const COOKIE_MAX_AGE_SEC = 90 * 24 * 60 * 60;
const META_CLICK_ID_MAX_AGE_MS = COOKIE_MAX_AGE_SEC * 1000;
const META_CLOCK_SKEW_MS = 5 * 60 * 1000;
const LS_FBCLID = '188_meta_fbclid';
const LS_FBC = '188_meta_fbc';
const LS_FBP = '188_meta_fbp';

const FBP_RE = /^fb\.\d+\.(\d{13})\.\d+$/;
/** Timestamp là group 1. Đuôi giữ nguyên fbclid + phụ lục Parameter Builder (có dấu chấm). */
const FBC_RE = /^fb\.\d{1,3}\.(\d{13})\.\S+$/;
const FBC_MAX_LEN = 2048;

export type MetaAdvancedMatchingPatch = {
  email?: string | null;
  phone?: string | null;
  fullName?: string | null;
  gender?: string | null;
  dateOfBirth?: string | null;
  userId?: number | string | null;
  city?: string | null;
  state?: string | null;
  country?: string | null;
};

type PixelWindow = Window & {
  fbq?: (...args: unknown[]) => void;
  __188FbPixelId?: string;
};

let matching: MetaAdvancedMatchingPatch = {};
let pixelReadyBound = false;

function lsGet(key: string): string {
  try {
    return (localStorage.getItem(key) || '').trim();
  } catch {
    return '';
  }
}

function lsSet(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* private mode */
  }
}

function decodeCookieValue(raw: string): string {
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

function readCookieValues(name: string): string[] {
  if (typeof document === 'undefined') return [];
  const prefix = `${name}=`;
  const out: string[] = [];
  for (const row of document.cookie.split('; ')) {
    if (!row.startsWith(prefix)) continue;
    const v = decodeCookieValue(row.slice(prefix.length)).trim();
    if (v) out.push(v);
  }
  return out;
}

function readCookie(name: string): string | null {
  return readCookieValues(name)[0] ?? null;
}

function writeCookie(name: string, value: string): void {
  if (typeof document === 'undefined' || typeof location === 'undefined') return;
  const secure = location.protocol === 'https:' ? ';Secure' : '';
  document.cookie = `${name}=${encodeURIComponent(value)};path=/;max-age=${COOKIE_MAX_AGE_SEC};SameSite=Lax${secure}`;
}

export function isValidMetaFbp(value: string | null | undefined): value is string {
  return hasValidMetaCreationTime(value, FBP_RE);
}

export function isValidMetaFbc(value: string | null | undefined): value is string {
  if (!value) return false;
  const v = value.trim();
  if (!v || v.length > FBC_MAX_LEN || /[\s;,]/.test(v)) return false;
  return hasValidMetaCreationTime(v, FBC_RE);
}

function hasValidMetaCreationTime(
  value: string | null | undefined,
  pattern: RegExp
): value is string {
  if (!value) return false;
  const match = pattern.exec(value.trim());
  if (!match) return false;
  const creationTimeMs = Number(match[1]);
  const now = Date.now();
  return (
    Number.isSafeInteger(creationTimeMs) &&
    creationTimeMs <= now + META_CLOCK_SKEW_MS &&
    creationTimeMs >= now - META_CLICK_ID_MAX_AGE_MS
  );
}

function newFbp(): string {
  return `fb.1.${Date.now()}.${Math.floor(Math.random() * 1e16)}`;
}

function fbcTail(value: string): string {
  const match = /^fb\.\d{1,3}\.\d{13}\.(.+)$/.exec(value.trim());
  return match ? match[1] : '';
}

/** Cookie Pixel có thể là `fbclid` hoặc `fbclid.<phụ lục>` — không được cắt phụ lục. */
function fbcMatchesFbclid(fbc: string, fbclid: string): boolean {
  const clid = fbclid.trim();
  if (!clid) return false;
  const tail = fbcTail(fbc);
  return tail === clid || tail.startsWith(`${clid}.`);
}

/**
 * Chỉ số subdomain Meta: example.com = 1, www.example.com = 2.
 * `com.vn` là hậu tố kép nên 188.com.vn = 1, www.188.com.vn = 2.
 */
export function metaSubdomainIndex(hostname: string): number {
  const host = hostname.split(':')[0].toLowerCase().replace(/\.$/, '');
  if (!host || host === 'localhost' || /^\d{1,3}(\.\d{1,3}){3}$/.test(host)) return 1;
  const parts = host.split('.').filter(Boolean);
  if (parts.length <= 1) return 0;
  const last = parts[parts.length - 1] || '';
  const second = parts[parts.length - 2] || '';
  const multiPartSuffix = last.length === 2 && /^(com|co|org|net|gov|edu|ac|ne)$/.test(second);
  if (multiPartSuffix && parts.length >= 3) return parts.length - 2;
  return parts.length - 1;
}

function fbcFromFbclid(fbclid: string, existing?: string | null): string {
  const clid = fbclid.trim();
  if (existing && isValidMetaFbc(existing) && fbcMatchesFbclid(existing, clid)) {
    return existing.trim();
  }
  const host = typeof location !== 'undefined' ? location.hostname : '';
  return `fb.${metaSubdomainIndex(host)}.${Date.now()}.${clid}`;
}

function bindPixelReady(): void {
  if (pixelReadyBound || typeof window === 'undefined') return;
  pixelReadyBound = true;
  window.addEventListener('188-site-embeds-ready', () => {
    applyPixelAdvancedMatching();
  });
}

function foldMetaText(raw: string): string {
  return raw
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function splitVnName(fullName: string): { fn?: string; ln?: string } {
  const folded = foldMetaText(fullName);
  if (!folded) return {};
  const parts = folded.split(' ');
  if (parts.length === 1) return { fn: parts[0] };
  return { ln: parts[0], fn: parts.slice(1).join(' ') };
}

function normalizePhoneVn(phone: string): string | undefined {
  const digits = phone.replace(/\D/g, '');
  if (!digits) return undefined;
  if (digits.startsWith('0')) return `84${digits.slice(1)}`;
  if (!digits.startsWith('84')) return `84${digits}`;
  return digits;
}

function genderToMeta(raw: string): 'm' | 'f' | undefined {
  const s = foldMetaText(raw).replace(/\s+/g, '');
  if (s === 'male' || s === 'm' || s === 'nam') return 'm';
  if (s === 'female' || s === 'f' || s === 'nu' || s === 'nữ') return 'f';
  return undefined;
}

function dobToMeta(raw: string): string | undefined {
  const s = raw.trim();
  const iso = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
  if (iso) return `${iso[1]}${iso[2]}${iso[3]}`;
  const compact = s.replace(/\D/g, '');
  return compact.length === 8 ? compact : undefined;
}

function matchingToPixelParams(src: MetaAdvancedMatchingPatch): Record<string, string> {
  const out: Record<string, string> = {};
  const email = (src.email || '').trim().toLowerCase();
  if (email.includes('@')) out.em = email;
  const phone = normalizePhoneVn(src.phone || '');
  if (phone) out.ph = phone;
  const names = splitVnName(src.fullName || '');
  if (names.fn) out.fn = names.fn;
  if (names.ln) out.ln = names.ln;
  const ge = src.gender ? genderToMeta(src.gender) : undefined;
  if (ge) out.ge = ge;
  const db = src.dateOfBirth ? dobToMeta(src.dateOfBirth) : undefined;
  if (db) out.db = db;
  const ct = foldMetaText(src.city || '');
  if (ct) out.ct = ct;
  const st = foldMetaText(src.state || '');
  if (st) out.st = st;
  const country = foldMetaText(src.country || 'vn') || 'vn';
  if (country) out.country = country.length === 2 ? country : 'vn';
  if (src.userId != null && String(src.userId).trim()) {
    out.external_id = String(src.userId).trim();
  }
  return out;
}

export function applyPixelAdvancedMatching(): void {
  if (typeof window === 'undefined') return;
  const w = window as PixelWindow;
  const fbq = w.fbq;
  const pid = (w.__188FbPixelId || '').trim();
  if (typeof fbq !== 'function' || !pid) return;
  const params = matchingToPixelParams(matching);
  if (!Object.keys(params).length) return;
  fbq('init', pid, params, { autoConfig: false });
}

export function patchMetaAdvancedMatching(patch: MetaAdvancedMatchingPatch): void {
  matching = { ...matching, ...patch };
  bindPixelReady();
  applyPixelAdvancedMatching();
}

export function resetMetaAdvancedMatching(): void {
  matching = {};
}

export function persistMetaClickIds(): { fbp?: string; fbc?: string } {
  if (typeof window === 'undefined' || typeof document === 'undefined') return {};

  const params = new URLSearchParams(window.location.search);
  const urlClid = (params.get('fbclid') || '').trim();
  if (urlClid) lsSet(LS_FBCLID, urlClid);

  const cookieFbcs = readCookieValues('_fbc');
  const storedFbc = lsGet(LS_FBC);
  const fbcCandidates = [...cookieFbcs, storedFbc];
  let fbc =
    (urlClid ? fbcCandidates.find((v) => isValidMetaFbc(v) && fbcMatchesFbclid(v, urlClid)) : '') ||
    fbcCandidates.find((v) => isValidMetaFbc(v)) ||
    '';
  if (urlClid) {
    const next = fbcFromFbclid(urlClid, fbc);
    if (isValidMetaFbc(next)) {
      fbc = next;
      writeCookie('_fbc', fbc);
      lsSet(LS_FBC, fbc);
    }
  } else if (fbc) {
    // Chỉ khôi phục _fbc nguyên bản. Không ghép fbclid cũ với timestamp hiện tại.
    writeCookie('_fbc', fbc);
    lsSet(LS_FBC, fbc);
  }

  const cookieFbp = readCookie('_fbp');
  const storedFbp = lsGet(LS_FBP);
  const fbp = isValidMetaFbp(cookieFbp)
    ? cookieFbp
    : isValidMetaFbp(storedFbp)
      ? storedFbp
      : newFbp();
  writeCookie('_fbp', fbp);
  lsSet(LS_FBP, fbp);

  return {
    ...(isValidMetaFbp(fbp) ? { fbp } : {}),
    ...(isValidMetaFbc(fbc) ? { fbc } : {}),
  };
}

export function readMetaClickIds(): { fbp?: string; fbc?: string } {
  const fbp = readCookie('_fbp') || lsGet(LS_FBP);
  const fbc = readCookie('_fbc') || lsGet(LS_FBC);
  return {
    ...(isValidMetaFbp(fbp) ? { fbp } : {}),
    ...(isValidMetaFbc(fbc) ? { fbc } : {}),
  };
}

export function getMetaCapiUserData(
  opts?: { includeEmail?: boolean }
): Record<string, string> {
  persistMetaClickIds();
  const cookies = readMetaClickIds();
  const pii = matchingToPixelParams(matching);
  if (opts?.includeEmail === false) delete pii.em;
  return {
    country: 'vn',
    ...pii,
    ...cookies,
  };
}

export function getMetaAdsCheckoutFields(): {
  meta_fbp?: string;
  meta_fbc?: string;
} {
  const ids = persistMetaClickIds();
  return {
    ...(ids.fbp ? { meta_fbp: ids.fbp } : {}),
    ...(ids.fbc ? { meta_fbc: ids.fbc } : {}),
  };
}
