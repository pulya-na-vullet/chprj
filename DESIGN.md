---
# Машиночитаемая часть закона: читает детектор impeccable
# (design-system-font/color/radius). Значения = tokens.css; синхронность
# сторожит frontend/src/test/designLaw.test.ts.
typography:
  ui:
    fontFamily: "Alfa Interface Sans"
  display:
    fontFamily: "Styrene A LC Black"
  mono:
    fontFamily: "SFMono-Regular"
colors:
  gray-01: "#FFFFFF"
  gray-02: "#0E0E0E"
  gray-03: "#1C1C1E"
  gray-04: "#27272A"
  gray-05: "#444444"
  gray-06: "#54545C"
  gray-07: "#86868E"
  gray-08: "#9C9CA3"
  gray-09: "#F2F3F5"
  gray-10: "#D5D6DC"
  gray-11: "#E7E8EA"
  gray-12: "#7A7A7A"
  gray-13: "#EEEEEE"
  gray-14: "#D9D6CE"
  gray-15: "#AEAEB6"
  gray-16: "#FDFCFC"
  gray-17: "rgba(3, 3, 6, 0.88)"
  gray-18: "#C9C9CF"
  gray-19: "#F8F8F9"
  gray-20: "rgba(20, 20, 45, 0.35)"
  gray-23: "#6E6E76"
  gray-21: "rgba(255, 255, 255, 0.72)"
  gray-22: "rgba(255, 255, 255, 0.92)"
  gray-24: "rgba(10, 10, 14, 0.55)"
  red-01: "#EF3124"
  red-02: "#FC493D"
  red-04: "#EC2D20"
  red-05: "#F2968D"
  red-08: "#F3EAEB"
  red-10: "rgba(239, 49, 36, 0.2)"
  red-11: "#E8281B"
  red-13: "#FFEBEB"
  blue-01: "#2A77EF"
  blue-08: "#EFF4FF"
  blue-09: "#E6EEFF"
  blue-12: "#E7E9F4"
  green-01: "#39A373"
  green-08: "#EAF4EF"
  green-10: "rgba(57, 163, 115, 0.25)"
  yellow-01: "#A06B00"
  yellow-08: "#FFF6D6"
  beige-01: "#F4ECE0"
  beige-02: "#D2B488"
rounded:
  row: 8px
  btn: 8px
  card: 16px
  panel: 12px
  chip: 6px
  micro: 2px
  pill: 999px
  composer: 20px
  composer-outer: 21px
---

# DESIGN.md — дизайн-закон «Нейроюриста»

Это закон, а не справочник: любое изменение UI сверяется с этим файлом до
написания кода. Планка качества — Legora, нейроюрист Яндекса, Альфа-Бизнес:
спокойный, плотный, «дорогой» интерфейс, который не выглядит сгенерированным.

## Идентичность

