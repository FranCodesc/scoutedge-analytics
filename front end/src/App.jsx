import { useEffect, useState } from "react";
import Chat from "./components/Chat";
import Preloader from "./components/Preloader";

// Durata del preloader (scelta di progetto: 3 secondi). È una scelta grafica, non
// legata a un caricamento reale: l'app è già pronta, il preloader è parte dell'identità.
const PRELOADER_MS = 3000;

export default function App() {
  const [loading, setLoading] = useState(true);

  // Il timer spegne `loading`; il cleanup lo annulla se il componente si smonta
  // (in sviluppo StrictMode monta due volte: il primo timer viene annullato).
  useEffect(() => {
    const id = setTimeout(() => setLoading(false), PRELOADER_MS);
    return () => clearTimeout(id);
  }, []);

  return (
    <>
      <Chat />
      <Preloader loading={loading} />
    </>
  );
}
