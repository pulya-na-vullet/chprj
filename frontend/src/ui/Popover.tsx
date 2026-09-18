import { Popover as CorePopover } from "@alfalab/core-components/popover";
import type { ComponentProps } from "react";

type Props = ComponentProps<typeof CorePopover>;

// Стабильная ссылка: новый массив на каждый рендер дёргал бы пропсы поппера.
const DEFAULT_OFFSET: [number, number] = [0, 8];

/** Поповер core-ds; по умолчанию открывается над якорем (композер внизу экрана).
 * Контейнер поппера всегда «голый» (popover-bare, см. core-theme.css): свою
 * поверхность рисует контент — иначе за скруглённой панелью виден
 * прямоугольник core-поповера. */
export function Popover({ position = "top-start", offset = DEFAULT_OFFSET, ...rest }: Props) {
  return <CorePopover position={position} offset={offset} popperClassName="popover-bare" {...rest} />;
}
