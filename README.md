# Report Meta

Gerador de relatórios de performance Meta (Instagram, Facebook e Meta Ads) da Internet Mais. Coletor diário com persistência em Postgres + API/dashboard em https://report.di4e.com.br. Deploy: `docs/deploy.md` (GitHub Actions → GHCR → Watchtower/Swarm). Plano completo em `docs/plano-report-meta.md`; acessos e IDs em `docs/acessos-meta.md`.

## Rodar local

```bash
cp .env.example .env            # preencher META_SYSTEM_USER_TOKEN
docker compose up -d db
pip install -e ".[dev]"
report-meta migrate             # cria o esquema meta.*
report-meta check               # fase 0: as três APIs respondem?
report-meta backfill            # 13 meses de Ads, 2 anos de Página, todas as mídias IG
report-meta collect             # coleta de ontem (rodar todo dia às 03h)
pytest                          # testes sem rede e sem banco
```

Dashboard local: `REPORT_BASIC_PASSWORD=x uvicorn web.app:app --reload` e abra http://localhost:8000.

## Estrutura

| Caminho | Função |
|---|---|
| `collector/graph.py` | Cliente Graph API: paginação, backoff em rate limit, `appsecret_proof` |
| `collector/instagram.py` | Conta (views, reach, interações, follows), demografia, mídias (feed/reels, lifetime, re-coleta 30 dias), stories (diário, obrigatório) |
| `collector/page.py` | Página (métricas pós-jun/2026, tolerante a deprecação) e posts |
| `collector/ads.py` | Objetos (campanha/conjunto/anúncio) e insights por dia × nível × breakdown (plataforma, dispositivo, idade/gênero, hora) |
| `collector/db.py` | Upserts idempotentes; todo fato guarda o JSON bruto em `raw` |
| `collector/sql/001_schema.sql` | Esquema `meta.*` (empacotado com o coletor; `migrate` aplica em ordem) |
| `collector/cli.py` | `migrate`, `check`, `collect`, `backfill`, `daemon` (modo serviço) |
| `web/app.py` | FastAPI: `/healthz`, `/api/report?start&end` (JSON), `/` dashboard (Basic Auth) |
| `web/report.py` | Agregações do relatório com comparação ao período anterior |
| `stack.yml` | Stack do Swarm (db + web + collector) com labels Traefik e Watchtower |

## Decisões

Snapshots diários, nunca sobrescrever histórico: stories somem em 24h, seguidores só existem a partir da integração e a Meta deprecia métricas com frequência. O dashboard e o PDF (fase 2 e 3) leem só do banco, nunca da API. Janela de atribuição fixa (`ADS_ATTRIBUTION_WINDOWS`) e re-coleta dos últimos 3 dias de Ads a cada rodada, porque a Meta ajusta conversões retroativamente.
