/**
 * Mở app ngân hàng kèm thông tin chuyển khoản VietQR.
 * https://dl.vietqr.io/pay?app=&ba=STK@maNH&am=&tn=&bn=&url=
 */

export type BankPayApp = {
  id: string;
  label: string;
  autofill: boolean;
};

/** App khách dùng để chuyển — thứ tự gần với sheet «Đã tìm thấy mã QR». */
export const BANK_PAY_APPS: BankPayApp[] = [
  { id: 'tcb', label: 'Techcombank', autofill: false },
  { id: 'mb', label: 'MB Bank', autofill: true },
  { id: 'bidv', label: 'BIDV', autofill: true },
  { id: 'vcb', label: 'Vietcombank', autofill: false },
  { id: 'acb', label: 'ACB ONE', autofill: true },
  { id: 'icb', label: 'VietinBank', autofill: true },
  { id: 'vpb', label: 'VPBank', autofill: false },
  { id: 'vba', label: 'Agribank', autofill: false },
  { id: 'tpb', label: 'TPBank', autofill: false },
  { id: 'ocb', label: 'OCB', autofill: true },
  { id: 'hdb', label: 'HDBank', autofill: false },
  { id: 'vib', label: 'VIB', autofill: false },
  { id: 'shb', label: 'SHB', autofill: false },
  { id: 'lpb', label: 'LPBank', autofill: false },
  { id: 'seab', label: 'SeABank', autofill: false },
  { id: 'cake', label: 'CAKE', autofill: false },
  { id: 'timo', label: 'Timo', autofill: false },
  { id: 'eib', label: 'Eximbank', autofill: false },
  { id: 'nab', label: 'Nam A Bank', autofill: false },
  { id: 'abb', label: 'ABBank', autofill: false },
  { id: 'pvcb', label: 'PVcomBank', autofill: false },
  { id: 'klb', label: 'KienlongBank', autofill: false },
  { id: 'ncb', label: 'NCB', autofill: false },
  { id: 'bvb', label: 'BAOVIET Bank', autofill: false },
  { id: 'vab', label: 'Vietbank', autofill: false },
  { id: 'shbvn', label: 'Shinhan Bank', autofill: false },
  { id: 'scb', label: 'SCB', autofill: false },
  { id: 'wvn', label: 'Woori Bank', autofill: false },
];

export const BANK_PAY_APPS_PREVIEW = 6;

const BENEFICIARY_BANK_ALIASES: Record<string, string> = {
  mb: 'mb',
  mbbank: 'mb',
  mbb: 'mb',
  '970422': 'mb',
  vcb: 'vcb',
  vietcombank: 'vcb',
  '970436': 'vcb',
  tcb: 'tcb',
  techcombank: 'tcb',
  '970407': 'tcb',
  bidv: 'bidv',
  '970418': 'bidv',
  acb: 'acb',
  '970416': 'acb',
  icb: 'icb',
  vietinbank: 'icb',
  ctg: 'icb',
  '970415': 'icb',
  vpb: 'vpb',
  vpbank: 'vpb',
  '970432': 'vpb',
  vba: 'vba',
  agribank: 'vba',
  '970405': 'vba',
  tpb: 'tpb',
  tpbank: 'tpb',
  '970423': 'tpb',
  ocb: 'ocb',
  '970448': 'ocb',
  hdb: 'hdb',
  hdbank: 'hdb',
  '970437': 'hdb',
  vib: 'vib',
  '970441': 'vib',
  shb: 'shb',
  '970443': 'shb',
  lpb: 'lpb',
  lpbank: 'lpb',
  lienvietpostbank: 'lpb',
  lienviet: 'lpb',
  '970449': 'lpb',
  seab: 'seab',
  seabank: 'seab',
  '970440': 'seab',
  cake: 'cake',
  timo: 'timo',
  bvbank: 'timo',
  eib: 'eib',
  eximbank: 'eib',
  '970431': 'eib',
  nab: 'nab',
  namabank: 'nab',
  '970428': 'nab',
  abb: 'abb',
  abbank: 'abb',
  '970425': 'abb',
  pvcb: 'pvcb',
  pvcombank: 'pvcb',
  '970412': 'pvcb',
  klb: 'klb',
  kienlongbank: 'klb',
  '970452': 'klb',
  ncb: 'ncb',
  '970419': 'ncb',
  bvb: 'bvb',
  baovietbank: 'bvb',
  baoviet: 'bvb',
  '970438': 'bvb',
  vab: 'vab',
  vietbank: 'vab',
  '970427': 'vab',
  shbvn: 'shbvn',
  shinhanbank: 'shbvn',
  shinhan: 'shbvn',
  '970424': 'shbvn',
  scb: 'scb',
  '970429': 'scb',
  wvn: 'wvn',
  wooribank: 'wvn',
  woori: 'wvn',
  '970457': 'wvn',
  stb: 'stb',
  sacombank: 'stb',
  '970403': 'stb',
  msb: 'msb',
  maritimebank: 'msb',
  '970426': 'msb',
  coopbank: 'coopbank',
  oceanbank: 'oceanbank',
  '970414': 'oceanbank',
  pbvn: 'pbvn',
  publicbank: 'pbvn',
  sgicb: 'sgicb',
  saigonbank: 'sgicb',
  cimb: 'cimb',
  '422589': 'cimb',
};

const KNOWN_BENEFICIARY_IDS = new Set(Object.values(BENEFICIARY_BANK_ALIASES));

/** Mã ngân hàng nhận tiền trong `ba=stk@ma` (MBBank → mb, Vietcombank → vcb…). */
export function vietQrBeneficiaryBankId(raw: string | null | undefined): string | null {
  const compact = (raw || '').trim().toLowerCase().replace(/[^a-z0-9]/g, '');
  if (!compact) return null;
  if (BENEFICIARY_BANK_ALIASES[compact]) return BENEFICIARY_BANK_ALIASES[compact];
  if (KNOWN_BENEFICIARY_IDS.has(compact)) return compact;
  return null;
}

export function bankPayAppIconUrl(appId: string): string {
  return `https://cdn.vietqr.io/bank-app-icon/${appId}-android.webp`;
}

export function buildVietQrBankDeeplink(input: {
  appId: string;
  accountNumber: string;
  beneficiaryBank: string | null | undefined;
  amount: number;
  transferContent: string;
  accountName?: string | null;
  returnUrl?: string | null;
}): string | null {
  const bankId = vietQrBeneficiaryBankId(input.beneficiaryBank);
  const account = (input.accountNumber || '').replace(/\s/g, '');
  const amount = Math.round(Number(input.amount));
  const content = (input.transferContent || '').trim();
  const appId = (input.appId || '').trim().toLowerCase();
  if (!bankId || !account || !appId || !Number.isFinite(amount) || amount <= 0 || !content) return null;

  const parts = [
    `app=${encodeURIComponent(appId)}`,
    `ba=${encodeURIComponent(account)}@${encodeURIComponent(bankId)}`,
    `am=${amount}`,
    `tn=${encodeURIComponent(content)}`,
  ];
  const name = (input.accountName || '').trim();
  if (name) parts.push(`bn=${encodeURIComponent(name)}`);
  const back = (input.returnUrl || '').trim();
  if (back) parts.push(`url=${encodeURIComponent(back)}`);
  return `https://dl.vietqr.io/pay?${parts.join('&')}`;
}
