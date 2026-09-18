# Neuro-Lawyer Upgrade Proposal

## Product Direction

Neurolegal should feel less like a generic chatbot and more like a legal research
workspace: the first answer must quickly give a lawyer a verified normative
basis, show what the answer stands on, and mark what still needs checking.

Visual work must stay inside the Alfa Kurs design language from
`kurs.alfabank.ru`. Legora is useful only as a product/workflow reference:
collaborative AI, research/review/drafting tools in one workspace, transparent
cited answers, and a connected operating system for legal work.

## Alfa Kurs Token Notes

Checked `https://kurs.alfabank.ru/` on 2026-06-28. The site exposes these
relevant primitives in its CSS:

- spacing: `0.5rem`, `0.75rem`, `1rem`, `1.5rem`, `2.5rem`, with larger
  desktop steps.
- radius: `0.125rem`, `0.25rem`, `0.5rem`, `0.75rem`, `1rem`, `1.5rem`,
  `2rem`, `3rem`, and pill radius.
- background/surfaces: `#FDFCFC`, `#F2F3F5`, `#FFFFFF`.
- text and borders: `#0E0E0E`, `#1C1C1E`, `#27272A`, `#7A7A7A`,
  `#E7E8EA`, `#D5D6DC`.
- accent: Alfa red `#EF3124`, hover red `#E8281B`, pale red `#FFEBEB`.

These values are mirrored as primitives in `frontend/src/styles/tokens.css`.

## Implemented In This Branch

- Design tokens now mirror Alfa Kurs primitives in
  `frontend/src/styles/tokens.css`: neutral surfaces, Alfa red accent,
  compact radii, and restrained borders.
- The chat composer keeps its visible animated frame/outline instead of
  becoming a flat input.
- Mobile sidebar state now starts collapsed, so the main workspace is usable
  on narrow screens without an always-on overlay.
- The legal system prompt now asks for a short conclusion, normative basis,
  application notes, and follow-up checks.
- Text-task and smalltalk turns no longer receive or execute legal research
  tools, which reduces accidental citations outside legal research mode.
- `neurolegal agent eval-retrieval` runs a seed retrieval benchmark against live RAG.
- Agent audit and next-step roadmap are captured in
  `product/agent-research-2026-06-28.md`.

## Agent Quality Metrics

Start with retrieval metrics before judging prose:

- `citation_recall`: expected act/article pairs found in top-N.
- `act_recall`: expected act family found even when article ranking is imperfect.
- `mrr`: whether the first correct article appears near the top.
- `top_score_avg`: useful for calibrating `NEUROLEGAL_RAG_MIN_SCORE`.

Command:

```bash
uv run neurolegal agent eval-retrieval --rag-url http://127.0.0.1:8001 --limit 8
```

Next layer after this branch: add answer-level review cases with checks for
citation format, unsupported legal claims, and missing "Что проверить
дополнительно" sections.

## Source Expansion Order

1. `publication.pravo.gov.ru` API for official publication metadata and new
   NPA discovery.
2. `pravo.gov.ru` current-text pages for actual editorial text; current code
   already has `PravoGovAcquirer`, but `PravoGovHTMLParser` is still a stub.
3. RusLawOD XML corpus for broad bootstrap, regression fixtures, and benchmark
   cases. It is useful as open data, but not a substitute for official-current
   validation.
4. Judicial-practice sources (`sudact.ru`, `sudrf.ru`, `kad.arbitr.ru`) as a
   separate retrieval namespace, never mixed with statutes without labels.

References checked on 2026-06-28:

- https://kurs.alfabank.ru/
- https://legora.com/
- https://legora.com/product
- https://publication.pravo.gov.ru/help
- https://pravo.gov.ru/
- https://github.com/irlcode/RusLawOD/
- https://regulation.gov.ru/
