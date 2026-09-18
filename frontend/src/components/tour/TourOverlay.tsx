// Оверлей тура (T-0132, спека E19 §9): затемнение с вырезом по DOM-якорю
// data-tour (+6px, радиус цели +6) и карточка-подсказка с мини-полосой
// прогресса. Геометрия снимается с живого DOM на каждом шаге и ресайзе —
// никаких зашитых координат; блокер закрывает продукт от кликов.
import { useCallback, useEffect, useRef, useState } from "react";
import { type CutRect, type Point, cutRectFor, tipPositionFor } from "../../tour/tourGeometry";
import { TOUR_PHASES, TOUR_STEPS } from "../../tour/tourMachine";
import { useTour } from "./TourProvider";

const TIP_WIDTH = 300;
const TIP_FALLBACK_HEIGHT = 140;

export function TourOverlay() {
  const { state, next, skip } = useTour();
  const [cut, setCut] = useState<CutRect | null>(null);
  const [tipPos, setTipPos] = useState<Point | null>(null);
  const [fading, setFading] = useState(false);
  const tipRef = useRef<HTMLDivElement | null>(null);
  const nextRef = useRef<HTMLButtonElement | null>(null);
  // База позиционирования карточки текущего шага (вырез либо вырез,
  // расширенный до низа элемента-просвета) — для уточняющего замера.
  const tipBaseRef = useRef<CutRect | null>(null);

  const stepConf = state.status === "steps" ? TOUR_STEPS[state.step] : null;

  const measure = useCallback(() => {
    if (!stepConf) return;
    const el = document.querySelector(`[data-tour="${stepConf.key}"]`);
    if (!(el instanceof HTMLElement)) {
      setCut(null);
      setTipPos(null);
      return;
    }
    const rect = el.getBoundingClientRect();
    const radius = Number.parseFloat(window.getComputedStyle(el).borderTopLeftRadius) || 0;
    const nextCut = cutRectFor(rect, radius);
    setCut(nextCut);
    // Опора карточки: обычно сам вырез; при clearanceKey — не выше низа
    // элемента-просвета (пилюля источников внутри композера → карточка
    // встаёт под композер целиком, как в принятом прототипе).
    let tipBase = nextCut;
    if (stepConf.clearanceKey) {
      const clearanceEl = document.querySelector(`[data-tour="${stepConf.clearanceKey}"]`);
      if (clearanceEl instanceof HTMLElement) {
        const clearanceBottom = clearanceEl.getBoundingClientRect().bottom;
        if (clearanceBottom > nextCut.top + nextCut.height) {
          tipBase = { ...nextCut, height: clearanceBottom - nextCut.top };
        }
      }
    }
    tipBaseRef.current = tipBase;
    const tip = tipRef.current;
    setTipPos(
      tipPositionFor(
        tipBase,
        {
          width: tip?.offsetWidth || TIP_WIDTH,
          height: tip?.offsetHeight || TIP_FALLBACK_HEIGHT,
        },
        { width: window.innerWidth, height: window.innerHeight },
        stepConf.placement,
      ),
    );
  }, [stepConf]);

  // Замер на каждом шаге и при ресайзе окна (вырез обязан пережить ресайз).
  useEffect(() => {
    if (!stepConf) return;
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [stepConf, measure]);

  // Второй замер после отрисовки карточки — фактическая высота уточняет
  // позицию (первый проход считает по фолбэку).
  useEffect(() => {
    if (!stepConf || !cut) return;
    const tip = tipRef.current;
    if (!tip) return;
    setTipPos(
      tipPositionFor(
        tipBaseRef.current ?? cut,
        { width: tip.offsetWidth, height: tip.offsetHeight },
        { width: window.innerWidth, height: window.innerHeight },
        stepConf.placement,
      ),
    );
  }, [stepConf, cut]);

  // Финал: затемнение растворяется (~0.5с), затем оверлей уходит совсем.
  useEffect(() => {
    if (state.status !== "finale") {
      setFading(false);
      return;
    }
    setFading(true);
    const t = window.setTimeout(() => {
      setFading(false);
      setCut(null);
      setTipPos(null);
    }, 550);
    return () => window.clearTimeout(t);
  }, [state.status]);

  const showSteps = state.status === "steps" && stepConf !== null;
  const showFadingCut = state.status === "finale" && fading && cut !== null;

  // Тур — модальный диалог: блокер снимает только клики, поэтому фокус нужно
  // забрать явно. Иначе он остаётся на кнопке под затемнением, и с клавиатуры
  // можно управлять приложением, которого не видно (T-0143).
  useEffect(() => {
    if (!showSteps) return;
    const restoreTo = document.activeElement;
    nextRef.current?.focus();
    return () => {
      if (restoreTo instanceof HTMLElement && document.contains(restoreTo)) restoreTo.focus();
    };
  }, [showSteps]);

  // Ловушка Tab: за пределами карточки на время тура ходить некуда. Выход
  // с клавиатуры остаётся — «Пропустить» внутри самой ловушки.
  useEffect(() => {
    if (!showSteps) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      const tip = tipRef.current;
      if (!tip) return;
      const stops = tip.querySelectorAll<HTMLElement>("button");
      if (stops.length === 0) return;
      const first = stops[0];
      const last = stops[stops.length - 1];
      const active = document.activeElement;
      const outside = !(active instanceof Node) || !tip.contains(active);
      if (e.shiftKey && (outside || active === first)) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && (outside || active === last)) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown, true);
    return () => document.removeEventListener("keydown", onKeyDown, true);
  }, [showSteps]);

  if (!showSteps && !showFadingCut) return null;

  return (
    <div className="tour-layer">
      {showSteps && <div className="tour-blocker" />}
      {cut && (
        <>
          {/* Затемнение — SVG-маска с дыркой по вырезу: гигантский
              box-shadow-spread из прототипа chromium местами отбрасывает
              при растеризации, маска рисуется надёжно; геометрия дырки
              анимируется CSS-транзишном (SVG geometry properties). */}
          <svg
            className={showFadingCut ? "tour-dim tour-dim-fade" : "tour-dim"}
            aria-hidden="true"
          >
            <defs>
              <mask id="tour-dim-mask">
                <rect width="100%" height="100%" fill="white" />
                <rect
                  className="tour-dim-hole"
                  x={cut.left}
                  y={cut.top}
                  width={cut.width}
                  height={cut.height}
                  rx={cut.radius}
                  ry={cut.radius}
                  fill="black"
                />
              </mask>
            </defs>
            <rect width="100%" height="100%" className="tour-dim-fill" mask="url(#tour-dim-mask)" />
          </svg>
          <div
            className={showFadingCut ? "tour-cut tour-cut-fade" : "tour-cut"}
            style={{
              left: cut.left,
              top: cut.top,
              width: cut.width,
              height: cut.height,
              borderRadius: cut.radius,
            }}
          />
        </>
      )}
      {showSteps && stepConf && (
        <div
          ref={tipRef}
          className="tour-tip"
          role="dialog"
          aria-modal="true"
          aria-label={stepConf.title}
          style={tipPos ? { left: tipPos.left, top: tipPos.top } : undefined}
        >
          <div className="tour-tip-bar" aria-hidden="true">
            {/* заливка — transform, не width: фаза N из 5 */}
            <i style={{ transform: `scaleX(${(state.step + 1) / TOUR_PHASES})` }} />
          </div>
          <b>{stepConf.title}</b>
          <p>{stepConf.text}</p>
          <div className="tour-tip-row">
            <button type="button" className="tour-tip-skip" onClick={skip}>
              Пропустить
            </button>
            <button type="button" className="tour-tip-next" ref={nextRef} onClick={next}>
              Далее
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
