/**
 * Chạy Next dev luôn trên cổng 3001 (ép `-p 3001`).
 * Không tin PORT trong .env.local — hay gây nhầm vẫn ra 3000.
 *
 * Dùng: npm run dev   hoặc   node scripts/next-dev.cjs
 */
const { spawnSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const root = path.join(__dirname, '..');

function resolveNextCli() {
  const pkgJsonPath = require.resolve('next/package.json', { paths: [root] });
  const dir = path.dirname(pkgJsonPath);
  const pkg = require(pkgJsonPath);
  const rel = typeof pkg.bin === 'string' ? pkg.bin : pkg.bin?.next;
  if (!rel) throw new Error('Không tìm thấy bin trong package next');
  const binPath = path.resolve(dir, rel.replace(/^\.\//, ''));
  if (!fs.existsSync(binPath)) throw new Error(`Thiếu Next CLI: ${binPath} — chạy npm install trong frontend`);
  return binPath;
}

const nextCli = resolveNextCli();
const result = spawnSync(process.execPath, [nextCli, 'dev', '-p', '3001'], {
  cwd: root,
  stdio: 'inherit',
  env: {
    ...process.env,
    PORT: '3001',
    API_INTERNAL_ORIGIN: process.env.API_INTERNAL_ORIGIN || 'http://127.0.0.1:8001',
    NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8001/api/v1',
  },
});

process.exit(result.status === null ? 1 : result.status);
