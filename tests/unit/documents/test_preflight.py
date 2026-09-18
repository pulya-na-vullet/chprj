import pytest

from neurolegal.documents.processing.preflight import (
    PreflightError,
    check_internal_token,
    check_tessdata,
)


def test_missing_tessdata_raises(tmp_path):
    with pytest.raises(PreflightError) as exc:
        check_tessdata(tmp_path)
    assert "rus.traineddata" in str(exc.value)


def test_present_tessdata_ok(tmp_path):
    (tmp_path / "rus.traineddata").write_bytes(b"stub")
    check_tessdata(tmp_path)  # no raise


def test_required_but_missing_internal_token_raises():
    with pytest.raises(PreflightError) as exc:
        check_internal_token(True, None)
    assert "NEUROLEGAL_INTERNAL_TOKEN" in str(exc.value)


def test_required_and_present_internal_token_ok():
    check_internal_token(True, "secret")  # no raise


def test_not_required_missing_internal_token_ok():
    check_internal_token(False, None)  # no raise
