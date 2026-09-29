from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.order import Order, OrderStatus, PaymentStatus, DepositType
from app.crud.order import get_order_stats
from app.schemas.order import AdminOrderStats


def test_get_order_stats_deposited_metrics():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[Order.__table__])
    TestingSessionLocal = sessionmaker(bind=engine)
    db = TestingSessionLocal()

    try:
        now = datetime.now(timezone.utc)

        # 1. Normal COD order (không cọc)
        o1 = Order(
            order_code="DH101",
            customer_name="Khach 1",
            customer_phone="0901234567",
            customer_address="HN",
            total_amount=Decimal("500000"),
            requires_deposit=False,
            deposit_paid=Decimal("0"),
            status=OrderStatus.SHIPPING.value,
            payment_status=PaymentStatus.PENDING.value,
            created_at=now,
        )

        # 2. Đơn cần cọc nhưng đang chờ cọc
        o2 = Order(
            order_code="DH102",
            customer_name="Khach 2",
            customer_phone="0901234568",
            customer_address="HCM",
            total_amount=Decimal("1000000"),
            requires_deposit=True,
            deposit_amount=Decimal("300000"),
            deposit_paid=Decimal("0"),
            status=OrderStatus.WAITING_DEPOSIT.value,
            payment_status=PaymentStatus.PENDING.value,
            created_at=now,
        )

        # 3. Đơn đã cọc 30% (đang xử lý / processing)
        o3 = Order(
            order_code="DH103",
            customer_name="Khach 3",
            customer_phone="0901234569",
            customer_address="DN",
            total_amount=Decimal("2000000"),
            requires_deposit=True,
            deposit_amount=Decimal("600000"),
            deposit_paid=Decimal("600000"),
            deposit_paid_at=now,
            status=OrderStatus.PROCESSING.value,
            payment_status=PaymentStatus.DEPOSIT_PAID.value,
            created_at=now,
        )

        # 4. Đơn đã cọc 100% (chờ gửi hàng / confirmed)
        o4 = Order(
            order_code="DH104",
            customer_name="Khach 4",
            customer_phone="0901234570",
            customer_address="HP",
            total_amount=Decimal("1500000"),
            requires_deposit=True,
            deposit_amount=Decimal("1500000"),
            deposit_paid=Decimal("1500000"),
            deposit_paid_at=now,
            status=OrderStatus.CONFIRMED.value,
            payment_status=PaymentStatus.PAID.value,
            created_at=now,
        )

        # 5. Đơn có cọc nhưng đã bị hủy (cancelled) -> không tính vào đơn đã cọc
        o5 = Order(
            order_code="DH105",
            customer_name="Khach 5",
            customer_phone="0901234571",
            customer_address="CT",
            total_amount=Decimal("800000"),
            requires_deposit=True,
            deposit_amount=Decimal("240000"),
            deposit_paid=Decimal("240000"),
            status=OrderStatus.CANCELLED.value,
            payment_status=PaymentStatus.REFUNDED.value,
            created_at=now,
        )

        db.add_all([o1, o2, o3, o4, o5])
        db.commit()

        stats = get_order_stats(db, period="all")

        # Schema validation
        schema_stats = AdminOrderStats(**stats)
        # DH105 đã hủy: không tính vào doanh thu và tổng đơn
        assert schema_stats.total_orders == 4
        assert schema_stats.total_revenue == Decimal("5000000")
        assert schema_stats.orders_including_cancelled == 5

        # Deposited metrics: o3 (2tr, cọc 600k) + o4 (1.5tr, cọc 1.5tr) = 2 đơn, 3.5tr doanh thu, 2.1tr tiền cọc
        assert schema_stats.deposited_orders == 2
        assert schema_stats.deposited_revenue == Decimal("3500000")
        assert schema_stats.deposited_amount == Decimal("2100000")
        assert schema_stats.waiting_deposit_orders == 1
        assert schema_stats.cancelled_orders == 1

    finally:
        db.close()
