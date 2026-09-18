import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import "@testing-library/jest-dom/vitest";

import { AssistantMessage } from "../components/AssistantMessage";
import { formatTimestamp } from "../util/format";

const AT = "2026-07-12T20:53:00";

describe("метки времени ответов ассистента (T-0015)", () => {
  it("финализированное сообщение показывает время создания", () => {
    render(
      <AssistantMessage
        content="Ответ"
        citations={null}
        actNames={[]}
        createdAt={AT}
      />,
    );
    expect(screen.getByText(formatTimestamp(AT))).toBeInTheDocument();
  });

  it("стрим-черновик и сообщение без даты — без метки времени", () => {
    const { container, rerender } = render(
      <AssistantMessage content="Ответ" citations={null} actNames={[]} />,
    );
    expect(container.querySelector(".msg-time")).toBeNull();
    rerender(
      <AssistantMessage content="Ответ" citations={null} actNames={[]} createdAt={AT} streaming />,
    );
    expect(container.querySelector(".msg-time")).toBeNull();
  });
});
