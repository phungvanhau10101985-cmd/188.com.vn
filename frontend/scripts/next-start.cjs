/** Production: luôn cổng 3001 — npm start */
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
  if (!fs.existsSync(binPath)) throw new Error(`Thiếu Next CLI: ${binPath}`);
  return binPath;
}

const nextCli = resolveNextCli();
const result = spawnSync(process.execPath, [nextCli, 'start', '-p', '3001'], {
  cwd: root,
  stdio: 'inherit',
  env: { ...process.env, PORT: '3001' },
});

process.exit(result.status === null ? 1 : result.status);
