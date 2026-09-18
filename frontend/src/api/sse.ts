import { notifyUnauthorized } from "./authEvents";
import type { ServerEvent } from "./types";

interface Frame {
  event: string;
  data: unknown;
}

// SSE frames separated by a blank line ("\r\n\r\n" from sse-starlette, or "\n\n").
// Lines inside a frame may use either ending. Comment lines (":") and frames
// without a `data:` line are skipped. Ported from the prior vanilla app.js.
export function parseFrames(buffer: string): { events: Frame[]; rest: string } {
  const events: Frame[] = [];
  while (true) {
    let idx = buffer.indexOf("\r\n\r\n");
    let sepLen = 4;
    const idxLf = buffer.indexOf("\n\n");
    if (idxLf >= 0 && (idx < 0 || idxLf < idx)) {
      idx = idxLf;
      sepLen = 2;
    }
    if (idx < 0) break;
    const raw = buffer.slice(0, idx);
    buffer = buffer.slice(idx + sepLen);
    let event = "message";
    const dataLines: string[] = [];
    for (const line of raw.split(/\r\n|\n/)) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).replace(/^\s/, ""));
    }
    if (dataLines.length === 0) continue;
    try {
      events.push({ event, data: JSON.parse(dataLines.join("\n")) });
    } catch (err) {
      // Don't leak frame contents (assistant/citation text) in production logs.
      if (import.meta.env.DEV) console.warn("malformed SSE frame", err, raw);
    }
  }
  return { events, rest: buffer };
}

export interface ChatParams {
  sessionId: string | null;
  message: string;
  acts: string[] | null;
  command?: {
    type: "risk_review";
    document_id: string;
    playbook_id: string;
    role?: string | null;
  } | null;
  // E20: вход из витрины «Шаблоны» — агент получает поля шаблона в контекст
  templateSlug?: string | null;
  signal?: AbortSignal;
}

// "interrupted": the body ended cleanly but the terminal `done` event never
// arrived (proxy idle-timeout, server died mid-answer) — the draft shown so
// far is NOT a completed answer and must not be finalized as one.
export type StreamOutcome =
  | "done"
  | "interrupted"
  | "not_found"
  | "unauthorized"
  | "http_error"
  | "network_error";

// POSTs to /chat and streams events to `onEvent`. Returns an outcome the caller
// maps to UI state. Does not throw on HTTP/network errors — reports via outcome.
export async function streamChat(
  params: ChatParams,
  onEvent: (ev: ServerEvent) => void,
): Promise<StreamOutcome> {
  let response: Response;
  try {
    response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({
        session_id: params.sessionId,
        message: params.message,
        acts: params.acts,
        command: params.command ?? null,
        template_slug: params.templateSlug ?? null,
      }),
      signal: params.signal,
    });
  } catch {
    return "network_error";
  }
  if (response.status === 404) return "not_found";
  if (response.status === 409) return "http_error"; // concurrent turn rejected
  if (response.status === 401) {
    notifyUnauthorized();
    return "unauthorized";
  }
  if (!response.ok || !response.body) return "http_error";

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let sawDone = false;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const { events, rest } = parseFrames(buffer);
      buffer = rest;
      for (const ev of events) {
        if (ev.event === "done") sawDone = true;
        onEvent(ev as ServerEvent);
      }
    }
  } catch {
    return "network_error";
  }
  return sawDone ? "done" : "interrupted";
}
