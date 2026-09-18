import { useCallback, useEffect, useRef } from "react";
import { SIDEBAR_MAX_WIDTH, SIDEBAR_MIN_WIDTH } from "../state/sidebarWidth";
import { useChat } from "../state/ChatContext";

// Drag-to-resize grip. The hit area is small and centered on the panel edge;
// only the grip is draggable (not the whole edge). Width is clamped and
// persisted by setSidebarWidth.
export function SidebarResizer() {
  const { setSidebarWidth } = useChat();
  const dragging = useRef(false);

  const onMove = useCallback(
    (e: MouseEvent) => {
      if (!dragging.current) return;
      const w = Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, e.clientX));
      setSidebarWidth(w);
    },
    [setSidebarWidth],
  );

  const onUp = useCallback(() => {
    dragging.current = false;
    document.body.style.cursor = "";
  }, []);

  useEffect(() => {
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [onMove, onUp]);

  return (
    <div
      className="sidebar-resizer"
      role="separator"
      aria-orientation="vertical"
      aria-label="Изменить ширину панели"
      onMouseDown={(e) => {
        dragging.current = true;
        document.body.style.cursor = "col-resize";
        e.preventDefault();
      }}
    >
      <div className="sidebar-grip" />
    </div>
  );
}
