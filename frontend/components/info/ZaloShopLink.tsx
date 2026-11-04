import { fetchPublicSiteEmbeds, resolveZaloClickUrl } from '@/lib/site-embeds-public';

export default async function ZaloShopLink({ className }: { className?: string }) {
  const embeds = await fetchPublicSiteEmbeds();
  const url = resolveZaloClickUrl(embeds);
  const personal =
    embeds.zaloOpen === 'personal' ||
    (embeds.zaloOpen !== 'oa' && Boolean(embeds.zaloPersonalUrl) && url === embeds.zaloPersonalUrl);
  return (
    <>
      <strong className="text-zinc-800">{personal ? 'Zalo cá nhân:' : 'Zalo Official Account:'}</strong>{' '}
      <a href={url} className={className} rel="noopener noreferrer" target="_blank">
        {url}
      </a>
    </>
  );
}
