const fs = require('fs');
const path = require('path');

describe('Meta attribution contract', () => {
  const attr = fs.readFileSync(
    path.join(__dirname, '..', 'lib', 'meta-attribution.ts'),
    'utf8',
  );
  const capi = fs.readFileSync(
    path.join(__dirname, '..', 'lib', 'facebook-capi-client.ts'),
    'utf8',
  );
  const tracker = fs.readFileSync(
    path.join(__dirname, '..', 'components', 'AnalyticsTracker.tsx'),
    'utf8',
  );

  test('persists fbclid into first-party _fbc/_fbp', () => {
    expect(attr).toContain('persistMetaClickIds');
    expect(attr).toContain("params.get('fbclid')");
    expect(attr).toContain("writeCookie('_fbc'");
    expect(attr).toContain("writeCookie('_fbp'");
    expect(attr).toContain('getMetaAdsCheckoutFields');
    expect(attr).toContain('external_id');
  });

  test('CAPI client merges click IDs and advanced matching', () => {
    expect(capi).toContain("from '@/lib/meta-attribution'");
    expect(capi).toContain('getMetaCapiUserData()');
  });

  test('route tracker stores click IDs and logged-in PII', () => {
    expect(tracker).toContain('persistMetaClickIds()');
    expect(tracker).toContain('patchMetaAdvancedMatching');
    expect(tracker).toContain('userId: user.id');
  });
});
