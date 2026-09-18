import { ButtonDesktop } from "@alfalab/core-components/button/desktop";
import type { ComponentProps } from "react";

type Props = ComponentProps<typeof ButtonDesktop>;

/** Кнопка core-ds с дефолтами Kurs: компактная, контурная. */
export function Button({ view = "outlined", size = 40, ...rest }: Props) {
  return <ButtonDesktop view={view} size={size} {...rest} />;
}
