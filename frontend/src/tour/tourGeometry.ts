// Геометрия спотлайта (T-0132, спека E19 §9): вырез точно повторяет контур
// цели с полем 6px и радиусом цели +6; никаких зашитых координат — рект
// цели снимается с DOM-якоря data-tour при каждом шаге и ресайзе.

import type { TipPlacement } from "./tourMachine";

export const CUT_PAD = 6;
const TIP_GAP = 16;
const VIEWPORT_MARGIN = 12;

export interface TargetRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

export interface CutRect extends TargetRect {
  radius: number;
}

export interface Size {
  width: number;
  height: number;
}

export interface Point {
  left: number;
  top: number;
}

export function cutRectFor(target: TargetRect, targetRadius: number): CutRect {
  // Пилюли задают радиус 999px «с запасом» — приводим к фактическому
  // (половина меньшей стороны), иначе SVG-дырка и CSS-рамка клампят его
  // по-разному (эллиптические углы против круглых торцов) и по бокам
  // выреза остаются тёмные серпы.
  const effective = Math.min(targetRadius, target.width / 2, target.height / 2);
  return {
    left: target.left - CUT_PAD,
    top: target.top - CUT_PAD,
    width: target.width + CUT_PAD * 2,
    height: target.height + CUT_PAD * 2,
    radius: effective + CUT_PAD,
  };
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

/** Позиция карточки-подсказки: под вырезом (по центру) или справа от него
 * (по верху), с зажимом в границы вьюпорта. Если снизу места нет (композер
 * в открытом чате прижат к низу экрана), карточка переворачивается наверх —
 * иначе зажим уложил бы её поверх выделенной области. */
export function tipPositionFor(
  cut: CutRect,
  tip: Size,
  viewport: Size,
  placement: TipPlacement,
): Point {
  let left: number;
  let top: number;
  if (placement === "right") {
    left = cut.left + cut.width + TIP_GAP;
    top = cut.top;
  } else {
    left = Math.round(cut.left + cut.width / 2 - tip.width / 2);
    top = cut.top + cut.height + TIP_GAP;
    if (top + tip.height > viewport.height - VIEWPORT_MARGIN) {
      top = cut.top - tip.height - TIP_GAP;
    }
  }
  return {
    left: clamp(left, VIEWPORT_MARGIN, viewport.width - tip.width - VIEWPORT_MARGIN),
    top: clamp(top, VIEWPORT_MARGIN, viewport.height - tip.height - VIEWPORT_MARGIN),
  };
}
