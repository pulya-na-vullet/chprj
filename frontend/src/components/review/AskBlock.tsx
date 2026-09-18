import type { MessageAsk } from "../../api/types";

/** Renders under an assistant message whose `ask.kind === "review_role"`
 * (T-0046 — the agent paused a `risk_review` turn to ask which side of the
 * contract the user is) or `"ask_user"` (T-0051 — the LLM's universal
 * clarifying question; the picked option is sent as a plain message).
 * The question text itself is NOT repeated here: it's
 * already the message's `content` (RenderMarkdown above this block already
 * shows it) — this only renders the answer affordances: one pill button per
 * playbook-declared role, plus a dashed "type it myself" button, plus a note
 * that a typed answer works too.
 *
 * `active` gates whether the buttons still do anything: once the
 * conversation has moved past this message (a later turn started, or a new
 * message was sent), answering here would be stale — MessageList computes
 * `active` as "this is the last message and no turn is streaming". */
export function AskBlock({
  ask,
  active,
  onPick,
  onFree,
}: {
  ask: MessageAsk;
  active: boolean;
  onPick: (text: string) => void;
  onFree: () => void;
}) {
  const options = ask.options ?? [];
  return (
    <div className="rvp-ask">
      <div className="rvp-ask-opts">
        {options.map((option) => (
          <button
            key={option}
            type="button"
            className="rvp-ask-opt"
            disabled={!active}
            onClick={() => onPick(option)}
          >
            {option}
          </button>
        ))}
        <button
          type="button"
          className="rvp-ask-opt rvp-ask-free"
          disabled={!active}
          onClick={onFree}
        >
          Другое — напишу сам
        </button>
      </div>
      <div className="rvp-ask-note">Можно ответить и текстом в поле ниже</div>
    </div>
  );
}
