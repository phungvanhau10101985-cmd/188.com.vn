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
      args: '-m uvicorn main:app --host 127.0.0.1 --port 8001 --timeout-graceful-shutdown 5',
      env: {
        SERVER_PORT: '8001',
        RUN_DB_INIT_ON_STARTUP: '0',
        IMAGE_LOCALIZATION_JOB_RESUME_ON_STARTUP: 'true',
        // Postgres max_connections=100 trên VPS nanoai — 15+20=35 vẫn còn dư địa lớn cho
        // các app khác (thu-do-online, worksheet-worker...). Tăng từ 10+15=25 vì admin bấm
        // nhiều thao tác nặng liên tiếp (tải danh sách + lọc + job ảnh...) từng chạm ngưỡng cũ.
        DATABASE_POOL_SIZE: '15',
        DATABASE_MAX_OVERFLOW: '20',
        DATABASE_POOL_TIMEOUT: '8',
        DATABASE_POOL_RECYCLE: '1800',
        DATABASE_IDLE_IN_TRANSACTION_TIMEOUT_SECONDS: '35',
        DATABASE_STATEMENT_TIMEOUT_SECONDS: '0',
        DATABASE_POOL_RELIEF_ENABLED: 'true',
        DATABASE_POOL_RELIEF_INTERVAL_SECONDS: '15',
        DATABASE_POOL_RELIEF_MIN_IDLE_SECONDS: '22',
        DATABASE_POOL_RELIEF_AGGRESSIVE_MIN_IDLE_SECONDS: '18',
        DATABASE_POOL_RELIEF_TRIGGER_IDLE_COUNT: '14',
        DATABASE_POOL_SELF_HEAL_ENABLED: 'true',
        DATABASE_POOL_SELF_HEAL_INTERVAL_SECONDS: '15',
        DATABASE_ACTIVE_QUERY_KILL_SECONDS: '45',
        DATABASE_POOL_RELIEF_INTERVAL_SECONDS: '10',
        DATABASE_POOL_RELIEF_TRIGGER_IDLE_COUNT: '10',
        DATABASE_POOL_SELF_HEAL_PROBE_TIMEOUT_SECONDS: '3',
        // A transient probe failure during a heavy admin operation must not
        // terminate the only API worker. Restart only after three failed
        // recovery cycles.
        DATABASE_POOL_SELF_HEAL_MAX_FAILURES: '3',
        EMS_TRACKING_INTERNAL_SCHEDULER_ENABLED: 'false',
        LEGACY_OOS_DEEPSEEK_ENABLED: 'false',
        GROUP_LISTING_SKIP_SLOW_SLUG_POOL: 'true',
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
      /** Tránh API treo sau nhiều giờ (RAM phình → pool DB kẹt). 3.5G: dưới mức treo ~3.8G trên VPS nanoai. */
      max_memory_restart: '3500M',
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
    },
  ],
};
