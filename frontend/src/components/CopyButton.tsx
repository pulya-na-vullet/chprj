import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { IconButton } from "../ui";

interface CopyButtonProps {
  text: string;
  label?: string;
  className?: string;
  // "icon" (default): IconButton with the label as aria-label only — used
  // wherever the surrounding row already reads (per-risk actions, panel
  // header). "text": a plain button with a visible label next to the icon —
  // used where the action needs to read as a real button on its own
  // (T-0010/Задача 5: «Копировать отчёт» at the bottom of the panel).
  variant?: "icon" | "text";
}

export function CopyButton({ text, label = "Копировать", className, variant = "icon" }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  // Clipboard API is only available in secure contexts; hide the button otherwise.
  if (typeof navigator === "undefined" || !navigator.clipboard) return null;

  const onClick = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard write denied — no-op */
    }
  };

  if (variant === "text") {
    return (
      <button type="button" className={className ?? "rvp-btn"} onClick={onClick}>
        {copied ? <Check size={14} /> : <Copy size={14} />}
        {copied ? "Скопировано" : label}
      </button>
    );
  }

  return (
    <IconButton
      className={className ? `copy-btn ${className}` : "copy-btn"}
      view="transparent"
      size={24}
      icon={copied ? <Check size={15} /> : <Copy size={15} />}
      onClick={onClick}
      aria-label={copied ? "Скопировано" : label}
    />
  );
}
