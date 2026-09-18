from pathlib import Path

import pytest

from neurolegal.agent.review.playbook import PlaybookError, load_playbooks

MINIMAL = """
id: test_pb
name: Тестовый
rules:
  - id: r1
    title: Оплата
    question: Определён ли срок оплаты?
    risk_if_missing: high
    rag_queries: ["срок оплаты"]
"""


def test_load_playbooks_parses_yaml(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text(MINIMAL, encoding="utf-8")
    pbs = load_playbooks(tmp_path)
    assert set(pbs) == {"test_pb"}
    assert pbs["test_pb"].rules[0].risk_if_missing == "high"
    assert pbs["test_pb"].rules[0].anchors == []


def test_duplicate_rule_ids_rejected(tmp_path: Path) -> None:
    bad = MINIMAL + "  - id: r1\n    title: Дубль\n    question: q\n"
    (tmp_path / "a.yaml").write_text(bad, encoding="utf-8")
    with pytest.raises(PlaybookError):
        load_playbooks(tmp_path)


def test_shipped_playbooks_are_valid() -> None:
    pbs = load_playbooks(Path("playbooks"))
    assert "services_ru" in pbs
    for pb in pbs.values():
        assert 10 <= len(pb.rules) <= 30


def test_roles_parses_from_yaml(tmp_path: Path) -> None:
    yaml_text = MINIMAL.replace(
        "name: Тестовый", 'name: Тестовый\nroles: ["Заказчик", "Исполнитель"]'
    )
    (tmp_path / "a.yaml").write_text(yaml_text, encoding="utf-8")
    pbs = load_playbooks(tmp_path)
    assert pbs["test_pb"].roles == ["Заказчик", "Исполнитель"]


def test_roles_defaults_to_empty_list_when_absent(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text(MINIMAL, encoding="utf-8")
    pbs = load_playbooks(tmp_path)
    assert pbs["test_pb"].roles == []


def test_shipped_playbooks_have_expected_roles() -> None:
    pbs = load_playbooks(Path("playbooks"))
    assert pbs["supply_ru"].roles == ["Покупатель", "Поставщик"]
    assert pbs["services_ru"].roles == ["Заказчик", "Исполнитель"]
    assert pbs["lease_ru"].roles == ["Арендатор", "Арендодатель"]


def test_doc_kind_defaults_to_contract(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text(MINIMAL, encoding="utf-8")
    pbs = load_playbooks(tmp_path)
    assert pbs["test_pb"].doc_kind == "contract"


def test_doc_kind_service_doc_accepted(tmp_path: Path) -> None:
    src = MINIMAL + "doc_kind: service_doc\n"
    (tmp_path / "a.yaml").write_text(src, encoding="utf-8")
    pbs = load_playbooks(tmp_path)
    assert pbs["test_pb"].doc_kind == "service_doc"


def test_doc_kind_invalid_rejected(tmp_path: Path) -> None:
    src = MINIMAL + "doc_kind: bogus\n"
    (tmp_path / "a.yaml").write_text(src, encoding="utf-8")
    with pytest.raises(PlaybookError):
        load_playbooks(tmp_path)


def test_user_agreement_playbook_valid() -> None:
    pbs = load_playbooks(Path("playbooks"))
    pb = pbs["user_agreement_ru"]
    assert pb.doc_kind == "service_doc"
    assert pb.roles == []
    assert 10 <= len(pb.rules) <= 30


def test_privacy_policy_playbook_valid() -> None:
    pbs = load_playbooks(Path("playbooks"))
    pb = pbs["privacy_policy_ru"]
    assert pb.doc_kind == "service_doc"
    assert 10 <= len(pb.rules) <= 30


def test_pdn_consent_playbook_valid() -> None:
    pbs = load_playbooks(Path("playbooks"))
    pb = pbs["pdn_consent_ru"]
    assert pb.doc_kind == "service_doc"
    assert 10 <= len(pb.rules) <= 30
