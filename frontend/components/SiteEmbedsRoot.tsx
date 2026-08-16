import type { PublicSiteEmbeds } from '@/lib/site-embeds-public';
import SiteEmbedsRootClient from '@/components/SiteEmbedsRoot.client';

/**
 * Dynamic import: pixel/chat inject sau idle (không chặn LCP). Stub gtag/fbq vẫn SSR trong head.
 * `whenFbqReady` đợi fbq tới 20s nên sự kiện sau hydrate không mất.
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
