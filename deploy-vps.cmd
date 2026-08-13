@echo off
chcp 65001 >nul
REM Canonical VPS deploy for 188.com.vn. Always use these two commands on the server.
REM Do not skip update-vps.sh, do not invent a shorter pm2-only / git-pull-only path.
echo.
echo === Deploy 188.com.vn tren VPS (copy len SSH) ===
echo Day la quy trinh BAT BUOC moi lan deploy production.
echo.
echo cd /var/www/188.com.vn ^&^& git pull origin main
echo DEPLOY_SKIP_GIT=1 DEPLOY_STOP_PM2_BEFORE_BUILD=1 DEPLOY_SKIP_LINT=1 NODE_BUILD_HEAP_MB=3072 bash ./deploy/update-vps.sh main
echo.
echo (Khong can verify-shipping-ops-api.sh — update-vps da kiem tra health + operations-stats)
echo.
pause
