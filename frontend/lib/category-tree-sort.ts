import type { CategoryLevel1, CategoryLevel2, CategoryLevel3 } from '@/types/api';

type GenderPriority = 'nam' | 'nu' | null;

function textGenderRank(name: string, priority: GenderPriority): number {
  if (!priority) return 1;
  const n = (name || '').trim();
  if (!n) return 1;
  const hasNam = /\bnam\b/i.test(n) || / nam$/i.test(n);
  const hasNu = /\b(nu|nữ)\b/i.test(n) || / nữ$/i.test(n);
  if (priority === 'nam') {
    if (hasNam && !hasNu) return 0;
    if (hasNu && !hasNam) return 2;
    return 1;
  }
  if (hasNu && !hasNam) return 0;
  if (hasNam && !hasNu) return 2;
  return 1;
}

/** Chuẩn hóa suffix API: Nam | Nữ | null */
export function genderSuffixToPriority(suffix: string | null | undefined): GenderPriority {
  const s = (suffix || '').trim().toLowerCase();
  if (s === 'nam' || s === 'male' || s === 'm') return 'nam';
  if (s === 'nu' || s === 'nữ' || s === 'female' || s === 'f') return 'nu';
  return null;
}

function sortByGender<T extends { name: string }>(nodes: T[], priority: GenderPriority): T[] {
  const indexed = nodes.map((node, i) => ({ node, i }));
  indexed.sort((a, b) => {
    const ra = textGenderRank(a.node.name, priority);
    const rb = textGenderRank(b.node.name, priority);
    if (ra !== rb) return ra - rb;
    if (a.i !== b.i) return a.i - b.i;
    return a.node.name.localeCompare(b.node.name, 'vi');
  });
  return indexed.map(({ node }) => node);
}

/** Sắp L1 → L2 → L3: danh mục khớp giới ưu tiên lên trước (ổn định trong từng nhóm). */
export function sortCategoryLevel1Tree(
  tree: CategoryLevel1[],
  genderSuffix: string | null | undefined,
): CategoryLevel1[] {
  const priority = genderSuffixToPriority(genderSuffix);
  if (!priority || tree.length === 0) return tree;

  const l1Sorted = sortByGender(tree, priority);
  return l1Sorted.map((l1) => {
    const l2Sorted = sortByGender(l1.children || [], priority);
    return {
      ...l1,
      children: l2Sorted.map((l2) => ({
        ...l2,
        children: sortByGender(l2.children || [], priority),
      })),
    };
  });
}
