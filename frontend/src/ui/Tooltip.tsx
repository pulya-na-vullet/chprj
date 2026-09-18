import { TooltipDesktop } from "@alfalab/core-components/tooltip/desktop";
import type { ComponentProps } from "react";

type Props = ComponentProps<typeof TooltipDesktop>;

export function Tooltip({ position = "top", trigger = "hover", ...rest }: Props) {
  return <TooltipDesktop position={position} trigger={trigger} {...rest} />;
}
