"""
backend/app/__init__.py - Main application package
"""

__version__ = "1.0.0"
__author__ = "188.com.vn"
__description__ = "E-commerce API Backend"

# Export các module chính
__all__ = [
    'models',
    'schemas', 
    'crud',
    'api',
    'core',
    'db'
]

print(f"✅ App package loaded: {__description__} v{__version__}")