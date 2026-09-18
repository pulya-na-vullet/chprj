import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { ErrorBoundary } from "../components/ErrorBoundary";

function Boom(): never {
  throw new Error("render boom");
}

it("renders fallback instead of crashing when a child throws", () => {
  // React logs the caught error; silence it for a clean test run.
  const spy = vi.spyOn(console, "error").mockImplementation(() => {});
  render(
    <ErrorBoundary fallback={<div>запасной текст</div>}>
      <Boom />
    </ErrorBoundary>,
  );
  expect(screen.getByText("запасной текст")).toBeInTheDocument();
  spy.mockRestore();
});

it("recovers and renders children after resetKey changes", () => {
  const spy = vi.spyOn(console, "error").mockImplementation(() => {});

  function Wrapper({ broken, k }: { broken: boolean; k: string }) {
    return (
      <ErrorBoundary resetKey={k} fallback={<div>запасной текст</div>}>
        {broken ? <Boom /> : <div>нормальный ответ</div>}
      </ErrorBoundary>
    );
  }

  const { rerender } = render(<Wrapper broken k="1" />);
  expect(screen.getByText("запасной текст")).toBeInTheDocument();

  // New token arrives (resetKey changes) and the content is now valid markdown.
  rerender(<Wrapper broken={false} k="2" />);
  expect(screen.getByText("нормальный ответ")).toBeInTheDocument();
  spy.mockRestore();
});
