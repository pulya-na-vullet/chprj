import type { components as AgentComponents } from "../api/generated/agent";
import type { components as RagComponents } from "../api/generated/rag";
import type { Act, Citation, Conversation, Message } from "../api/types";

// Compile-time assertion: hand-written types still match what the backend
// emits. Vitest just needs *a* test to assert at runtime that compilation
// happened; the real check is the `Equal` typing below.
type Equal<A, B> =
  (<T>() => T extends A ? 1 : 2) extends (<T>() => T extends B ? 1 : 2) ? true : false;

type AssertEq<T extends true> = T;

type AssertActMatches = AssertEq<Equal<Act, RagComponents["schemas"]["ActSummary"]>>;
type AssertCitationMatches = AssertEq<
  Equal<Citation, AgentComponents["schemas"]["Citation"]>
>;
type AssertConversationMatches = AssertEq<
  Equal<Conversation, AgentComponents["schemas"]["ConversationOut"]>
>;
type AssertMessageMatches = AssertEq<
  Equal<Message, AgentComponents["schemas"]["MessageOut"]>
>;

// Touch the asserts so unused-type lint doesn't strip them.
const _alive: [
  AssertActMatches,
  AssertCitationMatches,
  AssertConversationMatches,
  AssertMessageMatches,
] = [true, true, true, true];

import { describe, expect, it } from "vitest";
describe("api types", () => {
  it("compiles with structural-equality asserts", () => {
    expect(_alive.every(Boolean)).toBe(true);
  });
});
