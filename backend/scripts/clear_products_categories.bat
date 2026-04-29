@echo off
REM ============================================================
REM  Xoa SACH du lieu San pham + Danh muc + tuong tac (DEV LOCAL)
REM
REM  Cach dung:
REM    clear_products_categories.bat              -> hoi xac nhan
REM    clear_products_categories.bat --yes        -> bo qua confirm
REM    clear_products_categories.bat --dry-run    -> chi xem COUNT(*)
REM    clear_products_categories.bat --keep-views -> giu lai cart/views/search
REM ============================================================
chcp 65001 >nul
cd /d "%~dp0\.."
set PYTHONIOENCODING=utf-8
python scripts\clear_products_categories.py %*
set EC=%ERRORLEVEL%
if not "%EC%"=="0" pause
exit /b %EC%
