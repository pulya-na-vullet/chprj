import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusPill } from "../components/files/StatusPill";

describe("StatusPill", () => {
  it("рендерит подпись и тон по статусу", () => {
    const { container, rerender } = render(<StatusPill status="ready" />);
    expect(screen.getByText("готов")).toBeInTheDocument();
    expect(container.querySelector(".st-ok")).not.toBeNull();

    rerender(<StatusPill status="failed" />);
    expect(screen.getByText("ошибка")).toBeInTheDocument();
    expect(container.querySelector(".st-err")).not.toBeNull();
  });

  it("у обработки есть крутящееся кольцо", () => {
    const { container } = render(<StatusPill status="processing" />);
    expect(screen.getByText("обработка")).toBeInTheDocument();
    expect(container.querySelector(".st-ring")).not.toBeNull();
  });
});
