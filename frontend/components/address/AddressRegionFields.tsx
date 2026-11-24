'use client';

import { useId, useMemo } from 'react';
import {
  LEGACY_PROVINCE_TO_NEW,
  VN_ADMIN_AS_OF,
  VIETNAM_PROVINCES,
  isKnownProvince,
  wardsOfProvince,
} from '@/lib/vietnam-admin';

type AddressRegionFieldsProps = {
  province: string;
  ward: string;
  onChange: (next: { province: string; ward: string }) => void;
  selectClassName: string;
};

function groupWards(wards: readonly string[]): { label: string; items: string[] }[] {
  const groups = [
    { label: 'Phường', items: [] as string[] },
    { label: 'Xã', items: [] as string[] },
    { label: 'Đặc khu', items: [] as string[] },
    { label: 'Đã lưu', items: [] as string[] },
  ];
  for (const ward of wards) {
    if (ward.startsWith('Phường ')) groups[0].items.push(ward);
    else if (ward.startsWith('Xã ')) groups[1].items.push(ward);
    else if (ward.startsWith('Đặc khu ')) groups[2].items.push(ward);
    else groups[3].items.push(ward);
  }
  return groups.filter((group) => group.items.length > 0);
}

export default function AddressRegionFields({
  province,
  ward,
  onChange,
  selectClassName,
}: AddressRegionFieldsProps) {
  const provinceId = useId();
  const wardId = useId();
  const knownProvince = isKnownProvince(province);
  const legacyTarget = LEGACY_PROVINCE_TO_NEW[province];
  const officialWards = useMemo(() => wardsOfProvince(province), [province]);
  const provinceOptions = useMemo(() => {
    if (!province || knownProvince) return VIETNAM_PROVINCES;
    return [province, ...VIETNAM_PROVINCES];
  }, [knownProvince, province]);
  const visibleWards = useMemo(() => {
    if (ward && !officialWards.includes(ward)) return [ward, ...officialWards];
    return officialWards;
  }, [officialWards, ward]);
  const wardGroups = useMemo(() => groupWards(visibleWards), [visibleWards]);
  const fieldClass = `${selectClassName} disabled:cursor-not-allowed disabled:bg-gray-50 disabled:text-gray-500`;
  const asOf = VN_ADMIN_AS_OF.split('-').reverse().join('/');

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label htmlFor={provinceId} className="block text-sm font-medium text-gray-700 mb-1">
            Tỉnh / Thành phố *
          </label>
          <select
            id={provinceId}
            name="province"
            required
            value={province}
            autoComplete="address-level1"
            onChange={(event) => onChange({ province: event.target.value, ward: '' })}
            className={fieldClass}
          >
            <option value="">— Chọn tỉnh/thành phố —</option>
            {provinceOptions.map((name) => (
              <option key={name} value={name}>
                {isKnownProvince(name) ? name : `${name} (địa giới cũ)`}
              </option>
            ))}
          </select>
          {legacyTarget ? (
            <p className="mt-1 text-xs text-amber-800">
              {province} đã sáp nhập vào {legacyTarget}.{' '}
              <button
                type="button"
                className="underline font-medium"
                onClick={() => onChange({ province: legacyTarget, ward: '' })}
              >
                Chọn {legacyTarget}
              </button>
            </p>
          ) : null}
        </div>
        <div>
          <label htmlFor={wardId} className="block text-sm font-medium text-gray-700 mb-1">
            Phường / Xã *
          </label>
          <select
            id={wardId}
            name="ward"
            required
            value={ward}
            disabled={!knownProvince}
            autoComplete="address-level2"
            onChange={(event) => onChange({ province, ward: event.target.value })}
            className={fieldClass}
          >
            <option value="">{knownProvince ? '— Chọn phường/xã —' : '— Chọn tỉnh trước —'}</option>
            {wardGroups.map((group) => (
              <optgroup key={group.label} label={group.label}>
                {group.items.map((name) => (
                  <option key={name} value={name}>
                    {officialWards.includes(name) ? name : `${name} (địa giới cũ)`}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </div>
      </div>
      <p className="text-xs text-gray-500">
        Danh mục đến {asOf}. Cấp quận/huyện đã bãi bỏ, chọn thẳng phường/xã.
      </p>
    </div>
  );
}
