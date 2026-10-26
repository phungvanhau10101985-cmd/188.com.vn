/**
 * Mở app ngân hàng kèm đúng chuỗi VietQR (số TK, số tiền, nội dung).
 * Link https://dl.vietqr.io/pay chỉ mở app trống khi trang trung gian không trao được payload.
 * App nhận QR qua: scheme://applink?targetPage=QRPay&qrContent=<EMV>
 */

export type BankPayPlatform = 'android' | 'ios' | 'other';

export type BankPayApp = {
  id: string;
  label: string;
  /** scheme không có // , ví dụ mbbank */
  scheme: string;
  /** path sau scheme, ví dụ applink hoặc host.qrTransfer */
  path: string;
  androidPackage: string;
};

/** App đã nhận chuỗi QR (Zalo/VietQR handoff). Vietcombank, Agribank, MoMo không nhận. */
export const BANK_PAY_APPS: BankPayApp[] = [
  { id: 'tcb', label: 'Techcombank', scheme: 'tcb', path: 'applink', androidPackage: 'vn.com.techcombank.bb.app' },
  { id: 'mb', label: 'MB Bank', scheme: 'mbbank', path: 'applink', androidPackage: 'com.mbmobile' },
  { id: 'bidv', label: 'BIDV', scheme: 'dl.bidvsmartbanking.vn', path: 'applink', androidPackage: 'com.vnpay.bidv' },
  { id: 'acb', label: 'ACB ONE', scheme: 'acbone', path: 'applink', androidPackage: 'mobile.acb.com.vn' },
  { id: 'icb', label: 'VietinBank', scheme: 'vietinbankipay', path: 'host.qrTransfer', androidPackage: 'com.vietinbank.ipay' },
  { id: 'vpb', label: 'VPBank', scheme: 'vpbankneo', path: 'applink', androidPackage: 'com.vnpay.vpbankonline' },
  { id: 'tpb', label: 'TPBank', scheme: 'hydro', path: 'applink', androidPackage: 'com.tpb.mb.gprsandroid' },
  { id: 'ocb', label: 'OCB', scheme: 'newomni-app', path: 'applink', androidPackage: 'vn.com.ocb.awe' },
  { id: 'hdb', label: 'HDBank', scheme: 'hdbankmobile', path: 'applink', androidPackage: 'com.vnpay.hdbank' },
  { id: 'stb', label: 'Sacombank', scheme: 'sacombankpay', path: 'applink', androidPackage: 'com.sacombank.ewallet' },
  { id: 'vib', label: 'VIB', scheme: 'myvib2', path: 'applink', androidPackage: 'com.vib.myvib2' },
  { id: 'shb', label: 'SHB', scheme: 'saha', path: 'applink', androidPackage: 'vn.shb.saha.mbanking' },
  { id: 'msb', label: 'MSB', scheme: 'msbdigibank', path: 'applink', androidPackage: 'vn.com.msb.smartBanking' },
  { id: 'seab', label: 'SeABank', scheme: 'seamobile', path: 'applink', androidPackage: 'vn.com.seabank.mb1' },
  { id: 'eib', label: 'Eximbank', scheme: 'eximbankomnimobile', path: 'applink', androidPackage: 'com.vnpay.EximBankOmni' },
  { id: 'lpb', label: 'LPBank', scheme: 'lv24h', path: 'applink', androidPackage: 'vn.com.lpbank.digibank' },
  { id: 'cake', label: 'CAKE', scheme: 'cake.vn', path: 'applink', androidPackage: 'xyz.be.cake' },
  { id: 'timo', label: 'Timo', scheme: 'timo', path: 'applink', androidPackage: 'io.lifestyle.plus' },
  { id: 'pvcb', label: 'PVcomBank', scheme: 'pvcapp', path: 'applink', androidPackage: 'com.pvcombank.retail' },
  { id: 'abb', label: 'ABBank', scheme: 'vn.abbank.retail', path: 'applink', androidPackage: 'vn.abbank.retail' },
];

export const BANK_PAY_APPS_PREVIEW = 6;

