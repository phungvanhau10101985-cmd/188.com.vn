@echo off
chcp 65001 >nul
echo.
echo === Deploy 188.com.vn tren VPS (copy len SSH) ===
echo.
echo cd /var/www/188.com.vn ^&^& git pull origin main
echo DEPLOY_SKIP_GIT=1 DEPLOY_STOP_PM2_BEFORE_BUILD=1 DEPLOY_SKIP_LINT=1 NODE_BUILD_HEAP_MB=3072 bash ./deploy/update-vps.sh main
echo bash deploy/verify-shipping-ops-api.sh
echo.
pause
