import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CopyButton } from "../components/CopyButton";

describe("CopyButton", () => {
  it("writes the text to the clipboard and swaps to the copied state", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });

    render(<CopyButton text="привет" />);
    const btn = screen.getByRole("button", { name: "Копировать" });
    fireEvent.click(btn);

    expect(writeText).toHaveBeenCalledWith("привет");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Скопировано" })).toBeInTheDocument(),
    );
  });
});
