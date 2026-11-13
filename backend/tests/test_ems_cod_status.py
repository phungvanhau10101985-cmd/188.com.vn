from app.services.ems_cod_status import (
    is_cod_amount_mismatch,
    is_cod_settlement_paid,
    should_preserve_confirmed_full,
)


def test_paid_statuses():
    assert is_cod_settlement_paid("matched")
    assert is_cod_settlement_paid(" confirmed_full ")
    assert not is_cod_settlement_paid("amount_mismatch")
    assert not is_cod_settlement_paid(None)


def test_mismatch_and_preserve_confirmation():
    assert is_cod_amount_mismatch("amount_mismatch")
    assert should_preserve_confirmed_full("confirmed_full", "amount_mismatch")
    assert should_preserve_confirmed_full("confirmed_full", None)
    assert not should_preserve_confirmed_full("confirmed_full", "matched")
    assert not should_preserve_confirmed_full("amount_mismatch", "amount_mismatch")
