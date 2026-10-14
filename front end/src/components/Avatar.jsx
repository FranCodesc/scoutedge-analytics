/**
 * Avatar dell'assistente, accanto a risposte, attesa ed errori.
 * Nel prototipo questo SVG era copiato in tre punti: qui è uno solo.
 */
export default function Avatar() {
  return (
    <div className="grid size-8 shrink-0 place-items-center">
      <svg
        viewBox="0 0 24 24"
        className="size-9 text-edge"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        role="img"
        aria-label="Assistente"
      >
        <rect x="5" y="8" width="14" height="11" rx="3.5" />
        <path d="M12 8V5.5M3 12.5v3M21 12.5v3M9.5 16.2h5" />
        <circle cx="12" cy="4.5" r="1.2" fill="currentColor" />
        <circle cx="9.3" cy="12.3" r="1.1" fill="currentColor" stroke="none" />
        <circle cx="14.7" cy="12.3" r="1.1" fill="currentColor" stroke="none" />
      </svg>
    </div>
  );
}
