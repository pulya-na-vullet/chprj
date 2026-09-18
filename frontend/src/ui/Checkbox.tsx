import { Checkbox as CoreCheckbox } from "@alfalab/core-components/checkbox";
import type { ReactNode } from "react";

/** Чекбокс core-ds с упрощённым onChange — без события и payload. */
export function Checkbox({
  label,
  checked,
  onChange,
  className,
}: {
  label: ReactNode;
  checked: boolean;
  onChange: () => void;
  className?: string;
}) {
  return (
    <CoreCheckbox label={label} checked={checked} onChange={() => onChange()} className={className} size={20} />
  );
}
