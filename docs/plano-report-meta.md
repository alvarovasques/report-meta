# Report Meta: plano para o gerador próprio de relatórios de performance (Instagram, Facebook e Meta Ads)

Versão 1.2, 10/09/2026 (fase 0: inventário e permissões concluídos). Escopo definido com o Alvaro: construir ferramenta própria, primeira versão só para a Internet Mais, entregando dashboard web ao vivo e PDF mensal com resumo no WhatsApp.

Sucesso significa: no dia 1º de cada mês, a gestão da Internet Mais recebe no WhatsApp um PDF com o desempenho orgânico e pago do mês anterior, comparado ao mês anterior a ele, com análise em texto; e o time de marketing consulta a qualquer momento um dashboard com os mesmos números filtrados por período, sem ninguém abrir o Gerenciador de Anúncios ou o Instagram para montar planilha.

## 1. O que o Reportei entrega (referência de escopo)

O Reportei é um SaaS brasileiro de relatórios para agências. Ele não tem dado próprio: lê as APIs públicas da Meta e o valor dele está na apresentação, nos templates, no histórico acumulado e na distribuição. O que vale copiar do relatório Meta deles:

| Bloco | Conteúdo no Reportei |
|---|---|
| Instagram: perfil | Seguidores e variação, alcance e visualizações (orgânico + pago), visitas ao perfil, cliques no perfil; gráficos de crescimento; demografia por idade, gênero e cidade; melhor dia e melhor horário para postar |
| Instagram: feed | Alcance, visualizações, engajamento (curtidas, comentários, salvamentos, compartilhamentos), quantidade de posts; tabela de top posts com tipo, alcance, engajamento e data |
| Instagram: reels | Alcance, reproduções, interações, quantidade; tabela de reels em destaque |
| Instagram: stories | Alcance, visualizações, taxa de retenção, quantidade; por story: avanços, voltas, saídas, respostas |
| Facebook: página | Curtidas e novas curtidas, seguidores, alcance, visualizações de página, engajamento em posts (reações, comentários, compartilhamentos), demografia, posts em destaque |
| Meta Ads | Investimento, alcance, impressões, cliques, CPC, CPM, CTR, frequência, quantidade de anúncios; separação Facebook × Instagram; por campanha; por dispositivo, idade, gênero e horário; ações (cliques no link, reações, mensagens, leads) e custo por ação; mais de 180 métricas de conversão/custo adicionáveis |
| Recursos | Templates reutilizáveis, métricas manuais, blocos de texto/imagem/vídeo para análise, comparação com período anterior, envio por link, PDF e WhatsApp, automação de envio, dashboards, "Reportei AI" (análise gerada), "Marketing Timeline" (registro de ações do time sobre o gráfico) |

Duas coisas o Reportei não faz e que são a nossa vantagem: ele não sabe quantos leads viraram contrato (isso está no IXC e no OPA Suite) e não sabe o custo real de aquisição por plano ou por bairro. O relatório próprio deve fechar esse funil desde o desenho, mesmo que só na fase 4.

## 2. Princípio que governa o projeto

Relatório de performance é um pipeline com cinco etapas: coletar, armazenar, calcular, apresentar, distribuir. Quase todo erro de projeto desse tipo vem de pular a etapa "armazenar" e ir direto da API para a tela. Com a Meta isso é fatal por três motivos: stories só existem na API por 24 horas, contagem de seguidores e dados de stories só existem a partir da data em que você integra (o Reportei avisa exatamente isso na central de ajuda), e a Meta descontinua métricas com frequência (impressões viraram "visualizações" em 2025; várias métricas de página foram removidas em junho de 2026). Se guardamos snapshots diários no nosso banco, o histórico é nosso e uma deprecação vira só uma troca de campo no coletor. Portanto: coletor diário com persistência é o coração do sistema, e dashboard e PDF são leitores do banco, nunca da API.

## 3. Fontes de dados, permissões e acessos

