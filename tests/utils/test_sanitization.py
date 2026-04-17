from src.utils.sanitization import sanitize_for_llm


def test_sanitize_for_llm_strips_control_chars():
    raw = "benzene\u200b\u200c\u200d\u0000"
    cleaned = sanitize_for_llm(raw)
    assert "\u200b" not in cleaned
    assert "\u200c" not in cleaned
    assert "\u0000" not in cleaned
    assert "benzene" in cleaned


def test_sanitize_for_llm_removes_backticks_and_dollars():
    raw = "`ignore previous` and $ LaTeX $"
    cleaned = sanitize_for_llm(raw)
    assert "`" not in cleaned
    assert "$" not in cleaned


def test_sanitize_for_llm_collapses_newlines():
    raw = "line1\n\n\n\nline2"
    cleaned = sanitize_for_llm(raw)
    assert "\n\n\n" not in cleaned
    assert "line1" in cleaned
    assert "line2" in cleaned


def test_sanitize_for_llm_normalizes_unicode():
    raw = "caf\u00e9"  # composed e-acute
    cleaned = sanitize_for_llm(raw)
    assert "cafe" in cleaned or "café" in cleaned
