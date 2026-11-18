#!/usr/bin/env bash
# Lancia il benchmark del data agent su un Job di Hugging Face con la stessa macchina
# della demo: flavor cpu-basic (2 CPU, 16 GB) e la stessa immagine di base del
# Dockerfile (python:3.13-slim-trixie).
#
# Uso:
#   deploy/benchmark_job.sh --prova      corsa breve (1x, 2 ripetizioni): controlla il Job
#   deploy/benchmark_job.sh              corsa completa (1, 10, 30, 60, 100, 1000x, 5 ripetizioni)
#   aggiungere --dry-run                 stampa la configurazione del Job senza lanciarlo
#
# Il Job scarica da GitHub il codice del commit corrente (HEAD, che deve essere già
# pubblicato), installa data_agent/requirements-dev.txt, esegue benchmark.py e
# benchmark_riepilogo.py e copia JSON e Markdown della corsa nel bucket della demo
# (cartella benchmark/, o benchmark-prova/ per la corsa breve). Da lì si scaricano con
# "hf buckets cp" in data_agent/scripts/risultati_benchmark/.
#
# Serve lo strumento "hf" con l'accesso già effettuato, con un token che possa avviare
# Jobs e scrivere nel bucket: il token non passa da questo script.

set -euo pipefail
export GIT_OPTIONAL_LOCKS=0

REPO=https://github.com/FranCodesc/scoutedge-analytics
BUCKET=FranCodesc/scoutedge-analytics-storage
IMMAGINE=python:3.13-slim-trixie

DIMENSIONI="1 10 30 60 100 1000"
RIPETIZIONI=5
TIMEOUT=3h
NOME=benchmark-completo
CARTELLA=benchmark
SFONDO="--detach"
SECCO=""
for arg in "$@"; do
  case "$arg" in
    --prova) DIMENSIONI="1"; RIPETIZIONI=2; TIMEOUT=30m; NOME=benchmark-prova
             CARTELLA=benchmark-prova; SFONDO="" ;;
    --dry-run) SECCO="--dry-run" ;;
    *) echo "Opzione sconosciuta: $arg" >&2; exit 2 ;;
  esac
done

cd "$(git rev-parse --show-toplevel)"
COMMIT=$(git rev-parse HEAD)
if ! git branch -r --contains "$COMMIT" | grep -q .; then
  echo "ERRORE: il commit $COMMIT non è su GitHub: prima git push." >&2
  exit 1
fi
if [ -n "$(git status --porcelain)" ]; then
  echo "ATTENZIONE: ci sono modifiche non committate: il Job usa il commit $COMMIT, senza di esse." >&2
fi

# Comandi eseguiti dentro il Job.
CORSA=$(cat <<EOF
set -euo pipefail
echo "Commit $COMMIT, dimensioni $DIMENSIONI, ripetizioni $RIPETIZIONI"
python - <<'PY'
import io, tarfile, urllib.request
with urllib.request.urlopen("$REPO/archive/$COMMIT.tar.gz") as risposta:
    tarfile.open(fileobj=io.BytesIO(risposta.read()), mode="r:gz").extractall("/repo", filter="data")
PY
cd "/repo/scoutedge-analytics-$COMMIT/data_agent"
pip install --quiet --root-user-action=ignore -r requirements-dev.txt
python scripts/benchmark.py --dimensioni $DIMENSIONI --ripetizioni $RIPETIZIONI
python scripts/benchmark_riepilogo.py
mkdir -p "/data/$CARTELLA"
ULTIMA=\$(ls scripts/risultati_benchmark/corsa-*.json | sort | tail -n 1)
cp "\$ULTIMA" "\${ULTIMA%.json}.md" "/data/$CARTELLA/"
echo "Copiati nel bucket, cartella $CARTELLA/: \$(basename "\$ULTIMA") e il riepilogo .md"
EOF
)

echo "Job $NOME sul commit ${COMMIT:0:7}: cpu-basic, $IMMAGINE, timeout $TIMEOUT"
hf jobs run $SECCO $SFONDO --flavor cpu-basic --timeout "$TIMEOUT" --name "$NOME" \
  -v "hf://buckets/$BUCKET:/data" "$IMMAGINE" -- bash -c "$CORSA"
