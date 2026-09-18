import { InputDesktop } from "@alfalab/core-components/input/desktop";
import type { ComponentProps } from "react";

type CoreProps = ComponentProps<typeof InputDesktop>;
type Props = Omit<CoreProps, "onChange"> & { onChange?: (value: string) => void };

/** Текстовое поле core-ds с дефолтами Kurs: во всю ширину, лейбл сверху,
 * onChange отдаёт строку без события. */
export function Input({ onChange, block = true, size = 48, labelView = "outer", ...rest }: Props) {
  return (
    <InputDesktop
      block={block}
      size={size}
      labelView={labelView}
      onChange={onChange ? (_e, { value }) => onChange(value) : undefined}
      {...rest}
    />
  );
}
