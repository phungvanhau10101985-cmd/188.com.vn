import type { SsrHeadScriptSpec } from '@/lib/site-embed-head-ssr';

type Props = { specs: SsrHeadScriptSpec[] };

/**
 * Script từ API embed — render SSR trong &lt;head&gt; (có trong HTML gốc) để local/production khớp preview admin.
 * Next vẫn merge `export const metadata` vào cùng head.
 */
export default function SiteEmbedsSsrScripts({ specs }: Props) {
  if (!specs.length) return null;

  return (
    <>
      {specs.map((s, i) => {
        const key = `188-ssr-${i}`;
        if (s.src) {
          return (
            <script
              key={key}
              src={s.src}
              async={s.async || undefined}
              defer={s.defer || undefined}
              data-188-ssr-head="1"
            />
          );
        }
        return (
          <script
            key={key}
            data-188-ssr-head="1"
            dangerouslySetInnerHTML={{ __html: s.inline ?? '' }}
          />
        );
      })}
    </>
  );
}
