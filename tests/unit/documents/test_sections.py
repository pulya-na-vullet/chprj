from neurolegal.documents.processing.sections import build_sections


def test_numbered_sections():
    paras = ["Преамбула", "1. Предмет договора", "Текст пункта", "2. Цена", "100 руб"]
    sections, full_text = build_sections(paras)
    numbers = [s.number for s in sections]
    assert "1" in numbers and "2" in numbers
    assert "Предмет договора" in full_text


def test_unnumbered_falls_back_to_chunks():
    paras = ["просто текст без нумерации"] * 3
    sections, _ = build_sections(paras)
    assert sections and sections[0].number.startswith("p")
