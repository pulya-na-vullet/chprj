import { render, fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";

const setView = vi.fn();
vi.mock("../state/ChatContext", () => ({
  useChat: () => ({ state: { view: "sources" }, setView }),
}));

import { SidebarNav } from "../components/SidebarNav";

describe("SidebarNav", () => {
  it("marks the active view and switches on click", () => {
    render(<SidebarNav />);
    const sources = screen.getByRole("button", { name: "Источники права" });
    expect(sources.className).toContain("nav-item-active");
    fireEvent.click(screen.getByRole("button", { name: "Файлы" }));
    expect(setView).toHaveBeenCalledWith("files");
  });
});
