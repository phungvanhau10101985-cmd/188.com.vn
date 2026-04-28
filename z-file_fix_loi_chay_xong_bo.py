# restore_backup.py (nếu cần)
import shutil
import os

# Restore từ backup cuối cùng
backup_file = "backend/backups/cart.py.backup_20260129_143000"
original_file = "backend/app/models/cart.py"
shutil.copy2(backup_file, original_file)