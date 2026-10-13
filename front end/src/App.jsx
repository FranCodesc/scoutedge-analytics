import { useState } from 'react'
import { sendMessage, chartSrc, ApiError } from './api/chatApi'

// Pagina TEMPORANEA di verifica del client API (FE-1): sarà sostituita in FE-2.
export default function App() {
  const [input, setInput] = useState('')
  const [sessionId, setSessionId] = useState(null) // vive solo nello stato React
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null) // risposta 200 del contratto
  const [error, setError] = useState(null) // ApiError

  async function handleSubmit(e) {
    e.preventDefault()
    setBusy(true)
    setResult(null)
    setError(null)
    try {
      // Nessuna validazione lato client, di proposito: serve per provare gli errori del server.
      const data = await sendMessage({ message: input, sessionId })
      setSessionId(data.sessionId) // il contratto: si sovrascrive sempre con quello ricevuto
      setResult(data)
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError({ code: 'INTERNAL_ERROR', message: String(err) }))
    } finally {
      setBusy(false)
    }
  }

  const imgSrc = result ? chartSrc(result.chartUrl) : null

  return (
    <main className="min-h-full bg-pitch-950 p-6 text-white">
      <h1 className="font-display text-4xl font-extrabold tracking-wide">
        Scout<span className="text-edge">Edge</span>
        <span className="ml-3 text-base font-semibold text-white/60">verifica client API</span>
      </h1>

      <form onSubmit={handleSubmit} className="mt-6 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          aria-label="Messaggio"
          className="min-w-0 flex-1 rounded-lg border border-white/15 bg-pitch-900 px-3 py-2 outline-none focus:border-edge"
        />
        <button
          type="submit"
          disabled={busy}
          className="rounded-lg bg-edge px-4 py-2 font-semibold text-pitch-950 disabled:opacity-40"
        >
          {busy ? 'Attendo…' : 'Invia'}
        </button>
      </form>

      <p className="mt-3 text-xs text-white/60">sessionId: {sessionId ?? '(nessuno)'}</p>

      {error && (
        <pre className="mt-4 overflow-auto rounded-lg border border-red-400/40 bg-pitch-900 p-3 text-sm text-red-200">
          {JSON.stringify({ name: error.name, status: error.status, code: error.code, message: error.message }, null, 2)}
        </pre>
      )}

      {result && (
        <pre className="mt-4 overflow-auto whitespace-pre-wrap rounded-lg border border-white/15 bg-pitch-900 p-3 text-sm">
          {JSON.stringify(result, null, 2)}
        </pre>
      )}

      {imgSrc && (
        <img src={imgSrc} alt="Grafico generato dall'analisi dei dati" className="mt-4 max-w-full rounded-lg bg-white" />
      )}
    </main>
  )
}
