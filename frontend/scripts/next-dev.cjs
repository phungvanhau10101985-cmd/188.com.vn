/**
 * Chạy Next dev trên cổng 3001 mặc định, có thể truyền `-p <port>`.
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

const args = process.argv.slice(2);
const portArgIdx = args.findIndex((x) => x === '-p' || x === '--port');
const port = portArgIdx >= 0 && args[portArgIdx + 1] ? args[portArgIdx + 1] : process.env.PORT || '3001';
const passthrough =
  portArgIdx >= 0 ? args.filter((_, idx) => idx !== portArgIdx && idx !== portArgIdx + 1) : args;
const nextCli = resolveNextCli();
const result = spawnSync(process.execPath, [nextCli, 'dev', '-p', port, '--webpack', ...passthrough], {
  cwd: root,
  stdio: 'inherit',
  env: {
    ...process.env,
    PORT: port,
    /** Khớp backend: `SERVER_PORT` mặc định 8001 trong `backend/app/core/config.py`. */
    API_INTERNAL_ORIGIN: process.env.API_INTERNAL_ORIGIN || 'http://127.0.0.1:8001',
  },
});

process.exit(result.status === null ? 1 : result.status);
