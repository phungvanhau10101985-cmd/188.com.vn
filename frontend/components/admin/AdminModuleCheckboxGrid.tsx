'use client';

import { ADMIN_MODULE_LABELS } from '@/lib/admin-modules';
import { getAdminStaffModulePickerGroups } from '@/lib/admin-nav-config';

type Props = {
  selected: string[];
  onToggle: (moduleKey: string) => void;
  disabled?: boolean;
};

/** Checkbox gán quyền mục — nhóm giống sidebar admin. */
export default function AdminModuleCheckboxGrid({ selected, onToggle, disabled }: Props) {
  const groups = getAdminStaffModulePickerGroups();

  return (
    <div className="space-y-4">
      {groups.map((group) => (
        <div key={group.title}>
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
            {group.title}
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-2">
            {group.moduleKeys.map((key) => (
              <label
                key={key}
                className="flex items-start gap-2 text-xs text-gray-800 cursor-pointer rounded-lg border border-gray-100 bg-white px-2 py-1.5 hover:border-gray-200"
              >
                <input
                  type="checkbox"
                  checked={selected.includes(key)}
                  onChange={() => onToggle(key)}
                  disabled={disabled}
                  className="mt-0.5 rounded border-gray-300"
                />
                <span>{ADMIN_MODULE_LABELS[key] || key}</span>
              </label>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
