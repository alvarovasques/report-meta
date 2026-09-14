# Deploy — VPS di4e (Docker Swarm + Traefik + Watchtower)

Fluxo: `git push` em `main` → GitHub Actions roda os testes e publica `ghcr.io/alvarovasques/report-meta:latest` → Watchtower na VPS puxa a imagem e atualiza `report-web` e `report-collector`.

## 1. Repositório e imagem (uma vez)

```powershell
cd C:\Users\alvar\DEV\report
# o workflow foi entregue em deploy\github-workflow-build.yml (a pasta .github é protegida contra escrita remota); mova-o:
New-Item -ItemType Directory -Force .github\workflows | Out-Null
Move-Item deploy\github-workflow-build.yml .github\workflows\build.yml
git init; git add .; git commit -m "Report Meta: coletor + dashboard"
gh repo create alvarovasques/report-meta --private --source . --push
```

O workflow `.github/workflows/build.yml` usa o `GITHUB_TOKEN` para publicar no GHCR; não precisa de secret extra. Depois do primeiro build, em GitHub > Packages > report-meta > Package settings, deixe a visibilidade como **private** e confirme que a VPS consegue puxar: na VPS, `docker login ghcr.io` com um PAT `read:packages` (o mesmo que o Watchtower já usa para as outras stacks, se for o caso).

## 2. Secret do token da Meta (uma vez, na VPS)

O token do System User **não** vai em variável de ambiente nem no Portainer; vai como Docker secret:

```bash
printf '%s' 'COLE_O_TOKEN_AQUI' | docker secret create meta_system_user_token -
```

O app lê `/run/secrets/meta_system_user_token` automaticamente (fallback quando `META_SYSTEM_USER_TOKEN` está vazio). Para rotacionar: `docker secret rm` só funciona com o stack removido, então crie `meta_system_user_token_v2`, troque o nome em `stack.yml` e redeploy.

## 3. Stack no Portainer

Stacks > Add stack > nome `report` > cole `stack.yml` (ou aponte para o repositório Git). Variáveis de ambiente da stack:

| Variável | Valor |
|---|---|
| `REPORT_DB_PASSWORD` | senha nova do Postgres do stack (obrigatória: sem ela o `postgres:16` sai com exit 1) |
| `REPORT_BASIC_USER` / `REPORT_BASIC_PASSWORD` | login do dashboard |
| `META_APP_ID` | `2896813507325298` |
| `META_BUSINESS_ID` | `187051108801754` |
| `META_PAGE_ID` | `103784460999999` |
| `META_IG_USER_ID` | `17841418897462497` |
| `META_AD_ACCOUNT_ID` | `act_362683751` |
| `META_APP_SECRET` | opcional (habilita `appsecret_proof`) |

Nomes confirmados na VPS di4e em 14/09/2026: rede pública do Traefik `di4e`, resolver `letsencryptresolver`, provider Swarm (labels em `deploy.labels`). Para outra VPS, confira:

```bash
docker network ls | grep traefik          # nome da rede pública (stack.yml assume di4e)
docker service inspect traefik_traefik --format '{{json .Spec.TaskTemplate.ContainerSpec.Args}}' | tr ',' '\n' | grep certresolver   # nome do resolver (stack.yml usa letsencryptresolver)
```

## 4. Primeira carga

```bash
docker exec -it $(docker ps -qf name=report_report-collector) report-meta check      # 3 APIs respondendo?
docker exec -it $(docker ps -qf name=report_report-collector) report-meta backfill   # ~13 meses de Ads, 2 anos de Página, mídias IG
```

O `report-collector` roda em modo `daemon`: migra o esquema ao subir, coleta às 03h (America/Campo_Grande) e não repete a coleta do dia se ela já tiver status `ok` em `meta.collect_run`.

## 5. Verificação

- `https://report.di4e.com.br/healthz` → `{"ok": true}` (sem auth)
- `https://report.di4e.com.br/` → dashboard (Basic Auth)
- `https://report.di4e.com.br/api/report?start=2026-09-01&end=2026-09-30` → JSON do relatório

## Notas

- O Watchtower da VPS já puxa ~32x/dia; os dois serviços do stack têm `com.centurylinklabs.watchtower.enable=true`, o Postgres tem `false`.
- `report-db` tem volume próprio (`report_pgdata`) e não usa o Postgres compartilhado do Swarm, para o histórico ficar isolado e o backup ser simples (`pg_dump` do container).
- Rollback: `docker service update --image ghcr.io/alvarovasques/report-meta:sha-<hash> report_report-web` (as tags `sha-*` ficam no GHCR).
