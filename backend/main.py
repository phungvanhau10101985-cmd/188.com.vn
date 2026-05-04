# backend/main.py - FIXED VERSION WITH IMPORT/EXPORT DEBUG
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from datetime import datetime
from pathlib import Path
import logging
import uvicorn
import sys
import os
import traceback

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load config sớm để dùng cho CORS và docs
def _get_app_config():
    from app.core.config import settings
    return settings

_settings = _get_app_config()


def _setup_file_logging() -> None:
    """Ghi log ra LOG_FILE (.env) — trước đây biến này tồn tại nhưng không được gắn handler."""
    rel = (getattr(_settings, "LOG_FILE", "") or "").strip()
    if not rel:
        return
    backend_root = Path(__file__).resolve().parent
    path = Path(rel)
    if not path.is_absolute():
        path = backend_root / path
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    log_file = str(path.resolve())
    root = logging.getLogger()
    for h in root.handlers:
        if isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", None):
            try:
                if os.path.abspath(str(h.baseFilename)) == log_file:
                    return
            except (TypeError, ValueError):
                pass
    lvl_name = (getattr(_settings, "LOG_LEVEL", None) or "INFO").upper()
    level = getattr(logging, lvl_name, logging.INFO)
    root.setLevel(level)
    fh = logging.FileHandler(path, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    root.addHandler(fh)


_setup_file_logging()

# Production: tắt Swagger/ReDoc nếu cần (đặt DISABLE_DOCS=true trong .env)
_docs_url = None if os.getenv("DISABLE_DOCS", "").lower() == "true" else "/docs"
_redoc_url = None if os.getenv("DISABLE_DOCS", "").lower() == "true" else "/redoc"
_openapi_url = None if os.getenv("DISABLE_DOCS", "").lower() == "true" else "/openapi.json"

app = FastAPI(
    title="188.com.vn API",
    description="E-commerce Platform API",
    version="2.0.0",
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url=_openapi_url,
    # Tắt redirect /products → /products/ (Starlette mặc định bật) — qua proxy/ngrok dễ 502
    redirect_slashes=False,
)

# KHÔNG đăng ký lặp products/categories/cart/user_behavior ở đây:
# cùng các router được load lại trong load_api_routes() → trùng route, Starlette/ redirect 308, proxy Next 502.
# Mọi route API qua load_api_routes() + block products riêng bên dưới.

# THÊM PHẦN NÀY: Serve static files
import os
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# CORS: dùng BACKEND_CORS_ORIGINS từ .env khi deploy (không dùng allow_origins=["*"])
_cors_kwargs = dict(
    allow_origins=_settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
if getattr(_settings, "BACKEND_CORS_ORIGIN_REGEX", None):
    _cors_kwargs["allow_origin_regex"] = _settings.BACKEND_CORS_ORIGIN_REGEX
app.add_middleware(CORSMiddleware, **_cors_kwargs)

# ========== DATABASE INITIALIZATION ==========
def init_database_tables():
    """Tạo database tables nếu chưa có."""
    strict = os.getenv("DEPLOY_STRICT_DB_INIT", "").strip().lower() in ("1", "true", "yes")
    try:
        from sqlalchemy import create_engine
        from app.db.base import Base
        from app.core.config import settings

        print("🔧 CHECKING DATABASE TABLES...")
        url = settings.DATABASE_URL
        kwargs = {}
        if not url.startswith("sqlite"):
            kwargs = dict(
                pool_pre_ping=True,
                pool_size=settings.DATABASE_POOL_SIZE,
                max_overflow=settings.DATABASE_MAX_OVERFLOW,
                pool_recycle=settings.DATABASE_POOL_RECYCLE,
                pool_timeout=settings.DATABASE_POOL_TIMEOUT,
            )
        else:
            kwargs = dict(connect_args={"check_same_thread": False})
        engine = create_engine(url, **kwargs)
        
        # Import all models so they register with Base.metadata
        from app import models  # noqa: F401
        _ = models
        
        # Kiểm tra tables hiện có
        existing_tables = Base.metadata.tables.keys()
        print(f"📊 Existing tables in metadata: {list(existing_tables)}")
        
        # Tạo tables nếu chưa có
        Base.metadata.create_all(bind=engine)
        print("✅ Database tables ready!")
        # Chạy migrations (thêm cột mới vào bảng đã tồn tại, ví dụ order_code)
        try:
            from app.db.migrations import run_migrations
            run_migrations()
        except Exception as mig_err:
            print(f"⚠️  Migrations warning: {mig_err}")
            if strict:
                raise
        try:
            from app.db.session import SessionLocal
            from app.crud.site_embed_code import ensure_default_embed_codes, deactivate_nanoai_try_on_embeds
            from app.crud import shop_video_fab as shop_video_fab_crud
            _s = SessionLocal()
            try:
                shop_video_fab_crud.get_or_create_singleton(_s)
                n = ensure_default_embed_codes(_s)
                tn = deactivate_nanoai_try_on_embeds(_s)
                if n:
                    print(f"✅ Seeded {n} site embed placeholders (Google/Facebook/Zalo…)")
                if tn:
                    print(f"✅ Removed {tn} NanoAI try-on embed row(s)")
            finally:
                _s.close()
        except Exception as seed_err:
            print(f"⚠️  Site embed defaults warning: {seed_err}")
        
    except Exception as e:
        print(f"⚠️  Database initialization warning: {e}")
        print("   Some features may not work without proper database setup.")
        if strict:
            raise RuntimeError(f"DEPLOY_STRICT_DB_INIT: database init failed: {e}") from e

# ========== LOAD API ROUTES ==========
def load_api_routes():
    """Load API routes với error handling"""
    print("\n🔧 LOADING API ROUTES...")
    
    routes_config = [
        ("auth", "/auth", "authentication"),
        ("addresses", "/addresses", "addresses"),
        ("bank_accounts", "/bank-accounts", "bank-accounts"),
        ("admin", "/admin", "admin"),
        ("embed_codes", "/embed-codes", "embed-codes"),
        ("shop_video_fab", "/shop-video-fab", "shop-video-fab"),
        ("categories", "/categories", "categories"),
        ("category_seo", "/category-seo", "category-seo"),
        ("taxonomy_admin", "/taxonomy", "taxonomy-admin"),
        ("seo_clusters", "/seo-clusters", "seo-clusters"),
        ("cart", "/cart", "cart"),
        ("orders", "/orders", "orders"),
        ("import_export", "/import-export", "import-export"),  # ĐẶC BIỆT DEBUG
        ("user_behavior", "/user-behavior", "user-behavior"),
        ("analytics", "/analytics", "analytics"),
        ("nanoai_search", "/nanoai", "nanoai"),
        ("sepay_webhook", "/sepay", "sepay"),
        ("debug", "/debug", "debug"),
        ("fallback", "/fallback", "fallback"),
        ("filters", "/filters", "filters"),
        ("product_questions", "/product-questions", "product-questions"),
        ("product_reviews", "/product-reviews", "product-reviews"),
        ("loyalty", "/loyalty", "loyalty"),
        ("notifications", "/notifications", "notifications"),
        ("push", "/push", "push"),
    ]
    
    loaded = []
    failed = []
    
    for module_name, prefix, tag in routes_config:
        try:
            print(f"\n📦 {'='*50}")
            print(f"📦 ATTEMPTING TO LOAD: {module_name.upper()}")
            print(f"   Import path: app.api.endpoints.{module_name}")
            
            # Import module với đầy đủ path
            full_module_path = f"app.api.endpoints.{module_name}"
            print(f"   Full path: {full_module_path}")
            
            # Import thử
            module = __import__(full_module_path, fromlist=["router"])
            print(f"   ✓ Module imported successfully: {module}")
            
            # Kiểm tra attributes
            print(f"   Module file: {module.__file__}")
            print(f"   Available attributes: {[a for a in dir(module) if not a.startswith('_')][:10]}...")
            
            if hasattr(module, 'router'):
                print(f"   ✓ Found router attribute")
                
                # Include router
                full_prefix = f"/api/v1{prefix}"
                app.include_router(module.router, prefix=full_prefix, tags=[tag])
                loaded.append((module_name, full_prefix))
                print(f"  ✅ {module_name}: {full_prefix}")
                
                # Test thêm: print router endpoints
                try:
                    routes = module.router.routes
                    print(f"   Routes in {module_name}: {len(routes)} endpoints")
                    for route in routes[:3]:  # Show first 3
                        if hasattr(route, 'path'):
                            print(f"     - {route.path}")
                except:
                    pass
                    
            else:
                error_msg = f"No router attribute in module!"
                print(f"  ❌ {module_name}: {error_msg}")
                failed.append((module_name, error_msg))
                
        except ImportError as e:
            error_msg = f"Import error: {str(e)}"
            print(f"  ❌ {module_name}: {error_msg}")
            print(f"     Traceback:")
            traceback.print_exc()
            failed.append((module_name, error_msg))
            
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            print(f"  ❌ {module_name}: {error_msg}")
            print(f"     Traceback:")
            traceback.print_exc()
            failed.append((module_name, error_msg))
    
    # Thử load products riêng (có thể lỗi)
    print(f"\n📦 {'='*50}")
    print("📦 ATTEMPTING TO LOAD: PRODUCTS")
    try:
        module = __import__("app.api.endpoints.products", fromlist=["router"])
        if hasattr(module, 'router'):
            app.include_router(module.router, prefix="/api/v1/products", tags=["products"])
            loaded.append(("products", "/api/v1/products"))
            print(f"  ✅ products: /api/v1/products")
        else:
            print(f"  ⚠️  products: No router attribute")
            failed.append(("products", "No router attribute"))
    except Exception as e:
        print(f"  ⚠️  products: Skipping - {str(e)[:80]}")
        failed.append(("products", str(e)))
    
    # Alias SePay: nhiều deploy gửi toàn bộ /api/* vào FastAPI — SePay đăng ký .../api/sepay-webhook (Next)
    # thì vẫn cần endpoint này trên backend.
    try:
        from app.api.endpoints import sepay_webhook as _sepay_wh

        app.add_api_route(
            "/api/sepay-webhook",
            _sepay_wh.sepay_webhook_public_path,
            methods=["POST"],
            tags=["sepay"],
        )
        loaded.append(("sepay_webhook_alias", "/api/sepay-webhook"))
        print("  ✅ sepay_webhook_alias: POST /api/sepay-webhook")
    except Exception as e:
        print(f"  ⚠️  sepay_webhook_alias: {str(e)[:80]}")
        failed.append(("sepay_webhook_alias", str(e)))
    
    print(f"\n📊 {'='*50}")
    print(f"📊 ROUTE LOADING SUMMARY")
    print(f"   ✅ Loaded: {len(loaded)} routes")
    print(f"   ❌ Failed: {len(failed)} routes")
    
    if loaded:
        print(f"\n🎯 LOADED ENDPOINTS:")
        for name, path in loaded:
            print(f"   🌐 {path}")
    
    if failed:
        print(f"\n⚠️  FAILED TO LOAD:")
        for name, error in failed:
            print(f"   ❌ {name}: {error[:80]}")
    
    print(f"{'='*50}\n")
    return loaded, failed

@app.on_event("startup")
async def startup_event():
    print("\n" + "="*60)
    print("🚀 188.com.vn API Server Starting...")
    print("="*60)
    
    # Initialize database
    init_database_tables()
    
    # Load routes với debug
    loaded_routes, failed_routes = load_api_routes()
    
    # Hiển thị import/export endpoints đặc biệt
    print("🔍 IMPORT/EXPORT ENDPOINTS (if loaded):")
    for name, path in loaded_routes:
        if "import-export" in name or "import" in name or "export" in name:
            print(f"   📤 {path}")
    
    print("\n📌 IMPORTANT ENDPOINTS TO TEST:")
    print("   POST   /api/v1/import-export/import/excel          (đồng bộ, cần Bearer admin)")
    print("   POST   /api/v1/import-export/import/excel/async    (202 + job_id)")
    print("   GET    /api/v1/import-export/import/excel/job/{job_id}")
    print("   GET    /api/v1/import-export/export/excel")
    print("   GET    /api/v1/import-export/export/sample")
    print("   GET    /api/v1/import-export/download/sample       (file mẫu import — UI admin)")
    print("   GET    /api/v1/import-export/download/latest-export")
    
    from app.core.config import settings as _startup_settings
    _db_url = (_startup_settings.DATABASE_URL or "").lower()
    if _db_url.startswith("postgresql"):
        _db_quick = "PostgreSQL (DATABASE_URL)"
    elif _db_url.startswith("sqlite"):
        _db_quick = "SQLite (DATABASE_URL)"
    else:
        _db_quick = "Configured via DATABASE_URL"

    _p = _startup_settings.SERVER_PORT
    print("\n📌 QUICK ACCESS:")
    print(f"   📄 API Documentation: http://localhost:{_p}/docs")
    print(f"   📊 Database: {_db_quick}")
    print(f"   🏃 Server: http://localhost:{_p}")
    print("="*60)

# ========== BASIC ROUTES ==========
@app.get("/")
async def root():
    return {
        "app": "188.com.vn API",
        "version": "2.0.0",
        "status": "running",
        "timestamp": datetime.now().isoformat(),
        "docs": "/docs",
        "health": "/health"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/api")
async def api_root():
    return {
        "api": "v1",
        "endpoints": [
            {"auth": "/api/v1/auth"},
            {"products": "/api/v1/products"},
            {"categories": "/api/v1/categories"},
            {"cart": "/api/v1/cart"},
            {"orders": "/api/v1/orders"},
            {"import-export": "/api/v1/import-export"},
            {"user-behavior": "/api/v1/user-behavior"}
        ]
    }

@app.get("/api/v1")
async def api_v1_root():
    return {
        "api": "v1",
        "status": "active",
        "endpoints": {
            "import_export": {
                "import_sync": "POST /api/v1/import-export/import/excel",
                "import_async": "POST /api/v1/import-export/import/excel/async",
                "import_job": "GET /api/v1/import-export/import/excel/job/{job_id}",
                "export": "GET /api/v1/import-export/export/excel",
                "sample": "GET /api/v1/import-export/export/sample",
                "template_download": "GET /api/v1/import-export/download/sample",
                "latest": "GET /api/v1/import-export/download/latest-export",
            },
            "products": "GET /api/v1/products",
            "categories": "GET /api/v1/categories",
            "auth": "POST /api/v1/auth/login"
        }
    }

# ========== TEST ENDPOINT FOR IMPORT/EXPORT ==========
@app.post("/api/test-import")
async def test_import_endpoint():
    """Test endpoint để kiểm tra import/export system"""
    return {
        "status": "test",
        "import_endpoint": "POST /api/v1/import-export/import/excel",
        "note": "Use this to verify endpoint exists"
    }

# ========== ERROR HANDLING ==========
@app.exception_handler(404)
async def not_found_exception_handler(request, exc):
    """Custom 404 handler hiển thị available endpoints"""
    from fastapi.responses import JSONResponse
    
    paths = sorted(
        {route.path for route in app.routes if hasattr(route, "path") and route.path},
    )
    return JSONResponse(
        status_code=404,
        content={
            "error": "Endpoint not found",
            "requested": str(request.url),
            "available_paths_sample": paths[:80],
            "docs": "/docs",
            "note": "Đầy đủ trong OpenAPI /docs. Import async: POST /api/v1/import-export/import/excel/async — poll GET /api/v1/import-export/import/excel/job/{job_id}",
        },
    )

if __name__ == "__main__":
    from app.core.config import settings as _cli_settings
    _port = _cli_settings.SERVER_PORT
    print("🔄 Starting server with debug mode...")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=_port,
        reload=True,
        log_level="debug",
    )