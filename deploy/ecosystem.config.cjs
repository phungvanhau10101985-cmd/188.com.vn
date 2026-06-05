/**
 * PM2 — 188.com.vn (copy lên VPS hoặc pm2 start deploy/ecosystem.config.cjs)
 *
 * Trên VPS:
 *   cd /var/www/188.com.vn
 *   pm2 start deploy/ecosystem.config.cjs
 *   pm2 save
 */
module.exports = {
  apps: [
    {
      name: '188-api',
      cwd: './backend',
      script: './.venv/bin/python',
      args: '-m uvicorn main:app --host 127.0.0.1 --port 8001',
      env: {
        SERVER_PORT: '8001',
        RUN_DB_INIT_ON_STARTUP: '0',
      },
      max_restarts: 10,
      min_uptime: '10s',
      restart_delay: 3000,
      /** Tránh API treo sau nhiều giờ (RAM phình → pool DB kẹt). 3.5G: dưới mức treo ~3.8G trên VPS nanoai. */
      max_memory_restart: '3500M',
    },
    {
      name: '188-web',
      cwd: './frontend',
      script: './scripts/next-start.cjs',
      interpreter: 'node',
      env: {
        PORT: '3001',
        NODE_ENV: 'production',
      },
      max_restarts: 10,
      min_uptime: '10s',
      restart_delay: 3000,
    },
  ],
};
