import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { UploadModal } from "../../admin/components/UploadModal";

const jsonResponse = (body: unknown) => ({ ok: true, json: async () => body }) as Response;

afterEach(() => vi.unstubAllGlobals());

it("rejects non-docx files without calling the API", () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  render(<UploadModal onClose={vi.fn()} onDone={vi.fn()} />);
  const input = screen.getByTestId("file-input");
  fireEvent.change(input, { target: { files: [new File(["x"], "doc.pdf")] } });
  expect(screen.getByText("Нужен файл .docx")).toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();
});

it("submits multipart form and reports job id", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValue(jsonResponse({ code_id: "УК", job_id: "j1" }));
  vi.stubGlobal("fetch", fetchMock);
  const onDone = vi.fn();
  render(<UploadModal onClose={vi.fn()} onDone={onDone} />);

  fireEvent.change(screen.getByTestId("file-input"), {
    target: { files: [new File(["x"], "uk.docx")] },
  });
  fireEvent.change(screen.getByLabelText("code_id"), { target: { value: "УК" } });
  fireEvent.change(screen.getByLabelText("Полное название"), {
    target: { value: "Уголовный кодекс" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Создать" }));

  await waitFor(() => expect(onDone).toHaveBeenCalledWith("j1"));
  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  expect(url).toBe("/admin/documents");
  expect(init.body).toBeInstanceOf(FormData);
  const form = init.body as FormData;
  expect(form.get("code_id")).toBe("УК");
  expect(form.get("short_name")).toBe("uk"); // предзаполнено из имени файла
  expect(form.get("ingest_now")).toBe("true");
});
