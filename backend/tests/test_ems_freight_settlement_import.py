"""Đối soát cước đọc file cước shop: A mã đơn, B ngày gửi, L cước, W mã tham chiếu."""

from __future__ import annotations

from datetime import date

from app.services.ems_freight_settlement_import import parse_freight_settlement_rows
from app.services.ems_import_sample_templates import build_freight_settlement_sample_xlsx

_CUOC_XML = b"""<xml version>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Worksheet ss:Name="Cuoc"><Table>
 <Row><Cell><Data ss:Type="String">BANG TONG HOP NO CHI TIET</Data></Cell></Row>
 <Row>
  <Cell><Data ss:Type="String">Ma_E1</Data></Cell>
  <Cell><Data ss:Type="String">Ngay_Phat_Hanh</Data></Cell>
  <Cell ss:Index="12"><Data ss:Type="String">Cuoc_Chinh</Data></Cell>
  <Cell ss:Index="17"><Data ss:Type="String">Cuoc_Cod</Data></Cell>
  <Cell ss:Index="23"><Data ss:Type="String">So_Tham_Chieu</Data></Cell>
 </Row>
 <Row>
  <Cell><Data ss:Type="String">EG040722845VN</Data></Cell>
  <Cell><Data ss:Type="String">2026-11-02T00:00:00.000</Data></Cell>
  <Cell ss:Index="12"><Data ss:Type="Number">33453</Data></Cell>
  <Cell ss:Index="17"><Data ss:Type="Number">0</Data></Cell>
  <Cell ss:Index="23"><Data ss:Type="String">H02112617</Data></Cell>
 </Row>
 <Row>
  <Cell><Data ss:Type="String">EG040723024VN</Data></Cell>
  <Cell><Data ss:Type="String">2026-11-09T00:00:00.000</Data></Cell>
  <Cell ss:Index="12"><Data ss:Type="Number">72000</Data></Cell>
  <Cell ss:Index="23"><Data ss:Type="String">H02112641</Data></Cell>
 </Row>
 </Table></Worksheet>
</Workbook>
"""


def test_parse_cuoc_shop_xml_uses_order_date_fee_and_reference():
    settlement_date, rows, warnings = parse_freight_settlement_rows(
        _CUOC_XML, source_filename="cuoc shop 188.xls"
    )

    assert settlement_date == date(2026, 11, 9)
    assert warnings == ["Phát hiện dòng tiêu đề ở hàng 2."]
    assert len(rows) == 2
    assert rows[0]["ems_tracking_code"] == "EG040722845VN"
    assert rows[0]["reference_code"] == "H02112617"
    assert rows[0]["freight_amount"] == 33453
    assert rows[1]["freight_amount"] == 72000
    assert rows[1]["reference_code"] == "H02112641"


def test_sample_workbook_matches_cuoc_shop_columns():
    content, filename = build_freight_settlement_sample_xlsx()
    settlement_date, rows, _warnings = parse_freight_settlement_rows(
        content, source_filename=filename
    )

    assert settlement_date == date(2026, 11, 3)
    assert [row["ems_tracking_code"] for row in rows] == ["EG040722845VN", "EG040723024VN"]
    assert [row["reference_code"] for row in rows] == ["H02112617", "H02112641"]
    assert [row["freight_amount"] for row in rows] == [33453, 30618]
