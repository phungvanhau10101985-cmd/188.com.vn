/**
 * Meta click ID + Advanced Matching — giữ fbc/fbp 90 ngày và gửi PII cho Pixel/CAPI.
 * Meta: thiếu fbc trên Purchase làm giảm mạnh số chuyển đổi được báo cáo thêm.
 */

const COOKIE_MAX_AGE_SEC = 90 * 24 * 60 * 60;
const LS_FBCLID = '188_meta_fbclid';
const LS_FBC = '188_meta_fbc';
const LS_FBP = '188_meta_fbp';

const FBP_RE = /^fb\.\d+\.\d+\.\d+$/;
const FBC_RE = /^fb\.\d+\.\d+\.[A-Za-z0-9_-]+$/;

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

function readCookie(name: string): string | null {
  if (typeof document === 'undefined') return null;
  const hit = document.cookie.split('; ').find((row) => row.startsWith(`${name}=`));
  if (!hit) return null;
  const v = hit.slice(name.length + 1);
  try {
    return decodeURIComponent(v);
  } catch {
    return v;
  }
}

function writeCookie(name: string, value: string): void {
  if (typeof document === 'undefined' || typeof location === 'undefined') return;
  const secure = location.protocol === 'https:' ? ';Secure' : '';
  document.cookie = `${name}=${encodeURIComponent(value)};path=/;max-age=${COOKIE_MAX_AGE_SEC};SameSite=Lax${secure}`;
}

export function isValidMetaFbp(value: string | null | undefined): value is string {
  return Boolean(value && FBP_RE.test(value.trim()));
}

export function isValidMetaFbc(value: string | null | undefined): value is string {
  return Boolean(value && FBC_RE.test(value.trim()) && value.trim().length <= 512);
}

function newFbp(): string {
  return `fb.1.${Math.floor(Date.now() / 1000)}.${Math.floor(Math.random() * 1e16)}`;
}

function fbcFromFbclid(fbclid: string, existing?: string | null): string {
  const clid = fbclid.trim();
  if (existing && isValidMetaFbc(existing) && existing.endsWith(`.${clid}`)) {
    return existing;
  }
  return `fb.1.${Math.floor(Date.now() / 1000)}.${clid}`;
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
  const fbclid = urlClid || lsGet(LS_FBCLID);

  let fbc = readCookie('_fbc') || lsGet(LS_FBC) || '';
  if (fbclid) {
    fbc = fbcFromFbclid(fbclid, fbc);
    writeCookie('_fbc', fbc);
    lsSet(LS_FBC, fbc);
  } else if (isValidMetaFbc(fbc)) {
    writeCookie('_fbc', fbc);
    lsSet(LS_FBC, fbc);
  } else {
    fbc = '';
  }

  let fbp = readCookie('_fbp') || lsGet(LS_FBP) || '';
  if (!isValidMetaFbp(fbp)) {
    fbp = newFbp();
  }
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

export function getMetaCapiUserData(): Record<string, string> {
  persistMetaClickIds();
  const cookies = readMetaClickIds();
  const pii = matchingToPixelParams(matching);
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
