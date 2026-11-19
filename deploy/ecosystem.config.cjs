/**
 * PM2 — 188.com.vn (copy lên VPS hoặc pm2 start deploy/ecosystem.config.cjs)
 *
 * Trên VPS:
 *   cd /var/www/188.com.vn
 *   pm2 start deploy/ecosystem.config.cjs
 *   pm2 save
 */
const path = require('path');

const ROOT = path.join(__dirname, '..');
const BACKEND = path.join(ROOT, 'backend');
const FRONTEND = path.join(ROOT, 'frontend');

module.exports = {
  apps: [
    {
      name: '188-api',
      cwd: BACKEND,
      script: path.join(BACKEND, '.venv/bin/python'),
      // Bound graceful shutdown so PM2 can forcibly replace an API instance
      // that is waiting on a stuck request or Starlette background task.
      args: '-m uvicorn main:app --host 127.0.0.1 --port 8001 --workers 2 --timeout-graceful-shutdown 5',
      env: {
        SERVER_PORT: '8001',
        UVICORN_WORKERS: '2',
        RUN_DB_INIT_ON_STARTUP: '0',
        IMAGE_LOCALIZATION_JOB_RESUME_ON_STARTUP: 'false',
        IMAGE_LOCALIZATION_EMBEDDED_IN_API: 'false',
        // Chặn vòng OOM: worker ảnh ≤3.2GB AS; không resume khi MemAvailable < 2.8GB.
        IMAGE_LOCALIZATION_WORKER_MAX_AS_MB: '3200',
        IMAGE_LOCALIZATION_RESUME_MIN_AVAILABLE_MB: '2800',
        IMAGE_LOCALIZATION_MAX_AUTO_RESUME_COUNT: '6',
        // 25MP/batch thay 70MP — giảm spike RAM khi OCR merge trên VPS 11GB.
        IMAGE_LOCALIZATION_MERGE_MAX_PIXELS: '25000000',
        // 2 uvicorn workers × (10+8)=18 → 36 conn API. Postgres max_connections=100,
        // còn chỗ cho thu-do / stock / imgloc. Không để 15+20=35 × 2 = 70.
        DATABASE_POOL_SIZE: '10',
        DATABASE_MAX_OVERFLOW: '8',
        DATABASE_POOL_TIMEOUT: '8',
        DATABASE_POOL_RECYCLE: '1800',
        DATABASE_IDLE_IN_TRANSACTION_TIMEOUT_SECONDS: '12',
        DATABASE_STATEMENT_TIMEOUT_SECONDS: '0',
        DATABASE_POOL_RELIEF_ENABLED: 'true',
        DATABASE_POOL_RELIEF_INTERVAL_SECONDS: '15',
        DATABASE_POOL_RELIEF_MIN_IDLE_SECONDS: '10',
        DATABASE_POOL_RELIEF_AGGRESSIVE_MIN_IDLE_SECONDS: '8',
        DATABASE_POOL_RELIEF_TRIGGER_IDLE_COUNT: '8',
        DATABASE_POOL_SELF_HEAL_ENABLED: 'true',
        DATABASE_POOL_SELF_HEAL_INTERVAL_SECONDS: '15',
        DATABASE_ACTIVE_QUERY_KILL_SECONDS: '45',
        DATABASE_POOL_RELIEF_INTERVAL_SECONDS: '10',
        DATABASE_POOL_RELIEF_TRIGGER_IDLE_COUNT: '8',
        DATABASE_POOL_SELF_HEAL_PROBE_TIMEOUT_SECONDS: '3',
        // A transient probe failure during a heavy admin operation must not
        // terminate the only API worker. Restart only after three failed
        // recovery cycles.
        DATABASE_POOL_SELF_HEAL_MAX_FAILURES: '3',
        EMS_TRACKING_INTERNAL_SCHEDULER_ENABLED: 'false',
        LEGACY_OOS_DEEPSEEK_ENABLED: 'false',
        GROUP_LISTING_SKIP_SLOW_SLUG_POOL: 'true',
        // Chromium tồn kho nguồn chạy ở 188-stock-worker, không trong process này.
        // OCR bản địa hóa ảnh chạy ở 188-imgloc-worker, không trong process này.
        SOURCE_STOCK_CHECK_ENABLED: 'true',
        SOURCE_STOCK_CHECK_RUN_DAEMON: 'false',
        // Tắt warm nền phối đồ (NanoAI/ảnh). Khối /pdp-outfit vẫn đọc picks đã lưu.
        OUTFIT_VISUAL_WARM: '0',
        // Cào ưu tiên trình duyệt; nguồn hàng chạy tiếp khi cào xong. Không hoãn sang tối.
        HEAVY_WORK_GATE_ENABLED: '1',
        // CPU hoặc RAM cả máy ≥ 85% thì việc nền chờ khách. Mở lại khi cả hai ≤ 80%.
        HOST_PRESSURE_ENABLED: '1',
      },
      autorestart: true,
      max_restarts: 50,
      min_uptime: '10s',
      // Back off crash loops, but do not leave a failed API down after the
      // default PM2 restart cap is reached.
      exp_backoff_restart_delay: 100,
      // PM2 sends SIGKILL after this period if Uvicorn is still waiting for
      // open connections/background tasks during shutdown.
      kill_timeout: 8000,
      /** 2 worker ~1.6–1.8GB mỗi process + parent. 3.5G sẽ kill cả cụm ngay sau start. */
      max_memory_restart: '5500M',
    },
    {
      name: '188-web',
      cwd: FRONTEND,
      script: path.join(FRONTEND, 'scripts/next-start.cjs'),
      interpreter: 'node',
      env: {
        PORT: '3001',
        NODE_ENV: 'production',
        LAYOUT_CATEGORY_TREE_TIMEOUT_MS: '12000',
      },
      max_restarts: 10,
      min_uptime: '10s',
      restart_delay: 3000,
      max_memory_restart: '1536M',
    },
    {
      name: '188-stock-worker',
      cwd: BACKEND,
      script: path.join(BACKEND, '.venv/bin/python'),
      args: 'scripts/source_stock_worker.py',
      env: {
        SOURCE_STOCK_CHECK_ENABLED: 'true',
        SOURCE_STOCK_CHECK_RUN_DAEMON: 'true',
        // Pool nhỏ: scrape xong mới giữ connection. Không ăn pool 35 của API.
        DATABASE_POOL_SIZE: '2',
        DATABASE_MAX_OVERFLOW: '1',
        DATABASE_POOL_TIMEOUT: '8',
        DATABASE_POOL_RECYCLE: '1800',
        RUN_DB_INIT_ON_STARTUP: '0',
        IMAGE_LOCALIZATION_JOB_RESUME_ON_STARTUP: 'false',
        LISTING_IMPORT_QUEUE_RESUME_ON_STARTUP: 'false',
        HEAVY_WORK_GATE_ENABLED: '1',
        HOST_PRESSURE_ENABLED: '1',
      },
      autorestart: true,
      max_restarts: 30,
      min_uptime: '15s',
      exp_backoff_restart_delay: 2000,
      kill_timeout: 20000,
      max_memory_restart: '1200M',
    },
    {
      name: '188-imgloc-worker',
      cwd: BACKEND,
      script: path.join(BACKEND, '.venv/bin/python'),
      args: 'scripts/image_localization_worker.py',
      env: {
        // Script cũng ép resume=true. Pool nhỏ: job OCR không được chiếm pool 35 của API.
        IMAGE_LOCALIZATION_JOB_RESUME_ON_STARTUP: 'true',
        IMAGE_LOCALIZATION_EMBEDDED_IN_API: 'false',
        DATABASE_POOL_SIZE: '2',
        DATABASE_MAX_OVERFLOW: '2',
        DATABASE_POOL_TIMEOUT: '8',
        DATABASE_POOL_RECYCLE: '1800',
        RUN_DB_INIT_ON_STARTUP: '0',
        LISTING_IMPORT_QUEUE_RESUME_ON_STARTUP: 'false',
        SOURCE_STOCK_CHECK_RUN_DAEMON: 'false',
        OUTFIT_VISUAL_WARM: '0',
        HEAVY_WORK_GATE_ENABLED: '1',
        HOST_PRESSURE_ENABLED: '1',
      },
      autorestart: true,
      max_restarts: 30,
      min_uptime: '15s',
      exp_backoff_restart_delay: 2000,
      kill_timeout: 20000,
      max_memory_restart: '800M',
    },
  ],
};
