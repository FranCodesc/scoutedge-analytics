// Pallone: emoji ⚽ (il disegno cambia in base al sistema: Apple, Android, Windows).
// La dimensione si imposta con classi di testo (es. text-6xl).
export default function Ball({ className = "text-6xl" }) {
  return (
    <span
      className={`inline-block select-none leading-none ${className}`}
      aria-hidden="true"
    >
      ⚽
    </span>
  );
}
