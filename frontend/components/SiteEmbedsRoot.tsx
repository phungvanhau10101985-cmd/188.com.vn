import type { PublicSiteEmbeds } from '@/lib/site-embeds-public';
import SiteEmbedsRootClient from '@/components/SiteEmbedsRoot.client';

/**
 * Client component được import trực tiếp (không dynamic) để `fbq` được inject ngay tick hydrate.
 * Dynamic tách chunk khiến pixel chậm hơn trang con → `whenFbqReady` hết 4s trước khi có `fbq`, không còn sự kiện.
 *
 * `headClientRemainders`: meta/link/HTML không phải script (script head đã SSR qua SiteEmbedsSsrScripts).
 */
export default function SiteEmbedsRoot({
  embeds,
  headClientRemainders,
}: {
  embeds: PublicSiteEmbeds;
  headClientRemainders: string[];
}) {
  return <SiteEmbedsRootClient embeds={embeds} headClientRemainders={headClientRemainders} />;
}
