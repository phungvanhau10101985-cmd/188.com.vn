const GOOGLE_PUBLIC_KEY_PEM = `-----BEGIN PUBLIC KEY-----
MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAERUlUpxshr67EO66ZTX0Fpog0LEHc
nUnlSsIrOfroxTLu2XnigBK/lfYRxzQWq9K6nqsSjjYeea0T12r+y3nvqg==
-----END PUBLIC KEY-----`;

const token =
  'eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.eyJjIjoiVk5EIiwiZGMiOiJBQkNERUYiLCJkcCI6NSwiZXhwIjoxNzgxODYzMDYzLCJtIjoiNTY3MjEzODA5NyIsIm8iOiJBNjQxNjAzMjU3NjY2YTE4OE82MTEyIiwicCI6MTE0OTUwMH0.zYpoGw0a9Ylx9kKIo3znbgiqHwY_TN38u271H3f47eq49F_s7DsiMX1pun_j1K7BWfyMM30mERCqp4k_7V9voQ';

function base64UrlToBytes(input) {
  const pad = input.length % 4 === 0 ? '' : '='.repeat(4 - (input.length % 4));
  const b64 = input.replace(/-/g, '+').replace(/_/g, '/') + pad;
  return new Uint8Array(Buffer.from(b64, 'base64'));
}

const parts = token.split('.');
const b64 = GOOGLE_PUBLIC_KEY_PEM.replace(/-----[^-]+-----/g, '').replace(/\s/g, '');
const key = await crypto.subtle.importKey(
  'spki',
  Buffer.from(b64, 'base64'),
  { name: 'ECDSA', namedCurve: 'P-256' },
  false,
  ['verify'],
);
const signed = new TextEncoder().encode(`${parts[0]}.${parts[1]}`);
const ok = await crypto.subtle.verify(
  { name: 'ECDSA', hash: 'SHA-256' },
  key,
  base64UrlToBytes(parts[2]),
  signed,
);
const payload = JSON.parse(new TextDecoder().decode(base64UrlToBytes(parts[1])));
const prior = Math.round(payload.p / (1 - payload.dp / 100));
console.log(JSON.stringify({ verify: ok, price: payload.p, prior, dp: payload.dp }));
