# syntax=docker/dockerfile:1

# =============================================================================
# Fase 1 - Node: build del front end e dipendenze di produzione del back end.
# La variante "trixie" ha la stessa release Debian dell'immagine finale, così il
# binario di node copiato più avanti trova la glibc che si aspetta.
# =============================================================================
FROM node:24-trixie-slim AS node-build
WORKDIR /build

# URL pubblico con cui il browser raggiunge il back end (tramite nginx).
# Vite lo incorpora nel codice al momento della build; non è un segreto.
# Nessun valore predefinito: un URL dimenticato farebbe puntare la demo
# online a un indirizzo sbagliato, quindi senza argomento la build si ferma.
ARG VITE_API_URL
RUN test -n "$VITE_API_URL" || { echo "Manca --build-arg VITE_API_URL" >&2; exit 1; }
ENV VITE_API_URL=${VITE_API_URL}

# Prima i soli file delle dipendenze: finché non cambiano, Docker riusa la cache.
COPY ["front end/package.json", "front end/package-lock.json", "front end/"]
RUN cd "front end" && npm ci
COPY ["front end/", "front end/"]
RUN cd "front end" && npm run build

# Il back end gira solo con le dipendenze di produzione.
COPY ["back end/package.json", "back end/package-lock.json", "back end/"]
RUN cd "back end" && npm ci --omit=dev

# =============================================================================
# Fase 2 - Chroma: la stessa immagine fissata con il digest usata in locale
# (versione 1.4.4, indice multi-architettura amd64 + arm64). Serve solo per
# copiarne il programma "chroma", un eseguibile unico in /usr/local/bin.
# =============================================================================
FROM chromadb/chroma@sha256:1e0b73a187a28757c572acba508c46f48c9e8b0acaf5c20e6d95cdedce1acdf6 AS chroma

# =============================================================================
# Fase 3 - Immagine finale: Python 3.13 (data agent) con nginx, node e chroma.
# Stessa release Debian (trixie) delle fasi precedenti, perché node e chroma
# sono binari già compilati che usano la libreria C di sistema.
# =============================================================================
FROM python:3.13-slim-trixie

# nginx: unico punto esposto. curl: serve allo script di avvio per attendere
# che i servizi rispondano. libstdc++6: richiesta dal programma chroma.
RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx curl libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=node-build /usr/local/bin/node /usr/local/bin/node
COPY --from=chroma /usr/local/bin/chroma /usr/local/bin/chroma

# Utente non root con UID 1000, come richiesto da Hugging Face Spaces.
RUN useradd --create-home --uid 1000 user

WORKDIR /app

# Il log dei processi Python va subito su stdout, senza buffer.
ENV PYTHONUNBUFFERED=1

# Dipendenze del data agent. Si copia prima solo requirements.txt: se il codice
# cambia ma le dipendenze no, Docker riusa questo livello (il più lento da rifare).
COPY data_agent/requirements.txt data_agent/
RUN pip install --no-cache-dir -r data_agent/requirements.txt

# Codice e dati. Le cartelle mantengono i nomi del repo, perché i percorsi
# relativi del codice (es. ../data/scouting_data.csv) ne dipendono.
COPY ["back end/", "back end/"]
COPY --from=node-build ["/build/back end/node_modules", "back end/node_modules"]
COPY data_agent/ data_agent/
COPY data/ data/

# Build del front end, servita da nginx.
COPY --from=node-build ["/build/front end/dist", "www"]

# Il codice resta di proprietà di root e l'utente non root non può modificarlo.
# Può scrivere solo nella cartella dei grafici (la cartella dei dati di Chroma
# la crea lo script di avvio in /tmp).
RUN mkdir -p data_agent/charts && chown user:user data_agent/charts

# Indirizzi interni fissi: tutti i servizi stanno nello stesso container.
# OPENAI_API_KEY, FRONTEND_ORIGIN, RATE_LIMIT_* e TRUST_PROXY NON si scrivono qui:
# si passano all'avvio del container.
ENV CHROMA_URL=http://127.0.0.1:8001 \
    DATA_AGENT_URL=http://127.0.0.1:8000 \
    PORT=3001

USER user
EXPOSE 7860

# Configurazione di nginx e script di avvio. Si copiano solo questi due file
# della cartella deploy/ (gli altri servono fuori dal container).
COPY deploy/nginx.conf deploy/start.sh deploy/

# Lo script si lancia con bash: non serve il permesso di esecuzione sul file.
CMD ["bash", "deploy/start.sh"]