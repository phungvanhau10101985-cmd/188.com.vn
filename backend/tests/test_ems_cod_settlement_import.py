"""Import COD mới không được xóa đối soát của mã không có trong file."""

from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.order_shipment import EmsCodSettlementBatch, EmsCodSettlementRow, EmsShippingRecord
from app.services.ems_cod_settlement_import import import_cod_settlement_excel

_FILENAME = "Phùng Văn Hậu (Shop 188) (9).xls"


def _workbook(payment_label: str, tracking: str, paid: int) -> bytes:
    return f"""<xml version>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Worksheet ss:Name="COD"><Table>
 <Row><Cell ss:Index="5"><Data ss:Type="String">{payment_label}</Data></Cell></Row>
 <Row><Cell><Data ss:Type="String">STT</Data></Cell></Row>
 <Row>
  <Cell><Data ss:Type="Number">1</Data></Cell>
  <Cell><Data ss:Type="String">H01010101</Data></Cell>
  <Cell><Data ss:Type="String">{tracking}</Data></Cell>
  <Cell><Data ss:Type="Number">{paid}</Data></Cell>
 </Row>
 </Table></Worksheet>
</Workbook>
""".encode()


def test_same_filename_keeps_codes_from_the_previous_file():
    engine = create_engine("sqlite://")
    EmsShippingRecord.__table__.create(engine)
    EmsCodSettlementBatch.__table__.create(engine)
    EmsCodSettlementRow.__table__.create(engine)
    db = sessionmaker(bind=engine)()
    db.add_all(
        [
            EmsShippingRecord(
                reference_code="H04072601",
                ems_tracking_code="EH111111111VN",
                cod_amount=427000,
                sync_status="matched",
            ),
            EmsShippingRecord(
                reference_code="H10082610",
                ems_tracking_code="EH222222222VN",
                cod_amount=658000,
                sync_status="matched",
            ),
        ]
    )
    db.commit()

    first = import_cod_settlement_excel(
        db,
        _workbook("Ngày trả tiền: 18/07/2026", "EH111111111VN", 427000),
        source_filename=_FILENAME,
    )
    second = import_cod_settlement_excel(
        db,
        _workbook("Ngày trả tiền: 16/11/2026", "EH222222222VN", 658000),
        source_filename=_FILENAME,
    )

    kept = db.query(EmsShippingRecord).filter_by(ems_tracking_code="EH111111111VN").one()
    added = db.query(EmsShippingRecord).filter_by(ems_tracking_code="EH222222222VN").one()
    assert kept.cod_settlement_status == "matched"
    assert int(kept.cod_paid_amount) == 427000
    assert kept.cod_paid_date == date(2026, 7, 18)
    assert added.cod_settlement_status == "matched"
    assert int(added.cod_paid_amount) == 658000
    assert added.cod_paid_date == date(2026, 11, 16)
    assert db.query(EmsCodSettlementBatch).count() == 2
    assert db.query(EmsCodSettlementRow).count() == 2
    assert first["summary"]["matched"] == 1
    assert second["summary"]["matched"] == 1
    assert all("cập nhật đợt" not in warning for warning in second["warnings"])
    db.close()
