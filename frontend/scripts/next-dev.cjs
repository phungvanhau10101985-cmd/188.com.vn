/**
 * Chạy Next dev trên cổng 3001 mặc định, có thể truyền `-p <port>`.
 * Không tin PORT trong .env.local — hay gây nhầm vẫn ra 3000.
 *
 * Windows: cache dev (.next-run) trỏ junction sang %LOCALAPPDATA%\188-com-vn-next-dev
 * để giảm lỗi errno -4094 (Defender/indexer khóa file trong thư mục dự án).
 *
 * Dùng: npm run dev   hoặc   node scripts/next-dev.cjs
 *       npm run dev:clean  — xóa cache dev rồi chạy lại
 */
const { spawnSync } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');

const root = path.join(__dirname, '..');

function rmDirSafe(dir) {
  try {
    fs.rmSync(dir, { recursive: true, force: true, maxRetries: 3, retryDelay: 200 });
  } catch (e) {
    console.warn(`[next-dev] Không xóa được ${dir}: ${e.message}`);
  }
}

function unlinkSafe(linkPath) {
  try {
    if (!fs.existsSync(linkPath)) return;
    const st = fs.lstatSync(linkPath);
    if (st.isSymbolicLink()) fs.unlinkSync(linkPath);
    else rmDirSafe(linkPath);
  } catch (e) {
    console.warn(`[next-dev] Không gỡ được ${linkPath}: ${e.message}`);
  }
}

function windowsLocalDistTarget() {
  return path.join(os.homedir(), 'AppData', 'Local', '188-com-vn-next-dev');
}

/** Windows: .next-run là junction → AppData (tránh AV khóa chunk trên ổ dự án). */
function resolveDistDir() {
  if (process.env.NEXT_DIST_DIR) return process.env.NEXT_DIST_DIR;
  if (process.platform !== 'win32') return '.next-run';

  const link = path.join(root, '.next-run');
  const target = windowsLocalDistTarget();
  const cleanAll =
    process.env.NEXT_DEV_CLEAN === '1' ||
    process.env.NEXT_DEV_CLEAN === 'true' ||
    process.argv.includes('--clean');

  if (cleanAll) {
    unlinkSafe(link);
    rmDirSafe(target);
  }

  fs.mkdirSync(target, { recursive: true });

  if (!fs.existsSync(link)) {
    fs.symlinkSync(target, link, 'junction');
    console.log(`[next-dev] Windows: .next-run → ${target}`);
    return '.next-run';
  }

  const st = fs.lstatSync(link);
  if (st.isSymbolicLink()) return '.next-run';

  console.warn('[next-dev] Windows: chuyển cache .next-run sang AppData (giảm lỗi -4094)...');
  const backup = path.join(root, `.next-run.bak-${Date.now()}`);
  try {
    fs.renameSync(link, backup);
    fs.symlinkSync(target, link, 'junction');
    rmDirSafe(backup);
    console.log(`[next-dev] Cache dev: ${target}`);
  } catch (e) {
    console.warn(
      `[next-dev] Không chuyển được junction (dừng mọi npm run dev rồi thử npm run dev:clean): ${e.message}`,
    );
  }
  return '.next-run';
}

/** Tránh vòng lỗi UNKNOWN/open layout.js khi cache dev bị cắt cụt. */
function prepareDevDistDir(distDir) {
  const distRoot = path.join(root, distDir);
  const devDir = path.join(distRoot, 'dev');
  const layoutChunk = path.join(devDir, 'static', 'chunks', 'app', 'layout.js');
  const cleanAll =
    process.env.NEXT_DEV_CLEAN === '1' ||
    process.env.NEXT_DEV_CLEAN === 'true' ||
    process.argv.includes('--clean');

  if (cleanAll) return;

  if (!fs.existsSync(devDir)) return;

  const hasBuildManifest = fs.existsSync(path.join(devDir, 'build-manifest.json'));
  let layoutOk = false;
  if (fs.existsSync(layoutChunk)) {
    try {
      layoutOk = fs.statSync(layoutChunk).size > 1024;
    } catch (_) {
      layoutOk = false;
    }
  }
  if ((!layoutOk && !hasBuildManifest) || (fs.existsSync(layoutChunk) && !layoutOk)) {
    console.warn(
      `[next-dev] Cache dev hỏng (thiếu/cắt cụt layout.js) — xóa ${distDir}/dev rồi compile lại...`,
    );
    rmDirSafe(devDir);
  }
}

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
const distDir = resolveDistDir();
prepareDevDistDir(distDir);
const nextCli = resolveNextCli();
const result = spawnSync(
  process.execPath,
  [nextCli, 'dev', '-p', port, '--webpack', ...passthrough.filter((a) => a !== '--clean')],
  {
    cwd: root,
    stdio: 'inherit',
    env: {
      ...process.env,
      PORT: port,
      NEXT_DIST_DIR: distDir,
      /** Không ghi đè API_INTERNAL_ORIGIN ở đây — để .env.local / .env.development và next.config.js quyết định. */
    },
  },
);

process.exit(result.status === null ? 1 : result.status);
