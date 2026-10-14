import { useSyncExternalStore } from "react";

/**
 * Si iscrive agli eventi "online"/"offline" del browser. React richiama la funzione
 * passata quando uno dei due scatta, e rilegge lo stato con getSnapshot.
 */
function subscribe(onChange) {
  window.addEventListener("online", onChange);
  window.addEventListener("offline", onChange);
  return () => {
    window.removeEventListener("online", onChange);
    window.removeEventListener("offline", onChange);
  };
}

const getSnapshot = () => navigator.onLine;

// Lato server (non usato in questo progetto, ma richiesto dall'API): si assume online.
const getServerSnapshot = () => true;

/**
 * true se il browser dice di essere online. Attenzione: "online" non garantisce che
 * il back end sia raggiungibile; quel caso lo gestisce l'errore NETWORK_ERROR in chat.
 */
export function useOnlineStatus() {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
