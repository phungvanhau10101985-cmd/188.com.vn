"""Google Automated Discount — xác thực JWT pv2."""

from app.services.google_automated_discount import verify_google_automated_discount_token

SAMPLE_TOKEN = (
    "eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJjIjoiVk5EIiwiZGMiOiJBQkNERUYiLCJkcCI6NSwiZXhwIjoxNzgxODYzMDYzLCJtIjoiNTY3MjEzODA5NyIsIm8iOiJBNjQxNjAzMjU3NjY2YTE4OE82MTEyIiwicCI6MTE0OTUwMH0."
    "zYpoGw0a9Ylx9kKIo3znbgiqHwY_TN38u271H3f47eq49F_s7DsiMX1pun_j1K7BWfyMM30mERCqp4k_7V9voQ"
)


def test_verify_pv2_derives_prior_price_from_dp():
    payload = verify_google_automated_discount_token(SAMPLE_TOKEN)
    assert payload.price == 1_149_500
    assert payload.prior_price == 1_210_000
    assert payload.offer_id.lower() == "a641603257666a188o6112"
    assert payload.currency == "VND"


def test_verify_pv2_offer_id_match_case_insensitive():
    payload = verify_google_automated_discount_token(
        SAMPLE_TOKEN,
        expected_offer_id="a641603257666a188o6112",
    )
    assert payload.price == 1_149_500
