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
  const pixel = fs.readFileSync(
    path.join(__dirname, '..', 'lib', 'meta-pixel.ts'),
    'utf8',
  );

  test('persists fbclid into first-party _fbc/_fbp', () => {
    expect(attr).toContain('persistMetaClickIds');
    expect(attr).toContain("params.get('fbclid')");
    expect(attr).toContain('metaSubdomainIndex');
    expect(attr).toContain('fbcMatchesFbclid');
    expect(attr).toContain('return `fb.${metaSubdomainIndex(host)}.${Date.now()}.${clid}`;');
    expect(attr).not.toContain('Math.floor(Date.now() / 1000)');
    expect(attr).toContain("writeCookie('_fbc'");
    expect(attr).toContain("writeCookie('_fbp'");
    expect(attr).toContain('getMetaAdsCheckoutFields');
    expect(attr).toContain('external_id');
    expect(attr).toContain('getGuestSessionId');
    expect(attr).toContain('installFbqEmptyEventGuard');
  });

  test('CAPI client merges click IDs and advanced matching', () => {
    expect(capi).toContain("from '@/lib/meta-attribution'");
    expect(capi).toContain('getMetaCapiUserData({');
    expect(capi).toContain('includeEmail?: boolean');
    expect(capi).toContain('includePhone?: boolean');
    expect(attr).toContain("if (opts?.includeEmail === false) delete pii.em");
    expect(attr).toContain("if (opts?.includePhone === false) delete pii.ph");
    expect(attr).toContain('isRealCustomerEmail');
    expect(attr).toContain('isRealCustomerPhone');
    expect(attr).toContain('hotro@188.com.vn');
    expect(attr).toContain('84968659836');
  });

  test('Pixel+CAPI share event_id and skip empty event names', () => {
    expect(pixel).toContain("firePixelAndCapi('PageView', {}, { keepalive: true })");
    expect(pixel).not.toContain("firePixelAndCapi('PageView', {}, { sendCapi: false })");
    expect(pixel).toContain("const name = String(eventName ?? '').trim()");
    expect(pixel).toContain("if (!name) return");
    expect(pixel).toContain("fbq(trackFn, name, customData, { eventID: eventId })");
    expect(pixel).toContain("event_id: eventId");
    expect(pixel).toContain("trackMetaAddToWishlist");
    expect(pixel).toContain("firePixelAndCapi('AddToWishlist'");
    expect(pixel).toContain('installFbqEmptyEventGuard');
  });

  test('route tracker stores click IDs and logged-in PII', () => {
    expect(tracker).toContain('persistMetaClickIds()');
    expect(tracker).toContain('patchMetaAdvancedMatching');
    expect(tracker).toContain('userId: user.id');
    expect(tracker).toContain("startsWith('/admin')");
    expect(tracker).toContain('trackMetaPageView(path)');
  });
});
