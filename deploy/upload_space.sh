#!/usr/bin/env bash
# Carica sullo Space di Hugging Face una copia dei soli file committati.
#
# Uso:
#   deploy/upload_space.sh <utente/nome-space> --prova   elenca i file, non carica nulla
#   deploy/upload_space.sh <utente/nome-space>           carica
#
# Perché si parte da "git archive" e non dalla cartella di lavoro: l'esportazione
# contiene esattamente ciò che sta nel commit corrente (HEAD), quindi non
# possono finire sullo Space file locali non versionati come .env, venv/ o
# node_modules/. Le modifiche non ancora committate non vengono caricate.
# Per caricare serve lo strumento "hf" (pip install -U huggingface_hub) e
# l'accesso già effettuato con "hf auth login": il token non passa da questo script.

set -euo pipefail
export GIT_OPTIONAL_LOCKS=0

SPACE="${1:-}"
MODO="${2:-}"

if [ -z "$SPACE" ]; then
  echo "Uso: $0 <utente/nome-space> [--prova]" >&2
  exit 2
fi
if [ -n "$MODO" ] && [ "$MODO" != "--prova" ]; then
  echo "Opzione sconosciuta: $MODO" >&2
  exit 2
fi

cd "$(git rev-parse --show-toplevel)"

if [ -n "$(git status --porcelain)" ]; then
  echo "ATTENZIONE: ci sono modifiche non committate: non verranno caricate." >&2
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# Esportazione dei soli file committati.
git archive HEAD | tar -x -C "$TMP"

# Lo Space legge la propria configurazione dal README.md nella radice: si
# sostituisce quello del repo (senza intestazione) con quello dello Space.
cp deploy/README_SPACE.md "$TMP/README.md"

# Controllo di sicurezza: nessuno di questi file deve uscire dal repo.
VIETATI=$(find "$TMP" \( -name ".env*" ! -name ".env.example" -o -name venv -o -name node_modules -o -name chroma_data -o -name .git \) | head -n 5)
if [ -n "$VIETATI" ]; then
  echo "ERRORE: l'esportazione contiene file che non devono essere caricati:" >&2
  echo "$VIETATI" >&2
  exit 1
fi

NUMERO=$(find "$TMP" -type f | wc -l | tr -d ' ')

if [ "$MODO" = "--prova" ]; then
  echo "Prova a secco: verso $SPACE verrebbero caricati $NUMERO file (commit $(git rev-parse --short HEAD)):"
  (cd "$TMP" && find . -type f | sort)
  exit 0
fi

if ! command -v hf >/dev/null 2>&1; then
  echo "ERRORE: lo strumento 'hf' non è installato (pip install -U huggingface_hub)." >&2
  exit 1
fi

hf upload "$SPACE" "$TMP" . --repo-type=space --commit-message "Aggiornamento dal commit $(git rev-parse --short HEAD)"