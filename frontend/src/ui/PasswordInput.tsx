import { PasswordInput as CorePasswordInput } from "@alfalab/core-components/password-input";
import type { ComponentProps } from "react";

type CoreProps = ComponentProps<typeof CorePasswordInput>;
type Props = Omit<CoreProps, "onChange"> & { onChange?: (value: string) => void };

/** Поле пароля core-ds (со встроенным переключателем видимости) с дефолтами
 * Kurs: во всю ширину, лейбл сверху, onChange отдаёт строку без события. */
export function PasswordInput({
  onChange,
  block = true,
  size = 48,
  labelView = "outer",
  ...rest
}: Props) {
  return (
    <CorePasswordInput
      block={block}
      size={size}
      labelView={labelView}
      onChange={onChange ? (_e, { value }) => onChange(value) : undefined}
      {...rest}
    />
  );
}
