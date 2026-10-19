import { memo } from "react";

// Campo da calcio statico, con linee in percentuale (il cerchio non si deforma).
// Mobile: verticale. Desktop (lg): orizzontale. Memo evita ri-render a ogni messaggio.
const line = "absolute border-2 border-white/45";
const spot =
  "absolute size-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white/60";

// Grana dell'erba (rumore SVG, statico) e luce dei riflettori
const NOISE =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.6'/%3E%3C/svg%3E\")";

function Surface({ direction }) {
  return (
    <>
      <div
        className="absolute inset-0"
        style={{
          backgroundImage: `repeating-linear-gradient(${direction}, #166534 0, #166534 7.14%, #15803d 7.14%, #15803d 14.28%)`,
        }}
      />
      <div
        className="absolute inset-0 opacity-[0.14]"
        style={{ backgroundImage: NOISE }}
      />
      {/* Luce dall'alto + vignettatura */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_70%_55%_at_50%_25%,rgba(255,255,255,0.14),transparent_70%)]" />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_45%,rgba(2,20,10,0.55)_100%)]" />
    </>
  );
}

// Archi d'angolo (stessa posizione in entrambi gli orientamenti)
function Corners() {
  const base = "absolute size-4 border-white/45";
  return (
    <>
      <div
        className={`${base} left-[3%] top-[3%] rounded-br-full border-b-2 border-r-2`}
      />
      <div
        className={`${base} right-[3%] top-[3%] rounded-bl-full border-b-2 border-l-2`}
      />
      <div
        className={`${base} bottom-[3%] left-[3%] rounded-tr-full border-r-2 border-t-2`}
      />
      <div
        className={`${base} bottom-[3%] right-[3%] rounded-tl-full border-l-2 border-t-2`}
      />
    </>
  );
}

function Vertical() {
  return (
    <div className="absolute inset-0 lg:hidden">
      <Surface direction="180deg" />
      <div className={`${line} inset-[3%]`} />
      <Corners />
      <div
        className={`${line} inset-x-[3%] top-1/2 -translate-y-px border-0 border-t-2`}
      />
      <div
        className={`${line} left-1/2 top-1/2 aspect-square w-[28%] -translate-x-1/2 -translate-y-1/2 rounded-full`}
      />
      <div className={`${spot} left-1/2 top-1/2`} />
      {/* Porte */}
      <div
        className={`${line} left-1/2 top-[1%] h-[2%] w-[14%] -translate-x-1/2 border-b-0`}
      />
      <div
        className={`${line} bottom-[1%] left-1/2 h-[2%] w-[14%] -translate-x-1/2 border-t-0`}
      />
      {/* Aree di rigore, porta, dischetti e archi */}
      {["top-[3%]", "bottom-[3%]"].map((side) => (
        <div key={side}>
          <div
            className={`${line} left-1/2 h-[15%] w-[60%] -translate-x-1/2 ${side}`}
          />
          <div
            className={`${line} left-1/2 h-[6%] w-[30%] -translate-x-1/2 ${side}`}
          />
        </div>
      ))}
      <div className={`${spot} left-1/2 top-[13%]`} />
      <div className={`${spot} bottom-[13%] left-1/2 translate-y-1/2`} />
      <div
        className={`${line} left-1/2 top-[18%] aspect-2/1 w-[26%] -translate-x-1/2 rounded-b-full border-t-0`}
      />
      <div
        className={`${line} bottom-[18%] left-1/2 aspect-2/1 w-[26%] -translate-x-1/2 rounded-t-full border-b-0`}
      />
    </div>
  );
}

function Horizontal() {
  return (
    <div className="absolute inset-0 hidden lg:block">
      <Surface direction="90deg" />
      <div className={`${line} inset-[3%]`} />
      <Corners />
      <div
        className={`${line} inset-y-[3%] left-1/2 -translate-x-px border-0 border-l-2`}
      />
      <div
        className={`${line} left-1/2 top-1/2 aspect-square h-[40%] -translate-x-1/2 -translate-y-1/2 rounded-full`}
      />
      <div className={`${spot} left-1/2 top-1/2`} />
      {/* Porte */}
      <div
        className={`${line} left-[1%] top-1/2 h-[14%] w-[1.6%] -translate-y-1/2 border-r-0`}
      />
      <div
        className={`${line} right-[1%] top-1/2 h-[14%] w-[1.6%] -translate-y-1/2 border-l-0`}
      />
      {/* Aree di rigore, porta, dischetti e archi */}
      {["left-[3%]", "right-[3%]"].map((side) => (
        <div key={side}>
          <div
            className={`${line} top-1/2 h-[60%] w-[15%] -translate-y-1/2 ${side}`}
          />
          <div
            className={`${line} top-1/2 h-[30%] w-[6%] -translate-y-1/2 ${side}`}
          />
        </div>
      ))}
      <div className={`${spot} left-[13%] top-1/2`} />
      <div className={`${spot} right-[13%] top-1/2 translate-x-1/2`} />
      <div
        className={`${line} left-[18%] top-1/2 aspect-1/2 h-[26%] -translate-y-1/2 rounded-r-full border-l-0`}
      />
      <div
        className={`${line} right-[18%] top-1/2 aspect-1/2 h-[26%] -translate-y-1/2 rounded-l-full border-r-0`}
      />
    </div>
  );
}

function PitchBackground() {
  return (
    <div className="pointer-events-none absolute inset-0" aria-hidden="true">
      <Vertical />
      <Horizontal />
    </div>
  );
}

export default memo(PitchBackground);
