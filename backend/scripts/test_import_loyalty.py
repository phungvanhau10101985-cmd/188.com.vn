import sys
import os

# Add backend directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

try:
    from app.api.endpoints import loyalty
    print("✅ Import loyalty success")
    print(f"Router: {loyalty.router}")
except Exception as e:
    print(f"❌ Import loyalty failed: {e}")
    import traceback
    traceback.print_exc()
