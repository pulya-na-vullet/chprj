// Генеративные аватар-пресеты (T-0127, спека E19 §3.3, принятый прототип
// flow-full.html): базовый тон + три radial-градиента + SVG-геометрия +
// зерно feTurbulence поверх (blend overlay). Детерминированная функция от
// индекса пресета — рисуется в любом размере (60px онбординг, 26px сайдбар).
//
// Палитры пресетов — данные принятого генеративного арта, а не цвета
// интерфейса: в UI-хром они не попадают, токены дизайн-системы к ним не
// применяются (аналог доменных цветов док-иконок, но со свободной палитрой).

export type PresetInk = "light" | "dark";

interface AvatarPreset {
  /** Базовый тон нижнего слоя. */
  base: string;
  /** Цвет инициалов поверх: светлый почти всюду, тёмный на золото-беж. */
  ink: PresetInk;
  /** Три radial-градиента: [цвет, x%, y%, радиус%]. */
  gradients: ReadonlyArray<readonly [string, number, number, number]>;
  /** SVG-фрагмент геометрии (полоса-хорда, треугольники, точки). */
  shapes: string;
}

// Порядок палитр зафиксирован спекой: тил-лайм, небо, закат, золото-беж,
// зелёный, графит. Индекс = значение avatar_preset в профиле.
export const AVATAR_PRESETS: readonly AvatarPreset[] = [
  {
    base: "#57B489",
    ink: "light",
    gradients: [
      ["#2FA3A8", 30, 18, 72],
      ["#7CBF5B", 62, 52, 70],
      ["#CBDB4A", 52, 88, 66],
    ],
    shapes:
      "<rect x='-20' y='38' width='140' height='10' fill='white' fill-opacity='0.22' transform='rotate(-18 50 50)'/><polygon points='78,68 90,86 66,86' fill='%23106B60' fill-opacity='0.28'/>",
  },
  {
    base: "#6FA7E0",
    ink: "light",
    gradients: [
      ["#4E8FD9", 28, 22, 70],
      ["#7FB5E8", 70, 42, 68],
      ["#BFDDF0", 60, 88, 64],
    ],
    shapes:
      "<rect x='-20' y='32' width='140' height='6' fill='white' fill-opacity='0.28' transform='rotate(8 50 50)'/><rect x='-20' y='58' width='140' height='3' fill='white' fill-opacity='0.2' transform='rotate(8 50 50)'/><polygon points='24,18 34,32 14,32' fill='%23134A8C' fill-opacity='0.25'/>",
  },
  {
    base: "#E88A76",
    ink: "light",
    gradients: [
      ["#E8956F", 30, 20, 70],
      ["#E86F6F", 68, 55, 68],
      ["#F2C79E", 50, 90, 64],
    ],
    shapes:
      "<rect x='-20' y='54' width='140' height='13' fill='white' fill-opacity='0.2' transform='rotate(-30 50 50)'/><polygon points='68,20 80,36 56,36' fill='%23A8352B' fill-opacity='0.25'/>",
  },
  {
    base: "#D6B87F",
    ink: "dark",
    gradients: [
      ["#C9A96B", 30, 22, 70],
      ["#E3CA96", 66, 50, 70],
      ["#F4E7C9", 52, 88, 62],
    ],
    shapes:
      "<rect x='-20' y='44' width='140' height='5' fill='%236B5426' fill-opacity='0.2' transform='rotate(-24 50 50)'/><polygon points='30,60 42,78 18,78' fill='white' fill-opacity='0.35'/>",
  },
  {
    base: "#5FA985",
    ink: "light",
    gradients: [
      ["#3E8F6E", 28, 25, 72],
      ["#79BE9C", 66, 52, 70],
      ["#CDE8D8", 54, 90, 62],
    ],
    shapes:
      "<rect x='46' y='-20' width='9' height='140' fill='white' fill-opacity='0.2' transform='rotate(14 50 50)'/><polygon points='70,58 80,72 60,72' fill='%23175A3C' fill-opacity='0.3'/><polygon points='26,26 34,38 18,38' fill='white' fill-opacity='0.3'/>",
  },
  {
    base: "#989CA6",
    ink: "light",
    gradients: [
      ["#7E828E", 28, 22, 70],
      ["#AEB2BC", 66, 52, 70],
      ["#DDDEE3", 54, 90, 62],
    ],
    shapes:
      "<rect x='-20' y='40' width='140' height='8' fill='white' fill-opacity='0.28' transform='rotate(-40 50 50)'/><circle cx='72' cy='30' r='6' fill='%23303540' fill-opacity='0.25'/>",
  },
];

const NOISE =
  "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 220 220'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/><feColorMatrix type='saturate' values='0'/></filter><rect width='100%25' height='100%25' filter='url(%23n)' opacity='0.7'/></svg>\")";

// Масштаб зерна под размер отрисовки: крупный аватар и мелкий свотч.
const NOISE_SIZE = { lg: "220px 220px", sm: "90px 90px" } as const;

export type PresetSize = keyof typeof NOISE_SIZE;

export interface PresetBackground {
  backgroundImage: string;
  backgroundBlendMode: string;
  backgroundSize: string;
}

function shapesLayer(p: AvatarPreset): string {
  return `url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100' preserveAspectRatio='none'>${p.shapes}</svg>")`;
}

/** CSS-слои пресета для инлайн-стиля (вычисляемая отрисовка, не косметика). */
export function presetBackground(index: number, size: PresetSize): PresetBackground {
  const p = AVATAR_PRESETS[index] ?? AVATAR_PRESETS[0];
  const radials = p.gradients.map(
    ([color, x, y, r]) => `radial-gradient(circle at ${x}% ${y}%, ${color} 0%, transparent ${r}%)`,
  );
  const layers = [
    NOISE,
    shapesLayer(p),
    ...radials,
    `linear-gradient(0deg, ${p.base}, ${p.base})`,
  ];
  return {
    backgroundImage: layers.join(", "),
    backgroundBlendMode: "overlay, normal, normal, normal, normal, normal",
    backgroundSize: `${NOISE_SIZE[size]}, 100% 100%, auto, auto, auto, auto`,
  };
}

/** Инициалы из имени и фамилии: по первой букве, живьём при вводе. */
export function initialsOf(first?: string | null, last?: string | null): string {
  const f = (first ?? "").trim();
  const l = (last ?? "").trim();
  return ((f[0] ?? "") + (l[0] ?? "")).toUpperCase();
}
