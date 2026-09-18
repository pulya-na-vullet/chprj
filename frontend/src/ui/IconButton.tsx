import { IconButtonDesktop } from "@alfalab/core-components/icon-button/desktop";
import type { ComponentProps } from "react";

type Props = ComponentProps<typeof IconButtonDesktop>;

/** Иконочная кнопка core-ds; icon принимает готовый элемент (lucide). */
export function IconButton({ view = "secondary", size = 32, ...rest }: Props) {
  return <IconButtonDesktop view={view} size={size} {...rest} />;
}
