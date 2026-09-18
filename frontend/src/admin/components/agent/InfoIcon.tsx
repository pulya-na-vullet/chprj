import { useState } from "react";

export function InfoIcon({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <span
      className="info-icon"
      tabIndex={0}
      role="img"
      aria-label={text}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      i{open && <span className="info-tip">{text}</span>}
    </span>
  );
}
