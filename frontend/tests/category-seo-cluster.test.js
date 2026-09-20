const fs = require('fs');
const path = require('path');

describe('Category SEO cluster contract', () => {
  const sitemap = fs.readFileSync(
    path.join(__dirname, '..', 'lib', 'category-sitemap.ts'),
    'utf8',
  );
  const href = fs.readFileSync(
    path.join(__dirname, '..', 'lib', 'category-listing-href.ts'),
    'utf8',
  );
  const sitemapRoute = fs.readFileSync(
    path.join(__dirname, '..', 'app', 'sitemap.ts'),
    'utf8',
  );
  const nav = fs.readFileSync(
    path.join(__dirname, '..', 'components', 'Navigation.tsx'),
    'utf8',
  );

  test('sitemap flatten skips /danh-muc cat3 URLs', () => {
    expect(sitemap).toContain('Cấp 3 không index trên /danh-muc');
    expect(sitemap).not.toMatch(/out\.push\(\{\s*level:\s*3/);
  });

  test('cluster index requires products', () => {
    expect(href).toContain('MIN_CLUSTER_INDEX_PRODUCTS = 1');
    expect(href).toContain('isSeoClusterIndexable');
    expect(href).toContain("return `/c/${encodeURIComponent(cluster)}`");
  });

  test('public sitemap uses indexable helper', () => {
    expect(sitemapRoute).toContain('isSeoClusterIndexable');
  });

  test('menu cat3 links via cluster helper', () => {
    expect(nav).toContain('categoryLevel3HrefFromNode');
  });
});
