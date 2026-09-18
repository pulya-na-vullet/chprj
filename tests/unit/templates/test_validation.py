"""Field validation (contracts.validate_template_values): required, kind formats,
unknown fields — structured errors. Общая для рендера сервиса и stage агента."""

from neurolegal.contracts import TemplateField
from neurolegal.contracts import validate_template_values as validate_values

FIELDS = [
    TemplateField(name="fio", label="ФИО"),
    TemplateField(name="start_date", label="Дата", kind="date"),
    TemplateField(name="rent", label="Плата", kind="money"),
    TemplateField(name="floors", label="Этаж", kind="number"),
    TemplateField(name="comment", label="Комментарий", required=False),
]


def _codes(values: dict[str, str]) -> dict[str, str]:
    return {e.field: e.code for e in validate_values(FIELDS, values)}


def _valid() -> dict[str, str]:
    return {"fio": "Иванов И. И.", "start_date": "01.09.2026", "rent": "50000", "floors": "3"}


def test_valid_values_pass() -> None:
    assert validate_values(FIELDS, _valid()) == []


def test_optional_field_may_be_absent_or_blank() -> None:
    assert validate_values(FIELDS, _valid() | {"comment": "  "}) == []


def test_required_missing_and_blank() -> None:
    values = _valid()
    del values["fio"]
    values["rent"] = "   "
    codes = _codes(values)
    assert codes == {"fio": "required", "rent": "required"}


def test_date_formats() -> None:
    assert _codes(_valid() | {"start_date": "2026-09-01"}) == {}
    assert _codes(_valid() | {"start_date": "завтра"}) == {"start_date": "invalid_format"}
    assert _codes(_valid() | {"start_date": "32.13.2026"}) == {"start_date": "invalid_format"}


def test_money_formats() -> None:
    for ok in ("50000", "50000,50", "50000.5", "50 000"):
        assert _codes(_valid() | {"rent": ok}) == {}, ok
    for bad in ("50к", "-100", "50000,555"):
        assert _codes(_valid() | {"rent": bad}) == {"rent": "invalid_format"}, bad


def test_number_formats() -> None:
    assert _codes(_valid() | {"floors": "-2"}) == {}
    assert _codes(_valid() | {"floors": "3.5"}) == {"floors": "invalid_format"}


def test_unknown_field_reported() -> None:
    codes = _codes(_valid() | {"extra": "x"})
    assert codes == {"extra": "unknown_field"}


def test_errors_accumulate_with_messages() -> None:
    errors = validate_values(FIELDS, {"start_date": "xx", "unknown": "y"})
    by_field = {e.field: e for e in errors}
    assert set(by_field) == {"fio", "rent", "floors", "start_date", "unknown"}
    assert "ДД.ММ.ГГГГ" in by_field["start_date"].message
