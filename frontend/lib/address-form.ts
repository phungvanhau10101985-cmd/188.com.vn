import type { AddressCreateInput } from '@/types/api';
import {
  LEGACY_PROVINCE_TO_NEW,
  VN_PROVINCE_NAMES,
  VN_WARDS_BY_PROVINCE,
} from '@/lib/vietnam-admin';

const PROVINCE_SET = new Set(VN_PROVINCE_NAMES);

/** Chuẩn hóa SĐT Việt Nam về 10 số bắt đầu bằng 0. */
export function normalizeVnPhone(raw: string): string | null {
  let digits = raw.replace(/\D/g, '');
  if (digits.startsWith('84') && digits.length >= 11) digits = `0${digits.slice(2)}`;
  if (digits.length === 9) digits = `0${digits}`;
  if (!/^0\d{9,10}$/.test(digits)) return null;
  return digits;
}

export function prepareAddressPayload(
  input: AddressCreateInput,
): { ok: true; data: AddressCreateInput } | { ok: false; message: string } {
  const fullName = input.full_name.trim();
  if (fullName.length < 2) {
    return { ok: false, message: 'Họ và tên cần ít nhất 2 ký tự.' };
  }

  const phone = normalizeVnPhone(input.phone);
  if (!phone) {
    return { ok: false, message: 'Số điện thoại chưa đúng. Nhập 10 số, bắt đầu bằng 0.' };
  }

  const province = input.province?.trim() ?? '';
  const legacy = LEGACY_PROVINCE_TO_NEW[province];
  if (!province || !PROVINCE_SET.has(province)) {
    if (legacy) {
      return {
        ok: false,
        message: `${province} đã sáp nhập vào ${legacy}. Hãy chọn tỉnh mới, rồi chọn phường/xã.`,
      };
    }
    return { ok: false, message: 'Chọn tỉnh / thành phố.' };
  }

  const ward = input.ward?.trim() ?? '';
  const wards = VN_WARDS_BY_PROVINCE[province] ?? [];
  if (!ward || !wards.includes(ward)) {
    return { ok: false, message: 'Chọn phường / xã thuộc tỉnh đã chọn.' };
  }

  const street = input.street_address.trim();
  if (street.length < 5) {
    return { ok: false, message: 'Địa chỉ cụ thể cần ít nhất 5 ký tự (số nhà, tên đường).' };
  }

  return {
    ok: true,
    data: {
      full_name: fullName,
      phone,
      province,
      ward,
      street_address: street,
      is_default: Boolean(input.is_default),
    },
  };
}
