import dynamic from 'next/dynamic';
import type { PublicSiteEmbeds } from '@/lib/site-embeds-public';

/** Không SSR — chỉ mount trên trình duyệt để tránh Invalid hook call / React dispatcher null khi bundle xung đột. */
const SiteEmbedsRootClient = dynamic(() => import('@/components/SiteEmbedsRoot.client'), {
  ssr: false,
});

export default function SiteEmbedsRoot({ embeds }: { embeds: PublicSiteEmbeds }) {
  return <SiteEmbedsRootClient embeds={embeds} />;
}
