from neurolegal.agent.chat.prompts import SYSTEM_PROMPT, build_profile_note
from neurolegal.agent.store.models import UserRow


def test_prompt_mandates_number_then_act_citation_format() -> None:
    # Citations must read "ст. <номер> <акт>" (number first), matching the UI chip regex.
    assert "ст. <номер> <акт>" in SYSTEM_PROMPT.lower()


def test_prompt_does_not_ask_model_to_choose_acts() -> None:
    # Source scope is fixed by the user; the model no longer selects acts.
    assert "фильтр по" not in SYSTEM_PROMPT.lower()


def test_legal_prompt_marks_web_as_context_not_basis() -> None:
    from neurolegal.core.agent_prompts import DEFAULT_SYSTEM_PROMPT_LEGAL

    text = DEFAULT_SYSTEM_PROMPT_LEGAL.lower()
    assert "интернет" in text
    assert "не является основанием" in text


def test_legal_prompt_requires_research_brief_structure() -> None:
    from neurolegal.core.agent_prompts import DEFAULT_SYSTEM_PROMPT_LEGAL

    text = DEFAULT_SYSTEM_PROMPT_LEGAL.lower()
    assert "короткий вывод" in text
    assert "нормативная база" in text
    assert "что проверить дополнительно" in text


def test_template_prompt_bans_field_keys_summary_dup_and_emoji() -> None:
    # Замечания клиента (T-0141): после stage карточка уже показывает данные —
    # текст не должен дублировать сводку, упоминать машинные имена полей
    # или содержать эмодзи.
    from neurolegal.agent.chat.prompts import TEMPLATE_PROMPT

    lowered = TEMPLATE_PROMPT.lower()
    assert "не перечисляй собранные данные текстом" in lowered
    assert "русскими подписями" in lowered
    assert "эмодзи не используй" in lowered


# --- T-0128: профильный блок из заполненного профиля (спека E19 §7) ---


def _user(**profile: object) -> UserRow:
    return UserRow(email="p@example.com", password_hash="h", **profile)  # type: ignore[arg-type]


def test_profile_note_is_none_for_empty_profile() -> None:
    assert build_profile_note(_user()) is None


def test_profile_note_full_business_profile() -> None:
    note = build_profile_note(
        _user(
            first_name="Денис",
            last_name="Анастасьев",
            usage_kind="business",
            role="lawyer",
            tasks=["law_questions", "files"],
        )
    )
    assert note is not None
    text = note.lower()
    assert "о пользователе" in text
    assert "денис анастасьев" in text
    assert "для бизнеса" in text
    assert "юрист" in text
    assert "вопросы по законодательству" in text
    assert "работа со своими файлами" in text


def test_profile_note_partial_profile_only_name() -> None:
    note = build_profile_note(_user(first_name="Ася"))
    assert note is not None
    assert "Ася" in note
    assert "роль" not in note.lower()
    assert "задачи" not in note.lower()


def test_profile_note_role_ignored_outside_business() -> None:
    # Роль осмысленна только в ветке «Для бизнеса» (та же логика, что в UI).
    note = build_profile_note(_user(usage_kind="personal", role="lawyer"))
    assert note is not None
    assert "для себя" in note.lower()
    assert "юрист" not in note.lower()


def test_profile_note_does_not_restate_citation_rules() -> None:
    # Блок — про пользователя, не про правила: он не должен дублировать или
    # переопределять правило «только из результатов поиска».
    note = build_profile_note(_user(first_name="Денис"))
    assert note is not None
    assert "rag_search" not in note
    assert "цитир" not in note.lower()
