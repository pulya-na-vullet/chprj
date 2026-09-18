import { InfoIcon } from "./InfoIcon";

export function McpSection() {
  return (
    <div className="scaffold-card">
      <div className="scaffold-head">
        MCP-серверы
        <InfoIcon text="Подключение внешних инструментов по протоколу MCP. Каждый сервер даёт агенту набор тулзов." />
        <span className="soon-pill">скоро</span>
      </div>
      <p>
        Здесь появится список MCP-серверов с индикатором статуса, числом тулзов и переключателем,
        плюс кнопка «Добавить сервер». Пока не реализовано.
      </p>
    </div>
  );
}