- Язык Альфа-Банка: `@alfalab/core-components` + визуальный язык Kurs.
- Монохром + один акцент. Красный `--red-01` (#EF3124) — только действие,
  фокус, бренд-марка. Никогда — декор, фон секций, градиент.
- Русскоязычный UI, деловой тон (голос — в PRODUCT.md).

## Цвет

- Единственный источник цвета — `frontend/src/styles/tokens.css`.
- В компонентах и фичевых CSS ноль сырых hex/rgba — только `var(...)`.
- Два уровня:
  1. Примитивы Kurs (`--gray-NN`, `--red-NN`, `--blue-01`, `--green-01`) —
     живут только в tokens.css; используются только в tokens.css (алиасы)
     и core-theme.css (маппинг на core-components).
  2. Семантические алиасы — то, чем пользуются компоненты и фичевые CSS:
     фоны/линии (`--bg`, `--card`, `--line`, `--line-2`, `--line-soft`,
     `--hover`, `--hover-2`, `--active`, `--overlay`, `--glass`,
     `--glass-strong`), текстовая шкала (`--ink`, `--ink-2`, `--ink-3`,
     `--muted`, `--muted-2`, `--faint`, `--disabled`, `--ghost`, `--dark`,
     `--dark-2`, `--on-dark`, `--on-dark-2`), акцент (`--accent`,
     `--accent-hover`, `--accent-bg`, `--accent-line`, `--accent-glow`), информационные
     (`--info-bg`, `--info-bg-strong`), док-иконки (`--doc-ico-*`).
- Не хватает оттенка → добавь примитив в шкалу + алиас; инлайн запрещён.
- Статусные цвета — только токенами: `--ok`/`--ok-bg`/`--ok-line`,
  `--warn`/`--warn-bg`, `--danger`/`--danger-bg`. Tailwind/Material-палитры
  (#dc2626, #ecfdf5, #15803d…) запрещены.

## Типографика

- Alfa Interface Sans (400/500/700) — весь UI (`--font-ui`).
- Styrene A LC Black — только бренд-марка и крупные заголовки
  (`--font-display`).
- Моноширинный (`--font-mono`, системный SF Mono/Menlo) — только цитаты
  норм и технические идентификаторы (id моделей, коды).
- Шкала размеров: 11 (uppercase-подписи), 12, 13 (основной UI), 14, 15,
  20, 28. Значения вне шкалы (12.5px и т.п.) — существующий долг, не образец.
- Межбуквенный интервал: display-заголовки −0.02em; uppercase-подписи +0.06em.

## Компоненты

- core-components — только через обёртки `frontend/src/ui/` (Button,
  IconButton, Checkbox, Tooltip, Popover, ConfirmDialog, Skeleton).
  Прямой импорт `@alfalab/core-components/*` вне `src/ui/` запрещён.
- Нужен новый примитив → сначала обёртка в `src/ui/` с дефолтами Kurs,
  потом использование в фичах.
- Дефолты обёрток: Button `view="outlined" size={40}`; IconButton
  `view="secondary" size={32}`; Checkbox `size={20}`.

## Слои CSS

tokens.css (примитивы + алиасы) → core-theme.css (маппинг на переменные
core-components; справа только `var()` — новых значений там нет) → фичевые
файлы (`sources.css`, `files.css`, …). Новый CSS кладётся файлом на фичу;
`styles.css` не растёт (его распил — отдельная задача чистки).

## Геометрия

- Радиусы — только шкала: `--r-micro` (2, полоски/каретки), `--r-chip` (6,
  чипы и мелкие иконки), `--r-row`/`--r-btn` (8), `--r-panel` (12, меню и
  малые поповеры), `--r-card` (16), `--r-pill` (999), `--r-composer`/
  `--r-composer-outer` (20/21, только композер). Других нет.
- Тени — только токены: `--shadow-1`/`--shadow-2` (покой/подъём поверхностей,
  альфа ≤ 0.1, максимум два слоя), `--shadow-3`/`--shadow-4` (поповеры и
  модалки), фирменные составные `--shadow-glass`, `--shadow-window`,
  `--shadow-composer`. Цветные glow запрещены.
- Плотность: ряд списка 28–36px, карточки с padding 16.

## Motion

- 120–200ms, `ease-out` / `cubic-bezier(0.2, 0, 0, 1)`. Без bounce/elastic.
- Анимация — обратная связь (hover, появление поповера), не украшение.
- Единственная длинная анимация — «дыхание» активного композера
  (`composer-breathe`, 3.6s, утверждено клиентом в E09); новые длинные
  анимации не добавлять.
- На загрузке списков — скелетоны, не спиннеры.

## Анти-паттерны (запрещено)

- Сырые hex/rgba в компонентах и фичевых CSS; чужие палитры.
- Градиенты, «AI-фиолетовый», чистый `#000`.
- Стат-плашки, кричащие чипы, карточки-в-карточках.
- Эмодзи в интерфейсе; Inter и прочие «дефолтные» шрифты.
- Инлайн `style={{...}}` для косметики (допустим только для вычисляемой
  геометрии — ширина сайдбара и т.п.).

## Инструменты

- **impeccable** сторожит закон: `make impeccable` ставит скилл +
  advisory-hook Claude Code (per-machine — `.claude/` гитигнорен).
  Детектор: `npx impeccable detect frontend/src`. Калибровка —
  `.impeccable/config.json` (коммитится). Hook советует на каждой правке;
  pre-push блокирует при любых находках detect (при изменениях
  `frontend/**`). Warning-остаток Фазы 2 помечен inline-игнорами
  `impeccable-disable-next-line` с комментарием — снять при полировке.
- **Витрина токенов:** `npm --prefix frontend run design:preview` собирает
  `frontend/design-preview/` из tokens.css; витрина синкается в
  claude.ai/design (проект «nfs-neurolegal») через DesignSync.
- **Baseline долга:** `docs/superpowers/specs/2026-07-08-impeccable-baseline.json`
  (local-only). Чистка — отдельными сессиями, не «по пути».