| Fonte | Endpoint | Permissões | Observações |
|---|---|---|---|
| Instagram orgânico | Instagram Graph API: `/{ig-user-id}/insights`, `/{ig-user-id}/media`, `/{ig-media-id}/insights`, `/{ig-user-id}/stories` | `instagram_basic`, `instagram_manage_insights`, `pages_show_list`, `pages_read_engagement` | Conta profissional vinculada à Página. Limite de 200 chamadas/hora por conta IG. Demografia exige 100+ seguidores. Métricas de conta: reach, views, engaged_accounts, likes, comments, saves, shares, follower_changes (com breakdown follow_type desde jan/2026), profile_visits; demografia de seguidores e de alcance por cidade, país, idade e gênero. Métricas de mídia: views, reach, likes, comments, saves, shares, total_interactions; reels ainda têm métricas próprias de reprodução e, desde abr/2026, skip rate; stories têm navigation (avanço, volta, saída), replies, retenção. |
| Facebook Página | Graph API `/{page-id}/insights`, `/{page-id}/posts` | `read_insights`, `pages_read_engagement`, `pages_show_list` | Janela máxima de 90 dias por chamada e 2 anos de histórico. Desde 15/06/2026 a Meta removeu alcance e impressões orgânicas de página/post; o que sobrou de confiável é `page_views_total`, visualizações orgânicas, `page_post_engagements`, `page_fans`, `page_daily_follows`, vídeo. Confirmar a lista final no anúncio de fev/2026 da Meta antes de codar. |
| Meta Ads | Marketing API `/act_{id}/insights` com `level=campaign|adset|ad`, `time_increment=1`, breakdowns `age`, `gender`, `publisher_platform`, `device_platform`, `hourly_stats_aggregated_by_advertiser_time_zone` | `ads_read` | Campos: spend, impressions, reach, frequency, clicks, inline_link_clicks, cpc, cpm, ctr, actions e cost_per_action_type (leads, mensagens iniciadas, cliques no link), video metrics. Histórico com breakdown limitado a cerca de 13 meses; usar `async=true` para consultas grandes. Desde jun/2025 a atribuição padrão da API bate com o Gerenciador; fixar `action_attribution_windows` explicitamente para o número não mudar. |
| Funil interno (fase 4) | OPA Suite (conversas originadas de anúncio) e IXC (contratos) | APIs já mapeadas nas skills api-opa-suite e api-ixc | Fecha lead → atendimento → venda. |

Acesso (inventário feito em 10/09/2026 no portfólio "Grupo Easynet", business_id 187051108801754): o app "Di4E Provider" (id 1550725673131400) está ativo/publicado, mas tem um único caso de uso, WhatsApp; é o app do EasySuite e não deve ser mexido. O app "Gestor de Tráfego" (id 2896813507325298, modo desenvolvimento) já tinha Marketing API com `ads_read`, `ads_management`, `business_management`, `pages_read_engagement` e `pages_show_list` em "Pronto para teste" (acesso padrão, sem App Review) e Marketing API Access Tier em "Acesso limitado" (tier de desenvolvimento, suficiente para contas próprias). Nele foram adicionados os casos de uso "Gerenciar mensagens e conteúdo no Instagram" e "Gerenciar tudo na sua Página", e as permissões `instagram_basic`, `instagram_manage_insights`, `read_insights` e `pages_read_user_content`, todas em "Pronto para teste". Decisão: o Report Meta vive no Gestor de Tráfego. Os insights do Instagram devem ser lidos pelo caminho "API com login do Facebook" (conta IG vinculada à Página), não pelo login nativo do Instagram, que não expõe insights. Pendências humanas: reautenticação no Business Manager para criar/conferir o System User, atribuir a ele os ativos (Página, conta IG, conta de anúncios) e gerar o token permanente com as permissões acima; o token vai direto para o `.env` do coletor e nunca para o chat. Para a versão multi-cliente da Di4e será obrigatório Business Verification, App Review das permissões acima e Advanced Access no Marketing API, o que costuma levar semanas e deve ser iniciado cedo.

## 4. Métricas do MVP

Regra de corte: entra no MVP o que responde "estamos crescendo, o que funcionou, quanto custou". O resto fica para o modo "adicionar métrica".