const BENEFICIARY_BINS: Record<string, string> = {
  mb: '970422',
  mbbank: '970422',
  mbb: '970422',
  '970422': '970422',
  vcb: '970436',
  vietcombank: '970436',
  '970436': '970436',
  tcb: '970407',
  techcombank: '970407',
  '970407': '970407',
  bidv: '970418',
  '970418': '970418',
  acb: '970416',
  '970416': '970416',
  icb: '970415',
  vietinbank: '970415',
  ctg: '970415',
  '970415': '970415',
  vpb: '970432',
  vpbank: '970432',
  '970432': '970432',
  vba: '970405',
  agribank: '970405',
  '970405': '970405',
  tpb: '970423',
  tpbank: '970423',
  '970423': '970423',
  ocb: '970448',
  '970448': '970448',
  hdb: '970437',
  hdbank: '970437',
  '970437': '970437',
  vib: '970441',
  '970441': '970441',
  shb: '970443',
  '970443': '970443',
  lpb: '970449',
  lpbank: '970449',
  lienvietpostbank: '970449',
  lienviet: '970449',
  '970449': '970449',
  seab: '970440',
  seabank: '970440',
  '970440': '970440',
  cake: '546034',
  '546034': '546034',
  timo: '963388',
  bvbank: '963388',
  '963388': '963388',
  eib: '970431',
  eximbank: '970431',
  '970431': '970431',
  nab: '970428',
  namabank: '970428',
  '970428': '970428',
  abb: '970425',
  abbank: '970425',
  '970425': '970425',
  pvcb: '970412',
  pvcombank: '970412',
  '970412': '970412',
  klb: '970452',
  kienlongbank: '970452',
  '970452': '970452',
  ncb: '970419',
  '970419': '970419',
  bvb: '970438',
  baovietbank: '970438',
  baoviet: '970438',
  '970438': '970438',
  vab: '970427',
  vietabank: '970427',
  '970427': '970427',
  vietbank: '970433',
  '970433': '970433',
  shbvn: '970424',
  shinhanbank: '970424',
  shinhan: '970424',
  '970424': '970424',
  scb: '970429',
  '970429': '970429',
  wvn: '970457',
  wooribank: '970457',
  woori: '970457',
  '970457': '970457',
  stb: '970403',
  sacombank: '970403',
  '970403': '970403',
  msb: '970426',
  maritimebank: '970426',
  '970426': '970426',
  coopbank: '970446',
  '970446': '970446',
  oceanbank: '970414',
  '970414': '970414',
  pbvn: '970439',
  publicbank: '970439',
  '970439': '970439',
  sgicb: '970400',
  saigonbank: '970400',
  '970400': '970400',
  cimb: '422589',
  '422589': '422589',
};

/** BIN Napas của ngân hàng nhận tiền (MBBank → 970422). */
export function vietQrBeneficiaryBin(raw: string | null | undefined): string | null {
  const compact = (raw || '').trim().toLowerCase().replace(/[^a-z0-9]/g, '');
  if (!compact) return null;
  return BENEFICIARY_BINS[compact] ?? null;
}

/** @deprecated dùng vietQrBeneficiaryBin */
export function vietQrBeneficiaryBankId(raw: string | null | undefined): string | null {
  return vietQrBeneficiaryBin(raw);
}

export function bankPayAppIconUrl(appId: string): string {
  return `https://cdn.vietqr.io/bank-app-icon/${appId}-android.webp`;
}

export function detectBankPayPlatform(userAgent: string | null | undefined): BankPayPlatform {
  const ua = userAgent || '';
  if (/Android/i.test(ua)) return 'android';
  if (/iPhone|iPad|iPod/i.test(ua)) return 'ios';
  return 'other';
}

function tlv(id: string, value: string): string {
  const length = String(Array.from(value).length).padStart(2, '0');
  return `${id}${length}${value}`;
}

function crc16CcittFalse(text: string): string {
  let crc = 0xffff;
  for (let i = 0; i < text.length; i += 1) {
    crc ^= text.charCodeAt(i) << 8;
    for (let bit = 0; bit < 8; bit += 1) {
      crc = crc & 0x8000 ? ((crc << 1) ^ 0x1021) & 0xffff : (crc << 1) & 0xffff;
    }
  }
  return crc.toString(16).toUpperCase().padStart(4, '0');
}

/** Chuỗi EMV VietQR động: BIN + STK + số tiền + nội dung. */
export function buildVietQrPayload(input: {
  beneficiaryBank: string | null | undefined;
  accountNumber: string;
  amount: number;
  transferContent: string;
}): string | null {
  const bin = vietQrBeneficiaryBin(input.beneficiaryBank);
  const account = (input.accountNumber || '').replace(/\s/g, '');
  const amount = Math.round(Number(input.amount));
  const note = (input.transferContent || '').trim().slice(0, 50);
  if (!bin || !/^\d{6}$/.test(bin)) return null;
  if (!/^[A-Za-z0-9]{1,19}$/.test(account)) return null;
  if (!Number.isSafeInteger(amount) || amount <= 0 || String(amount).length > 13) return null;
  if (!note || Array.from(note).length > 50) return null;

  const merchant =
    tlv('00', 'A000000727') +
    tlv('01', tlv('00', bin) + tlv('01', account)) +
    tlv('02', 'QRIBFTTA');
  const body =
    tlv('00', '01') +
    tlv('01', '12') +
    tlv('38', merchant) +
    tlv('53', '704') +
    tlv('54', String(amount)) +
    tlv('58', 'VN') +
    tlv('62', tlv('08', note)) +
    '6304';
  return body + crc16CcittFalse(body);
}

/** Link mở app đã gắn chuỗi QR. Android dùng intent để app nhận query, không chỉ mở màn hình chính. */
export function buildBankQrOpenUrl(input: {
  appId: string;
  beneficiaryBank: string | null | undefined;
  accountNumber: string;
  amount: number;
  transferContent: string;
  platform: BankPayPlatform;
}): string | null {
  const app = BANK_PAY_APPS.find((item) => item.id === input.appId);
  const payload = buildVietQrPayload(input);
  if (!app || !payload) return null;
  const query = `targetPage=QRPay&qrContent=${encodeURIComponent(payload)}`;
  if (input.platform === 'android') {
    return `intent://${app.path}?${query}#Intent;scheme=${app.scheme};package=${app.androidPackage};end`;
  }
  return `${app.scheme}://${app.path}?${query}`;
}
