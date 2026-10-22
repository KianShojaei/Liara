from app.liara.redaction import is_sensitive_env, mask_obj, mask_text

JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySUQiOiIxMjM0NTY3ODkwMTIzNDU2Nzg5MCJ9.abcdefghijklmnopqrstuvwxyz0123456789"


def test_masks_jwt_bearer_and_urls():
    text = f"Authorization: Bearer {JWT} postgres://u:p4ssw0rd@db/x ?token=abcdef123456"
    masked = mask_text(text)
    assert JWT not in masked
    assert "p4ssw0rd" not in masked
    assert "abcdef123456" not in masked


def test_masks_env_pairs_by_key():
    masked = mask_obj(
        [{"key": "DATABASE_URL", "value": "postgres://x"}, {"key": "PORT", "value": "3000"}]
    )
    assert masked[0]["value"] == "<hidden>"
    assert masked[1]["value"] == "3000"
    assert is_sensitive_env("SHOP_API_KEY") and not is_sensitive_env("NODE_ENV")
