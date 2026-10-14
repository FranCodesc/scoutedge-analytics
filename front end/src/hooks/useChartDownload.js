import { useCallback, useState } from "react";
import { downloadChart } from "../api/chatApi";

const FAILURE_TEXT = "Impossibile scaricare il grafico. Riprova.";

/**
 * Gestisce il "Scarica" del pannello grafici: scarica il PNG, lo salva sul computer
 * con il suo nome e tiene lo stato (in corso / errore).
 *
 * @param {string | null} src indirizzo del grafico (da chartSrc), o null
 * @returns {{ download: () => Promise<void>, downloading: boolean, downloadError: string | null }}
 */
export function useChartDownload(src) {
  const [downloading, setDownloading] = useState(false);
  // L'errore si ricorda insieme al grafico a cui si riferisce: quando arriva un
  // grafico nuovo l'errore vecchio non vale più, senza bisogno di reset.
  const [failure, setFailure] = useState(null);

  const download = useCallback(async () => {
    if (!src || downloading) return;
    setDownloading(true);
    setFailure(null);
    try {
      const { blob, filename } = await downloadChart(src);
      // Link temporaneo con `download`: l'URL del blob è della nostra origine,
      // quindi qui il nome del file viene rispettato.
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      // Si libera la memoria del blob; il ritardo lascia al browser il tempo di avviare il salvataggio.
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
    } catch {
      setFailure({ src, message: FAILURE_TEXT });
    } finally {
      setDownloading(false);
    }
  }, [src, downloading]);

  return {
    download,
    downloading,
    downloadError: failure?.src === src ? failure.message : null,
  };
}
