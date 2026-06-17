# CLAUDE.md — SysMon Agent Project Guide

## Build & Run

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
python app.py
# → http://127.0.0.1:8080

# Docker
docker build -t sysmon-agent:latest .
docker run -d -p 8080:8080 --name sysmon-agent sysmon-agent:latest
```

## Project Structure

```
sysmon-agent/
├── app.py                    # FastAPI backend (REST + WebSocket)
├── requirements.txt
├── Dockerfile
├── .env.example
├── .gitignore
├── CLAUDE.md                 # This file
├── README.md                 # Submission README
├── frontend/
│   ├── index.html            # SPA — single page with tab navigation
│   ├── style.css             # Glassmorphism dark/light theme
│   └── app.js                # Client logic, WebSocket, fetch APIs
├── data/                     # Persistent JSON storage (gitignored)
│   ├── config.json
│   ├── logs.json
│   ├── sops.json
│   └── metrics.json
└── temp_uploads/             # Temp dir for SOP file parsing
```

## Code Guidelines

- **Backend:** FastAPI in `app.py`. JSON file-based storage (no DB dependency).
- **Frontend:** Vanilla HTML/CSS/JS — no framework. Glassmorphism design with CSS variables for theming.
- **Security:** API keys masked in responses. Never commit `data/config.json`. Use `MAAS_API_KEY` env var or Settings UI.
- **WebSocket:** Real-time log/alert updates via `/ws` endpoint. Broadcasts on log CRUD.
- **RAG:** TF-IDF weighted SOP matching for chatbot context injection.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/dashboard | Aggregated system stats |
| GET/POST/PUT/DELETE | /api/logs | Log CRUD |
| GET/POST/DELETE | /api/sops | SOP management |
| POST | /api/sops/upload | Upload SOP document |
| GET/POST | /api/config | System configuration |
| GET | /api/nagios-alerts | Fetch Nagios alerts (IMAP or mock) |
| GET | /api/escalations | Detect alert escalations |
| GET | /api/handover | Generate handover report |
| POST | /api/chat | AI chatbot |
| WS | /ws | Real-time updates |

## Agent Behavior

1. **Language:** Respond in Vietnamese (professional, concise). Switch to English if user writes in English.
2. **SOP Lookup:** When asked about incident handling, search uploaded SOPs first. If no match, suggest uploading docs.
3. **Incident Email:** Auto-extract from logs: component, severity, time, impact.
4. **Alert Analysis:** When asked about spikes, analyze Nagios timeline for escalating patterns.
5. **Escalation Detection:** Hosts with ≥N alerts (configurable) within time window = escalation risk.