Instagram: seguidores no fim do período e variação líquida (ganhos e perdas), alcance total, visualizações totais, visitas ao perfil, interações totais e taxa de engajamento sobre alcance, quantidade de posts por formato, top 5 posts e top 5 reels por alcance, stories publicados com retenção média, demografia (idade, gênero, 5 cidades principais) e melhor dia/horário calculados a partir da nossa base de posts, não da API.

Facebook: seguidores e variação, visualizações da página, engajamento em posts, posts publicados, top 3 posts.

Meta Ads: investimento, alcance, impressões, frequência, cliques no link, CTR, CPC, CPM, resultados por objetivo (leads, conversas iniciadas, cliques), custo por resultado, tabela por campanha (com status ativo/pausado), divisão Facebook × Instagram, divisão por dispositivo, distribuição por idade e gênero.

Visão consolidada (o que a gestão realmente lê): uma página com alcance orgânico × pago, investimento, custo por lead, seguidores ganhos, três destaques e três alertas em texto.

Tudo comparado ao período anterior equivalente, com variação percentual e seta.

## 5. Arquitetura proposta

Sugestão de stack coerente com o que o grupo já roda (VPS com Docker Swarm, Python, Postgres):

Coletor: serviço Python (FastAPI + APScheduler ou um cron do Swarm) que roda uma vez por dia às 03h e busca, para o dia anterior: insights de conta IG e Página, lista de mídias novas e re-coleta de insights de todas as mídias dos últimos 30 dias (métricas de post crescem por dias), stories ativos (obrigatório diário, senão perdem-se), e insights de Ads com `time_increment=1` nos níveis campanha, conjunto e anúncio, mais os breakdowns do MVP. Backfill inicial: 13 meses de Ads, 2 anos de Página (em blocos de 90 dias) e todas as mídias do IG com métricas lifetime. Implementar backoff exponencial, respeito ao limite de 200/h e log de cada chamada.

Banco: Postgres com tabelas de fatos por grão (dia × conta, dia × mídia, dia × campanha × breakdown) e tabelas de dimensão (conta, mídia, campanha, conjunto, anúncio). Nunca sobrescrever: cada coleta grava um snapshot com `collected_at`. Views materializadas para os agregados de período.

API: FastAPI expondo `/report?account=&from=&to=&compare=previous_period` que devolve o JSON completo de um relatório. Dashboard e PDF consomem o mesmo JSON, o que garante que os dois nunca discordam.

Dashboard: aplicação web simples (Next.js ou HTML + Chart.js servido pelo próprio FastAPI, para não abrir um segundo projeto), com filtro de período, comparação e as seções do item 4. Login simples por senha ou pelo SSO que já exista no grupo.

PDF: renderizar a própria página do dashboard em modo "impressão" com Playwright (Chromium headless). Uma única camada de layout para manter.

Análise em texto: um passo com LLM que recebe o JSON do relatório e devolve destaques, alertas e recomendações em português, com regras (comparar sempre com o período anterior, citar número e variação, apontar campanha com pior custo por resultado). Guardar o texto no banco para revisão humana antes do envio.

Distribuição: no dia 1º, job gera o PDF, salva no storage, publica o link do dashboard filtrado no mês e envia pelo OPA Suite (WhatsApp) para a lista da gestão com o resumo de cinco linhas e o PDF anexo. O relatório também fica arquivado na pasta do projeto.

## 6. Fases e entregas

| Fase | Duração estimada | Entrega | Critério de pronto |
|---|---|---|---|
| 0. Acessos | 1 a 2 dias (inventário e permissões concluídos em 10/09) | Restam: System User com token permanente no Gestor de Tráfego, IDs da conta IG, Página e conta de anúncios, chamadas de teste devolvendo dados | `curl` nas três APIs retorna insights do dia anterior |
| 1. Coletor + banco | 2 semanas | Coletor diário em produção no Swarm, backfill concluído, tabelas populadas | 7 dias seguidos de coleta sem falha; conferência manual de 10 números contra Gerenciador e Insights do app |
| 2. API + dashboard | 2 semanas | Endpoint `/report` e dashboard com as seções do MVP, comparação de período | Time de marketing usa por 1 semana e valida os números |
| 3. PDF + WhatsApp + análise IA | 2 semanas | Geração automática no dia 1º, envio pelo OPA Suite, texto de análise revisável | Primeiro relatório mensal entregue sem intervenção manual |
| 4. Funil fechado | 2 a 3 semanas | Leads de anúncio cruzados com OPA e contratos do IXC; custo por contrato por campanha e por bairro; metas mensais no dashboard | Relatório mostra CAC real por campanha |
| 5. Multi-cliente (Di4e) | a planejar | Multi-tenant, onboarding por OAuth, Business Verification e App Review, templates, white label | Um provedor externo conecta as contas sozinho |

