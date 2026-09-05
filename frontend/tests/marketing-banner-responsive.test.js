const fs = require('fs');
const path = require('path');

describe('marketing banner responsive contract', () => {
  const component = fs.readFileSync(
    path.join(__dirname, '..', 'components', 'home', 'MarketingBannerCarousel.tsx'),
    'utf8',
  );

  test('uses one full-width image without cropping on every viewport', () => {
    expect(component).toContain('className="block h-auto w-full"');
    expect(component).not.toContain('object-cover');
    expect(component).not.toContain('<picture');
    expect(component).not.toContain('srcSet=');
  });

  test('keeps birthday greeting outside the image', () => {
    expect(component).toContain('{active.greeting}');
    expect(component.indexOf('{active.greeting}')).toBeGreaterThan(
      component.indexOf('</Link>'),
    );
  });

  test('routes both campaigns to the age and gender recommendation group', () => {
    expect(component).toContain("const destination = '/#san-pham-cung-shop'");
    expect(component).not.toContain('/?category=deal');
    expect(component).not.toContain("const destination = '/kho-sale'");
  });

  test('provides loading, error, empty and image failure behavior', () => {
    expect(component).toContain('if (loading)');
    expect(component).toContain('if (error)');
    expect(component).toContain('if (!active) return null');
    expect(component).toContain('onError=');
  });
});
