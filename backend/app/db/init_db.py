from app.db.session import engine, SessionLocal
from app.models.product import Base, Product
from app.models.category import Category
from app.models.loyalty import LoyaltyTier
import json

def init_db():
    Base.metadata.create_all(bind=engine)
    print("✅ Đã tạo bảng database thành công!")

if __name__ == "__main__":
    init_db()
