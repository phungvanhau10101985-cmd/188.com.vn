import type { PublicSiteEmbeds } from '@/lib/site-embeds-public';
import SiteEmbedsRootClient from '@/components/SiteEmbedsRoot.client';

/**
 * Client component được import trực tiếp (không dynamic) để `fbq` được inject ngay tick hydrate.
 * Dynamic tách chunk khiến pixel chậm hơn trang con → `whenFbqReady` hết 4s trước khi có `fbq`, không còn sự kiện.
 */
export default function SiteEmbedsRoot({ embeds }: { embeds: PublicSiteEmbeds }) {
  return <SiteEmbedsRootClient embeds={embeds} />;
}
