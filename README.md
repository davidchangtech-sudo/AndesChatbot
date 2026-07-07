# Andes AI Chatbot

RAG chat widget for andestech.com. Backend runs in Docker; WordPress gets a plugin.

## handoff (send to IT)

```bash
./make-handoff.sh
```

Sends: zip + `GOOGLE_API_KEY` separately. IT opens `START.txt` inside the zip.

## local dev

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add GOOGLE_API_KEY
uvicorn app.main:app --reload --port 8000
```

Health: `curl http://localhost:8000/health`

## deploy target

On-prem Linux next to WordPress — not cloud, not a dev laptop for production.
