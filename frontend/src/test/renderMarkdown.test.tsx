import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Citation } from "../api/types";
import { RenderMarkdown } from "../markdown/renderMarkdown";

const citation: Citation = {
  act_short_name: "ГК РФ",
  kind: "codex",
  number: "1477",
  title: "Товарный знак",
  full_text: "Текст статьи 1477 про товарный знак.",
  score: 0.1,
};

describe("RenderMarkdown citation chips", () => {
  it("renders a citation chip and opens the article preview on click", () => {
    render(
      <RenderMarkdown
        content="Согласно ст. 1477 ГК РФ это работает."
        citations={[citation]}
        actNames={["ГК РФ"]}
      />,
    );
    const chip = screen.getByText("ст. 1477 ГК РФ");
    expect(chip).toBeInTheDocument();
    fireEvent.click(chip);
    expect(screen.getByText(/Текст статьи 1477/)).toBeInTheDocument();
  });

  it("closes the preview on Escape", () => {
    render(
      <RenderMarkdown content="Согласно ст. 1477 ГК РФ." citations={[citation]} actNames={["ГК РФ"]} />,
    );
    fireEvent.click(screen.getByText("ст. 1477 ГК РФ"));
    expect(screen.getByText(/Текст статьи 1477/)).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByText(/Текст статьи 1477/)).not.toBeInTheDocument();
  });

  it("closes the preview when the page scrolls", () => {
    render(
      <RenderMarkdown content="Согласно ст. 1477 ГК РФ." citations={[citation]} actNames={["ГК РФ"]} />,
    );
    fireEvent.click(screen.getByText("ст. 1477 ГК РФ"));
    expect(screen.getByText(/Текст статьи 1477/)).toBeInTheDocument();
    fireEvent.scroll(window);
    expect(screen.queryByText(/Текст статьи 1477/)).not.toBeInTheDocument();
  });

  it("stays open when scrolling inside the preview body", () => {
    render(
      <RenderMarkdown content="Согласно ст. 1477 ГК РФ." citations={[citation]} actNames={["ГК РФ"]} />,
    );
    fireEvent.click(screen.getByText("ст. 1477 ГК РФ"));
    const body = document.querySelector(".article-preview-body");
    expect(body).not.toBeNull();
    fireEvent.scroll(body!);
    expect(screen.getByText(/Текст статьи 1477/)).toBeInTheDocument();
  });

  it("renders plain markdown when there are no citations", () => {
    render(<RenderMarkdown content="**жирный** текст" citations={[]} actNames={[]} />);
    expect(screen.getByText("жирный")).toBeInTheDocument();
  });
});
