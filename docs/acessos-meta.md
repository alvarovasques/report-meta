# Report Meta — acessos e IDs (fase 0)

Inventário feito em 10/09/2026 no portfólio empresarial **Grupo Easynet** (business_id `187051108801754`).

## App usado

| Item | Valor |
|---|---|
| App | Gestor de Tráfego |
| App ID | `2896813507325298` |
| Modo | Em desenvolvimento (suficiente para ativos próprios; sem App Review) |
| Casos de uso | Marketing API (já existia), Instagram API e Páginas (adicionados em 10/09) |
| Permissões prontas para teste | `ads_read`, `ads_management`, `business_management`, `pages_read_engagement`, `pages_show_list`, `pages_read_user_content`, `read_insights`, `instagram_basic`, `instagram_manage_insights` |
| Marketing API Access Tier | Acesso limitado (tier de desenvolvimento) |

O app "Di4E Provider" (`1550725673131400`, ativo) é exclusivo do WhatsApp/EasySuite e não é usado pelo Report Meta.

## System User

| Item | Valor |
|---|---|
| Nome | Report Meta Collector |
| ID | `61594079289741` |
| Função | Funcionário |
| Ativos atribuídos | Página Internet Mais MS (Insights), conta de anúncios Internet Mais (Ver desempenho), conta IG @internetmaisms (Insights) |
| Token | **pendente**: gerar manualmente (o painel legado deu "Estamos tendo problemas para concluir sua solicitação" duas vezes; tentar de novo ou pelo novo painel de Configurações do portfólio). Guardar só no `.env`. |

## Ativos da Internet Mais

| Ativo | ID |
|---|---|
| Página Facebook "Internet Mais MS" | `103784460999999` |
| Conta Instagram @internetmaisms (IG User ID) | `17841418897462497` |
| Conta de anúncios "Internet Mais" | `act_362683751` |

## Chamadas de teste (depois do token no `.env`)

```bash
source .env
# Página
curl -s "https://graph.facebook.com/$META_GRAPH_VERSION/$META_PAGE_ID/insights?metric=page_post_engagements,page_views_total&period=day&date_preset=yesterday&access_token=$META_SYSTEM_USER_TOKEN"
# Instagram
curl -s "https://graph.facebook.com/$META_GRAPH_VERSION/$META_IG_USER_ID/insights?metric=reach,views,total_interactions&period=day&metric_type=total_value&since=$(date -d yesterday +%F)&until=$(date +%F)&access_token=$META_SYSTEM_USER_TOKEN"
# Ads
curl -s "https://graph.facebook.com/$META_GRAPH_VERSION/$META_AD_ACCOUNT_ID/insights?fields=spend,impressions,reach,clicks,ctr,cpc&date_preset=yesterday&access_token=$META_SYSTEM_USER_TOKEN"
```

Critério de pronto da fase 0: as três chamadas devolvem dados do dia anterior.
