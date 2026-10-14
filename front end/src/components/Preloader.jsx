import { useEffect, useState } from "react";
import Ball from "./Ball";

const MESSAGES = [
  "Caricamento dei dati di campo…",
  "Analisi dei giocatori…",
  "Calcolo delle statistiche…",
  "Preparazione del report scouting…",
];

/**
 * Preloader a schermo intero per ScoutEdge.
 *
 * Props:
 *  - progress: numero 0-100 (opzionale). Se omesso, la barra avanza in automatico
 *    fino al 90% e completa solo quando `loading` diventa false.
 *  - loading: true finché la pagina sta caricando; a false il preloader sfuma e sparisce.
 */
export default function Preloader({ loading = true, progress }) {
  const [auto, setAuto] = useState(8);
  const [msg, setMsg] = useState(0);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    if (progress !== undefined) return;
    const id = setInterval(() => {
      setAuto((p) => (p < 90 ? p + (90 - p) * 0.08 + 0.5 : p));
    }, 120);
    return () => clearInterval(id);
  }, [progress]);

  useEffect(() => {
    const id = setInterval(
      () => setMsg((m) => (m + 1) % MESSAGES.length),
      1600,
    );
    return () => clearInterval(id);
  }, []);

  // Quando `loading` diventa false il preloader sfuma (700 ms) e poi si smonta.
  // `visible` parte già a true, e `loading` non torna mai a true: niente da riaccendere.
  useEffect(() => {
    if (loading) return;
    const id = setTimeout(() => setVisible(false), 700);
    return () => clearTimeout(id);
  }, [loading]);

  if (!visible) return null;

  const value = Math.round(loading ? (progress ?? auto) : 100);

  return (
    // L'uscita è solo una sfumatura di trasparenza (niente zoom): animare solo
    // l'opacità è la cosa più leggera per il browser, e will-change gli fa preparare
    // il livello in anticipo, così non scatta quando sotto c'è il campo da disegnare.
    <div
      role="status"
      aria-live="polite"
      aria-label="Caricamento ScoutEdge"
      className={`fixed inset-0 z-50 h-dvh flex flex-col items-center justify-center gap-10 overflow-hidden bg-pitch-950 px-6 transition-opacity duration-700 ease-in will-change-[opacity] ${
        loading ? "opacity-100" : "opacity-0"
      }`}
    >
      {/* Campo stilizzato di sfondo */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.07]"
        aria-hidden="true"
      >
        <div className="absolute inset-6 rounded-lg border-2 border-white" />
        <div className="absolute inset-y-6 left-1/2 w-0.5 -translate-x-1/2 bg-white" />
        <div className="absolute left-1/2 top-1/2 size-48 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white" />
      </div>
      <div
        className="pointer-events-none absolute left-1/2 top-1/2 size-[min(36rem,140vw)] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[radial-gradient(circle,rgba(61,255,139,0.12),transparent_65%)]"
        aria-hidden="true"
      />

      {/* Pallone che rimbalza */}
      <div className="relative flex h-32 flex-col items-center justify-end">
        <div className="animate-ball-bounce">
          <Ball className="animate-ball-spin text-6xl" />
        </div>
        <div className="mt-1 h-2 w-14 animate-shadow-pulse rounded-full bg-black/60" />
      </div>

      {/* Logo */}
      <h1 className="animate-fade-up font-display text-6xl font-extrabold leading-none tracking-wide text-white sm:text-7xl">
        Scout<span className="text-edge">Edge</span>
      </h1>

      {/* Progresso */}
      <div className="w-full max-w-xs">
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/10">
          <div
            className="h-full origin-left rounded-full bg-edge transition-transform duration-300 ease-out will-change-transform"
            style={{ transform: `scaleX(${value / 100})` }}
          />
        </div>
        <div className="mt-3 flex items-center justify-between text-xs text-white/60">
          <span key={msg} className="animate-fade-up">
            {MESSAGES[msg]}
          </span>
          <span className="tabular-nums text-edge">{value}%</span>
        </div>
      </div>
    </div>
  );
}
