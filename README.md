# ScoutEdge Analytics — assistente AI ibrido

[![Test](https://github.com/FranCodesc/scoutedge-analytics/actions/workflows/test.yml/badge.svg)](https://github.com/FranCodesc/scoutedge-analytics/actions/workflows/test.yml)

Assistente conversazionale per il reparto Data Science & Client Success di **ScoutEdge Analytics**, un'azienda immaginaria che vende software di scouting e performance analytics ai club di calcio. L'utente scrive una domanda in italiano e un agente AI decide da solo come rispondere: cercando nel manuale interno dell'azienda oppure facendo analizzare il dataset delle osservazioni di scouting da un servizio Python, con tanto di grafici. È il progetto finale del master universitario "AI e Agenti AI per il Business" (Start2Impact / UniMarconi).

**Demo online:** <https://francodesc-scoutedge-analytics.hf.space>. Va in pausa dopo 48 ore senza visite: se è ferma, la prima apertura richiede circa 30 secondi. Come è costruita e come si pubblica: [`docs/DEPLOY.md`](docs/DEPLOY.md).

## Architettura

- **Front end** React (`front end/`) → **back end** Node.js con Express e LangChain.js (`back end/`), l'unico servizio con cui parla il browser.
- Il back end gestisce la conversazione e, per ogni domanda, l'LLM (`gpt-4o-mini`) sceglie lo strumento con il *function calling*: `search_handbook` cerca nel manuale indicizzato in **ChromaDB** (RAG), `analyze_data` delega l'analisi del CSV al **data agent** Python (`data_agent/`, FastAPI e pandas), che scrive ed esegue il codice e genera i grafici.
- In locale sono quattro processi (porte 5173, 3001, 8000 e 8001); online girano in un solo container, dietro nginx.

Schema, dati e struttura del repository: [`docs/PROGETTO.md`](docs/PROGETTO.md). Come l'LLM sceglie lo strumento: [`docs/DESIGN_ORCHESTRATORE.md`](docs/DESIGN_ORCHESTRATORE.md).

## Avvio rapido

Comandi per macOS e Linux, dalla radice del repository. Servono Node.js 22.13 o successivo (per il solo avvio bastano 20.19 o 22.12, ma i test del front end chiedono 22.13), Python 3.13, Docker e una chiave OpenAI. Prerequisiti, dettagli di ogni passo, tabella dei file `.env` e comandi per Windows: [`docs/INSTALLAZIONE.md`](docs/INSTALLAZIONE.md).

```bash
git clone https://github.com/FranCodesc/scoutedge-analytics.git
cd scoutedge-analytics
cd "back end"
npm install
cp .env.example .env
cd ..
cd "front end"
npm install
cp .env.example .env
cd ..
cd data_agent
python3.13 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
deactivate
cd ..
# Inserisci la chiave OpenAI in OPENAI_API_KEY di back end/.env e di data_agent/.env, poi, con Docker avviato:
cd "back end"
docker run -d --name chroma-scoutedge -p 127.0.0.1:8001:8000 -v "$(pwd)/chroma_data:/data" chromadb/chroma@sha256:1e0b73a187a28757c572acba508c46f48c9e8b0acaf5c20e6d95cdedce1acdf6
npm run ingest
cd ..
# Primo terminale: data agent (aspetta "Data agent pronto")
cd data_agent
source venv/bin/activate
uvicorn main:app --reload
# Secondo terminale: back end (aspetta "Back end in ascolto su http://localhost:3001")
cd "back end"
npm run dev
# Terzo terminale: front end, poi apri http://localhost:5173
cd "front end"
npm run dev
```

## Test

```bash
(cd data_agent && source venv/bin/activate && pip install -r requirements-dev.txt && python -m pytest)
(cd "back end" && npm test)
(cd "front end" && npm test)
```

Si lanciano dalla radice del repository, dopo l'installazione: sono 437 test automatici (136 del data agent, 225 del back end, 76 del front end), senza chiamate al modello né chiave OpenAI, eseguiti anche dall'integrazione continua a ogni push e pull request. Valutazione con il modello reale, benchmark e verifiche manuali: [`docs/TEST.md`](docs/TEST.md).

## Documentazione

- [`docs/PROGETTO.md`](docs/PROGETTO.md): scenario, funzionalità, dati e knowledge base, stack, architettura con lo schema e struttura del repository.
- [`docs/INSTALLAZIONE.md`](docs/INSTALLAZIONE.md): prerequisiti, installazione, file `.env`, Chroma e indicizzazione, avvio e comandi per Windows.
- [`docs/DEPLOY.md`](docs/DEPLOY.md): demo online, container, avvio con Docker in locale, pubblicazione su Hugging Face e `TRUST_PROXY`.
- [`docs/SICUREZZA.md`](docs/SICUREZZA.md): sicurezza, protezioni della demo online e limiti noti.
- [`docs/PROBLEMI.md`](docs/PROBLEMI.md): risoluzione dei problemi più comuni.
- [`docs/TEST.md`](docs/TEST.md): test automatici, valutazione con il modello reale, benchmark, verifiche manuali e valori attesi.
- [`docs/CONTRATTO_API.md`](docs/CONTRATTO_API.md): contratto tra front end e back end (richieste, risposte, errori, limiti).
- [`docs/DESIGN_ORCHESTRATORE.md`](docs/DESIGN_ORCHESTRATORE.md): ciclo ReAct, strumenti e system prompt dell'orchestratore.
- [`docs/decisions/`](docs/decisions/README.md): storia e motivazioni delle scelte principali, con le alternative scartate.
- [`docs/CHANGELOG_HANDBOOK.md`](docs/CHANGELOG_HANDBOOK.md): storico delle versioni del manuale.
- [`docs/ScoutEdge_Analytics_presentazione.pdf`](docs/ScoutEdge_Analytics_presentazione.pdf): presentazione di 16 slide (scenario, architettura, esempi, sfide, test e limiti).
