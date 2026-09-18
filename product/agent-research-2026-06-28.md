# Agent Research Audit

Date: 2026-06-28

## Target

Neurolegal should help a lawyer quickly find a usable normative basis. The agent
must prioritize retrieval quality, exact citations, freshness signals, and
honest gaps over confident prose.

## Current Architecture

- Intent routing is rule-based in `src/neurolegal/agent/chat/intent.py`.
  Unknown messages default to `LEGAL`, which is the right conservative default
  for this product.
- `ChatAgent` in `src/neurolegal/agent/chat/agent.py` runs a streaming LLM/tool loop
  with a configurable max iteration count and a hard legal safety floor:
  if legal intent produces no retrieved articles, the draft answer is replaced
  with the no-basis or search-unavailable note.
- Tool exposure is now gated by intent: legal turns receive the enabled
  research tools, while text-task and smalltalk turns run without tools and do
  not execute unexpected tool calls.
- Legal grounding enters the agent only through `RagClient` in
  `src/neurolegal/agent/tools/rag_client.py`, which calls the RAG HTTP API.
- The built-in legal prompt lives in `src/neurolegal/core/agent_prompts.py` and can
  be overridden from admin behavior settings.
- Web tools exist, but the prompt now frames them as context only, never as a
  source of legal norms.
- The data layer already stores source metadata including redaction fields, but
  official `pravo.gov.ru` HTML parsing is still a stub. Local DOCX remains the
  practical corpus path today.

## Strengths

- No retrieved legal basis means no legal answer. That is the most important
  safety primitive for a legal research assistant.
- The agent emits citations as structured events, not only prose, so the UI can
  show evidence without parsing model text.
- Source filtering can be passed into the RAG context through `acts`.
- Admin settings already separate behavior and tool flags, which gives a clean
  path for controlled experiments.
- Reset-delta handling prevents partial pre-tool prose from becoming the final
  stored answer.
- Text-task and smalltalk turns no longer have a path to accidental legal
  citations via RAG.

## Quality Gaps

- The prompt asks for citations, but there is no post-generation validator that
  checks whether every legal claim maps to a retrieved article.
- The agent does not verify article citations mentioned in prose against the
  retrieved `articles_seen` set. A hallucinated "ст. N" can survive if the turn
  had at least one retrieved article.
- Query planning is fully model-managed. There is no deterministic legal
  research plan such as "direct user wording", "statutory term expansion",
  and "act/article exact lookup".
- The answer format is prompt-level only. There is no server-side answer
  contract enforcing "Нормативная база" before application notes.
- Redaction/currentness is not surfaced in the answer contract, even though
  source manifests can carry redaction metadata.
- There is no coverage map showing which acts are in the local corpus and which
  requested areas are missing.
- Retrieval quality was not measurable before this branch. The new benchmark
  starts this, but the gold set is still small.

## Metrics

Start with deterministic checks before using an LLM judge.

- `citation_recall`: expected act/article pairs found in top-N search results.
- `act_recall`: expected act family found, even if the exact article ranking is
  imperfect.
- `mrr`: first correct article position.
- `top_score_avg`: average score of the first returned article for calibrating
  thresholds.
- `unsupported_citation_rate`: citations in prose that are absent from
  retrieved or fetched articles.
- `grounded_claim_rate`: legal claims that can be mapped to one or more cited
  retrieved articles.
- `no_basis_precision`: how often refusals happen only when the corpus truly
  lacks the required basis.
- `section_completeness`: whether answers contain the required legal research
  sections.
- `tool_call_count` and time-to-first-answer: quality must not make research
  feel sluggish.

## Roadmap

1. Expand the retrieval benchmark from seed cases to 50-100 questions across
   contracts, consumer law, employment, tax, corporate, IP, administrative, and
   civil procedure.
2. Add a citation validator after generation:
   parse `ст. <номер> <акт>` mentions, compare them to `articles_seen`, and
   reset/refuse or ask the model to repair unsupported citations.
3. Add a deterministic legal research planner before the LLM loop:
   run the user query, one expanded statutory query, and exact `fetch_article`
   calls when article numbers are present.
4. Introduce an answer contract for legal turns:
   "Короткий вывод", "Нормативная база", "Как применить", and
   "Что проверить дополнительно" should be validated server-side.
5. Surface source freshness:
   include act redaction, source document, and "currentness unknown" warnings
   when metadata is missing.
6. Build a corpus coverage report:
   show available acts, redactions, article counts, ingest dates, and gaps in
   admin/internal product views before exposing any source-management UI.
7. Add answer-level regression tests with fixed RAG fixtures and deterministic
   fake LLM outputs before adding an LLM judge.

## Data Source Direction

- Use `publication.pravo.gov.ru` for official publication metadata and update
  discovery.
- Use `pravo.gov.ru` current-text pages for authoritative text acquisition
  once `PravoGovHTMLParser` is implemented.
- Use RusLawOD as a bootstrap corpus and benchmark fixture source, not as the
  final authority for current redactions.
- Keep judicial practice in a separate namespace with clear labels. It should
  support legal analysis, but never be mixed into statute citations.

## First Engineering Slice After This Branch

The next best slice is not another UI panel. It is a grounding loop:

1. Make a fixed RAG fixture for 10 legal questions.
2. Generate answers with a fake LLM that intentionally includes one unsupported
   citation.
3. Add a citation validator and prove it catches the unsupported article.
4. Add a repair path where the model receives the validator error and rewrites
   the answer using only retrieved citations.
