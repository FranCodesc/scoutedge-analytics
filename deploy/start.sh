#!/usr/bin/env bash
# Script di avvio del container: avvia i servizi nell'ordine in cui dipendono
# l'uno dall'altro e, se uno di essi si ferma, fa terminare tutto il container
# con un codice diverso da 0 (così la piattaforma lo riavvia).
# Non stampa mai il valore delle variabili segrete.

set -u

log() { echo "[avvio] $*"; }

# Variabili obbligatorie: si controlla solo che ci siano, senza mai stamparle
# (i valori del limite di frequenza li valida il back end). Il limite deve
# essere sempre attivo online, e senza TRUST_PROXY tutti gli utenti avrebbero
# l'IP di nginx e condividerebbero un solo contatore: meglio non partire.
for var in OPENAI_API_KEY FRONTEND_ORIGIN RATE_LIMIT_WINDOW_MIN RATE_LIMIT_PER_IP RATE_LIMIT_GLOBAL TRUST_PROXY; do
  if [ -z "${!var:-}" ]; then
    log "ERRORE: variabile $var non impostata"
    exit 1
  fi
done

declare -A NOMI   # pid -> nome del servizio, per dire quale si è fermato
PIDS=()

# avvia <nome> <comando...>: avvia un servizio in background.
avvia() {
  local nome=$1
  shift
  "$@" &
  NOMI[$!]=$nome
  PIDS+=("$!")
  log "$nome avviato (pid $!)"
}

# Chiude con SIGTERM i servizi ancora attivi.
ferma_tutto() {
  local pid
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null
  done
}

# Attesa massima per ciascun servizio, in secondi. Sull'hardware condiviso della
# piattaforma l'avvio (soprattutto il caricamento delle librerie Python del data
# agent) può essere molto più lento che su un computer locale.
ATTESA_MAX=120

# attendi <nome> <url> <pid>: attende (al massimo ATTESA_MAX secondi) che il
# servizio risponda e si ferma subito se il suo processo è già terminato.
attendi() {
  local nome=$1 url=$2 pid=$3 i
  for i in $(seq 1 "$ATTESA_MAX"); do
    if ! kill -0 "$pid" 2>/dev/null; then
      log "ERRORE: $nome si è fermato durante l'avvio"
      return 1
    fi
    if curl -fsS -o /dev/null --max-time 2 "$url" 2>/dev/null; then
      log "$nome pronto"
      return 0
    fi
    sleep 1
  done
  log "ERRORE: $nome non risponde dopo $ATTESA_MAX secondi"
  return 1
}

# Arresto richiesto dalla piattaforma (docker stop): chiude i servizi ed esce.
trap 'log "arresto richiesto"; ferma_tutto; exit 0' TERM INT

# 1) Chroma, solo su 127.0.0.1. I dati stanno in una cartella temporanea: a ogni
#    avvio si riparte da zero e il manuale viene indicizzato di nuovo.
CHROMA_DATA=/tmp/chroma-data
mkdir -p "$CHROMA_DATA"
avvia "Chroma" chroma run --host 127.0.0.1 --port 8001 --path "$CHROMA_DATA"
attendi "Chroma" http://127.0.0.1:8001/api/v2/heartbeat "${PIDS[-1]}" || { ferma_tutto; exit 1; }

# 2) Indicizzazione del manuale (deve produrre 18 chunk).
log "Indicizzazione del manuale..."
(cd "/app/back end" && node scripts/ingestHandbook.js) || { log "ERRORE: indicizzazione fallita"; ferma_tutto; exit 1; }

# 3) Data agent (FastAPI), solo su 127.0.0.1. All'avvio legge e pulisce il CSV.
cd /app/data_agent
avvia "Data agent" uvicorn main:app --host 127.0.0.1 --port 8000
attendi "Data agent" http://127.0.0.1:8000/ "${PIDS[-1]}" || { ferma_tutto; exit 1; }

# 4) Back end (Express): ascolta sulla porta 3001 di tutte le interfacce del
#    container, ma la porta non è pubblicata, quindi si raggiunge solo tramite nginx.
cd "/app/back end"
avvia "Back end" node src/index.js
attendi "Back end" http://127.0.0.1:3001/ "${PIDS[-1]}" || { ferma_tutto; exit 1; }

# 5) nginx, unico servizio raggiungibile dall'esterno (porta 7860).
avvia "nginx" nginx -c /app/deploy/nginx.conf -g "daemon off;"
attendi "nginx" http://127.0.0.1:7860/ "${PIDS[-1]}" || { ferma_tutto; exit 1; }

log "Tutti i servizi sono attivi."

# Resta in attesa: appena uno dei servizi termina, per qualsiasi motivo, si
# chiude tutto e il container esce con un codice diverso da 0, così la
# piattaforma lo riavvia. Anche un'uscita "pulita" (codice 0) di un servizio
# è un guasto: dovrebbero restare attivi per sempre.
FINITO=""
wait -n -p FINITO "${PIDS[@]}"
CODICE=$?
log "ERRORE: ${NOMI[$FINITO]:-un servizio} si è fermato (codice $CODICE): chiusura del container"
ferma_tutto
[ "$CODICE" -eq 0 ] && CODICE=1
exit "$CODICE"