Total para chegar ao relatório mensal automático (fases 0 a 3): cerca de 7 semanas com uma pessoa dedicada, ou 4 a 5 semanas se coletor e dashboard forem paralelizados entre duas pessoas. Checkpoint recomendado no fim de cada fase para ajustar direção sem perder progresso.

## 7. Riscos e mitigação

Deprecações da Meta são o risco principal e recorrente. Mitigação: coletar sempre pelo nome da métrica em uma tabela de configuração (não hardcoded), guardar o snapshot bruto em JSON ao lado das colunas tipadas e assinar o changelog da Graph API. Quando uma métrica some, o histórico continua no banco.

Histórico inexistente para stories e seguidores antes da integração. Mitigação: começar a coleta na fase 0, antes mesmo do dashboard existir; cada dia perdido não volta.

Números "diferentes" do que aparece no app do Instagram ou no Gerenciador. Isso é esperado (janelas de atribuição, fuso horário, métricas lifetime × período). Mitigação: fixar fuso America/Campo_Grande, fixar janela de atribuição, documentar no rodapé do relatório o que cada número significa. Sem isso o time perde confiança no relatório na primeira divergência.

Limite de 200 chamadas/hora na conta IG. Mitigação: coleta noturna, re-coleta de mídias só dos últimos 30 dias, cache de IDs.

Análise gerada por IA com afirmação errada. Mitigação: o texto só cita números vindos do JSON, passa por revisão humana no primeiro trimestre e a régua de envio tem um botão "aprovar".

## 8. Construir ou assinar

Posição: construir, como decidido, por três razões: o dado que diferencia o relatório (lead que virou contrato, CAC por plano) não existe no Reportei; o custo mensal de um SaaS de agência é recorrente e cresce por projeto, enquanto o coletor é um custo único; e a mesma base vira produto da Di4e para outros provedores. O alerta de segunda ordem: até a fase 3 terminar (cerca de 7 semanas), a gestão não recebe relatório. Se isso for um problema, a mitigação barata é assinar um mês do Reportei e usar o relatório dele como gabarito de validação dos nossos números na fase 1, cancelando em seguida. Não vi o preço público do Reportei (a página de planos não exibe a tabela); vale confirmar antes de decidir por essa ponte.

## 9. Próximos passos imediatos (o que depende do Alvaro)

Concluir a reautenticação no Business Manager e gerar o token de System User para o Gestor de Tráfego (com ads_read, read_insights, pages_read_engagement, pages_show_list, pages_read_user_content, instagram_basic, instagram_manage_insights, business_management), guardando-o no `.env` do coletor; enviar os IDs da conta do Instagram, da Página e da conta de anúncios; definir a lista de destinatários do WhatsApp e o dia/hora do envio; escolher se o dashboard usa Next.js ou fica dentro do FastAPI. Com isso em mãos, a fase 0 fecha em poucos dias e a coleta começa a acumular histórico.

## Fontes consultadas

Reportei: relatório de Instagram e Meta Ads (reportei.com/relatorio-de-instagram-e-meta-ads), relatório de Instagram (reportei.com/relatorio-de-instagram), relatórios de Facebook e Meta Ads (reportei.com/en/facebook-reports), métricas de Meta Ads (reportei.com/meta-ads), central de ajuda sobre métricas do Instagram e sobre a mudança de alcance/impressões do Facebook em 2026. Meta for Developers: referência de insights de usuário do Instagram e de Page Insights. Supermetrics: histórico de mudanças da Instagram Insights API. AdManage.ai: guia de configuração da Marketing API (System User, rate limits, atribuição).
