"""Обнулить «Суть» готовых документов, чтобы стартовый sweep сервиса
пересчитал их по новому промпту (T-0147).

Разовая операция после выкатки. Сам пересчёт делает
neurolegal.documents.worker.backfill_missing_summaries при следующем
старте сервиса documents.

Необратимая массовая операция без ограничения по владельцу: трогает каждый
готовый документ в базе, заданной DATABASE_URL. Без --dry-run требует
явного --yes (Minor 16, финальное ревью) — опечатка в адресе базы иначе
стирает «Суть» без единого подтверждения.

Run via: ``uv run python -m scripts.reset_summaries [--dry-run] [--yes]``
"""

import argparse
import asyncio

from sqlalchemy import text

from neurolegal.core.db import get_engine


async def main_async(dry_run: bool, yes: bool) -> None:
    engine = get_engine()
    try:
        async with engine.begin() as conn:
            count = await conn.scalar(
                text(
                    "SELECT count(*) FROM hub_documents WHERE status = 'ready' AND summary IS NOT NULL"
                )
            )
            if dry_run:
                print(f"dry-run: обнулило бы {count} строк")
                return
            if not yes:
                raise SystemExit(
                    "Необратимая операция — обнулит «Суть» у всех готовых документов "
                    f"({count} строк). Повторите с --yes для подтверждения "
                    "(или --dry-run, чтобы только посчитать)."
                )
            # Печатаем фактически задетые строки (Minor 16), не
            # предварительную оценку выше: обновление трогает надмножество —
            # включая строки, где выжимка уже пуста.
            result = await conn.execute(
                text("UPDATE hub_documents SET summary = NULL WHERE status = 'ready'")
            )
            print(f"обнулено строк: {result.rowcount}")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="только показать число строк")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="подтвердить необратимое обнуление (обязателен без --dry-run)",
    )
    args = parser.parse_args()
    asyncio.run(main_async(args.dry_run, args.yes))


if __name__ == "__main__":
    main()
