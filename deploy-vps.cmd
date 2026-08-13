@echo off
chcp 65001 >nul
REM Canonical VPS deploy for 188.com.vn. Always this one command when user says upgit deploy.
REM Script tự git pull — không DEPLOY_SKIP_GIT, không pm2 restart tay.
echo.
echo === Deploy 188.com.vn tren VPS (copy len SSH) ===
echo Day la quy trinh BAT BUOC moi lan upgit deploy.
echo.
echo cd /var/www/188.com.vn ^&^& DEPLOY_STOP_PM2_BEFORE_BUILD=1 DEPLOY_SKIP_LINT=1 NODE_BUILD_HEAP_MB=3072 bash ./deploy/update-vps.sh main
echo.
echo (Khong can verify-shipping-ops-api.sh — update-vps da kiem tra health + operations-stats)
echo.
pause
