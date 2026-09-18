"""Fixed strings the agent emits in known-bad situations.

Centralised so tests can assert on the exact wording and so a future i18n
pass has one place to touch."""

CAP_NOTE = "Не удалось собрать достаточную опору в корпусе для уверенного ответа."
NO_BASIS_NOTE = (
    "В моём корпусе не нашлось норм, релевантных вашему запросу. "
    "Попробуйте уточнить формулировку или выбрать другой источник."
)
# A failed search must never read as "the law does not exist" — that is a
# false legal statement. Shown instead of NO_BASIS_NOTE when rag_search
# errored rather than returned an empty result.
SEARCH_UNAVAILABLE_NOTE = (
    "Поиск по корпусу законодательства временно недоступен, поэтому я не могу "
    "дать обоснованный ответ. Попробуйте повторить вопрос через минуту."
)
