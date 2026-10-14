import { useState } from "react";

/**
 * Grafico dentro il fumetto di una risposta. `src` arriva già validato da chartSrc().
 * Se l'immagine non si carica (file sparito, data agent spento) al suo posto compare
 * un messaggio, invece dell'icona di immagine rotta.
 *
 * Niente `loading="lazy"`: il grafico è in vista appena la risposta arriva, quindi il
 * caricamento in ritardo non porta vantaggi e Chrome chiederebbe dimensioni esplicite.
 *
 * `onLoad` (opzionale): il layout cambia quando l'immagine finisce di caricarsi, perché
 * prima non se ne conosce l'altezza; il chiamante lo usa per riportare la chat in fondo.
 *
 * @param {{ src: string, onLoad?: () => void }} props
 */
export default function ChartImage({ src, onLoad }) {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return (
      <p className="mt-2 text-xs text-white/70">
        Il grafico non è al momento disponibile.
      </p>
    );
  }

  return (
    <img
      src={src}
      alt="Grafico generato dall'analisi dei dati"
      onLoad={onLoad}
      onError={() => setFailed(true)}
      className="mt-2 w-full max-w-lg rounded-lg bg-white"
    />
  );
}
