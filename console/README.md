# console/ — Consola web ARGOS (Fase 6)

Consola **read-only** que refleja el HITL en vivo, reconstruyendo el diseño de `ARGOS Console.html`
(dark `#0a0e16` + IBM Plex + amber `#f0a338`). FastAPI sirve la API + el SPA vanilla; el front hace
polling. Las aprobaciones siguen por **Telegram / trigger local** (`scripts/live_approve.py`). La
Streamlit (`ui/`) queda como **fallback** (no se toca; sus tests siguen verdes).

## Correr
```bash
docker run --rm -p 6379:6379 redis:7
python scripts/demo_injector.py uc04 --redis-url redis://localhost:6379/0
REDIS_URL=redis://localhost:6379/0 uvicorn console.api.main:app --port 8080
# abrir http://localhost:8080
```

## API
- `GET /api/incidents` — lista de `Incident` (abiertos primero; **filtra `incident:counter:*`**).
- `GET /api/incidents/{id}` — uno, o 404.
- `GET /health` — `{ok, redis}`.

## Notas
- Fuentes vía Google Fonts CDN (IBM Plex, el mismo del bundle). Para **air-gap**: self-hostear los woff2
  (están embebidos en `ARGOS Console.html`) y cambiar el `<link>` de `static/index.html`.
- La vista SOC-wide / OpenSearch del mockup queda **fuera** (necesita el indexer = Perfil B, F7).
- La compose de Fase 5 empaqueta este servicio (por eso se construyó 6 antes que 5).
