# FINDE — RELATÓRIO DE EXECUÇÃO

Evolução do projeto Órbitae → Finde, seguindo o prompt mestre.

**Data:** 3 de setembro de 2026
**Base:** `Orbitae__2_.zip` (94 arquivos, 64 testes)
**Resultado:** 74 arquivos Python, 42 templates HTML, 9 migrations, 217 testes

---

## AVISO QUE VALE PARA O RELATÓRIO INTEIRO

O ambiente onde este trabalho foi feito **não tem Django instalado e não tem
acesso à rede**. `pip install Django` falha com "No matching distribution
found".

Consequência direta, e ela é grande:

```
[VERIFICAR NO AMBIENTE]  python manage.py check          NÃO EXECUTADO
[VERIFICAR NO AMBIENTE]  python manage.py test           NÃO EXECUTADO
[VERIFICAR NO AMBIENTE]  python manage.py makemigrations --check   NÃO EXECUTADO
[VERIFICAR NO AMBIENTE]  python manage.py migrate        NÃO EXECUTADO
```

> **ATUALIZAÇÃO após a primeira execução real na máquina do usuário:**
> `manage.py check` passou sem nenhum problema e
> `makemigrations --check --dry-run` respondeu **"No changes detected"** — as
> migrations escritas à mão batem exatamente com os modelos. A suíte revelou
> dois bugs reais (perda de campos derivados em `update_fields` e comparação
> de data com precisão errada), ambos corrigidos, com 6 testes de regressão.
> Detalhes em FALHAS.md, seção "Primeira execução real".

**Nenhum teste foi executado. Nenhuma migration foi aplicada.** Onde este
relatório diz "implementado", significa que o arquivo foi escrito e passou por
verificação estática — não que foi visto funcionando.

O que foi possível verificar, e foi:

| Verificação | Ferramenta | Resultado |
|---|---|---|
| Sintaxe Python | `ast.parse` em 74 arquivos | limpo |
| Sintaxe JavaScript | `node --check` | limpo |
| Balanceamento CSS | contagem de chaves | 477/477 |
| Nomes de URL usados x declarados | script próprio | 48/52, sem órfão |
| Tags e filtros de template x biblioteca | script próprio | limpo |
| Templates referenciados x disco | script próprio | 52/52 existem |
| Imports internos x módulos existentes | script próprio | limpo |
| Views referenciadas em urls.py | script próprio | 56 definidas, todas existem |
| **Campos dos modelos x estado das migrations** | script próprio | **7 modelos coerentes** |
| Índices e constraints x AddIndex/AddConstraint | script próprio | coerentes |
| admin/forms x campos reais | script próprio | coerentes |
| Migrations importando código do app | script próprio | zero |
| Ocorrências de "Orbitae" | `grep -rniI` | **zero** |

---

## FASE 0 — SEGURANÇA E PRESERVAÇÃO

**STATUS:** concluída

**ALTERAÇÕES**
- Backup íntegro do projeto original preservado antes de qualquer alteração.
- `.gitignore` reescrito: bloqueia `.env`, `.env.*` (exceto `.env.example`),
  `*.pem`, `*.key`, banco local e artefatos gerados.
- `.env.example` reescrito com todas as chaves comentadas por seção.
- Comando `gerar_secret_key` criado, com o roteiro completo de rotação:
  trocar a chave, derrubar as sessões, limpar o histórico com `git-filter-repo`
  e rotacionar SMTP, banco e storage.

**ARQUIVOS**
`.gitignore`, `.env.example`, `eventos/management/commands/gerar_secret_key.py`

**TESTES:** nenhum aplicável (configuração e documentação).

**PROBLEMAS ENCONTRADOS**
- A `SECRET_KEY` antiga esteve versionada. Remover o `.env` do repositório
  **não resolve**: a chave continua no histórico. O roteiro de limpeza está no
  comando e no README, mas **precisa ser executado por você** — não dá para
  fazer isso a partir de uma cópia extraída do zip.

---

## FASE 1 — CORREÇÃO DOS BUGS

**STATUS:** concluída

### 1. Paginação — `??page=2`

`{% querystring %}` já devolve a string começando com `?`. O template escrevia
`href="?{% querystring page=2 %}"`, gerando `??page=2`: o servidor lia a chave
`"?page"` e o parâmetro `page` nunca chegava. **Toda a paginação do site
mostrava sempre a primeira página.**

Corrigido com as tags `querystring_pagina`, `querystring_sem` e `remover_valor`,
que montam o link inteiro preservando os filtros. Mudar de filtro volta para a
página 1 — cair numa página 7 que não existe mais no resultado novo era o
comportamento errado.

**Testes:** `test_navegacao.PaginacaoTests` (5).

### 2. Ordenação — o listener no formulário errado

A página tem **dois** formulários com `[data-filtros-form]`: o painel de filtros
e o seletor "Ordenar por". O JS usava `$` (querySelector), que devolve só o
primeiro. Mudar a ordenação não enviava nada.

`$` → `$$` em `iniciarFiltros`, com o listener aplicado aos dois. Campos de data
também disparam envio.

**Testes:** `test_navegacao.OrdenacaoTests` (5).

### 3. Destaques — dois eventos sumiam do site

A home buscava 3 destaques, o template renderizava só `destaques.0`, e a seção
"em breve" excluía os três. **Dois eventos marcados como destaque não apareciam
em lugar nenhum.**

O contexto agora traz `destaque_principal` e `destaques_secundarios`, com uma
faixa própria para os secundários.

**Testes:** `test_navegacao.DestaquesTests` (4).

### 4. Moderação — evento publicado editável sem revisão

Bastava publicar algo inocente, esperar a aprovação e trocar nome, data, local e
preço depois. `services/catalogo.py` define `CAMPOS_SENSIVEIS` e devolve o
evento para `PENDENTE` quando um deles muda, zerando `publicado_em` e avisando o
produtor por e-mail.

Corrigir uma descrição **não** tira o evento do ar — seria um remédio pior que a
doença.

**Testes:** `test_moderacao.ModeracaoDeEdicaoTests` (8).

### 5. Reservas — centavos, concorrência e limites

- `data-valor="{{ valor_inteira }}"` renderizava `80,50` em pt-BR;
  `parseFloat("80,50")` devolve `80`. Corrigido com `|unlocalize`.
- A lógica saiu da view para `services/reservas.py`, com `select_for_update` e
  `@transaction.atomic`.
- Limite por pessoa (`limite_por_usuario`) e capacidade do evento passaram a ser
  verificados dentro da transação.

**Testes:** `test_reservas` (20), incluindo um de concorrência real com threads.

### 6. Vazamento por `/evento/<id>/`

Redirecionava 301 mesmo para evento pendente ou rejeitado, entregando o slug —
ou seja, o nome — de conteúdo que ainda não deveria existir para o público.
Agora filtra por `status=PUBLICADO` e devolve 404.

**Testes:** `test_seguranca.VazamentoPorIdTests` (4).

### 7. Importação — fuso, status, idempotência

- `garantir_aware()`: com `USE_TZ=True`, datetime ingênuo era gravado como UTC.
  Um show anunciado para 21h aparecia às 18h. Pior: `localtime()` levanta
  `ValueError` em datetime ingênuo, e a página do evento quebrava.
- `salvar_importados(status=PENDENTE)` por padrão.
- `Categoria.UNIVERSITARIO` valia `"universitário"`, com acento. Como
  `slugify()` nunca produz acento, **nenhum evento importado jamais entrou
  nessa categoria.**

**Testes:** `test_ingestao` (33).

### 8. Extras encontrados durante a implementação

- `clean_data` exigia data futura também na edição: quem errou a data ficava
  com o formulário permanentemente inválido, sem conseguir corrigir nem a
  descrição.
- `registrar_visualizacao()` era um UPDATE em todo GET, sem deduplicação. O
  número inflava com Googlebot e F5, e o site escrevia no banco a cada leitura.
- `LoginForm.username` era `EmailField`: superusuário criado por
  `createsuperuser` não conseguia entrar pela página de login.
- `CadastroForm` tinha corrida entre `.exists()` e `.create()`: dois cadastros
  simultâneos davam erro 500 em vez de mensagem.
- Eventos sem categoria e sem região "combinavam" com todos os outros também
  vazios na seção de relacionados.

**PRÓXIMA FASE:** 2.

---

## FASE 2 — SEGURANÇA E PRODUÇÃO

**STATUS:** concluída

**ALTERAÇÕES**
- `eventos/ratelimit.py`: contador de janela fixa sobre o cache do Django,
  cobrindo login, cadastro, senha, reserva, busca, favoritar, colar link e
  exclusão de conta. **Zero dependências novas.**
- `eventos/middleware.py`: `ADMIN_URL` configurável, allowlist de IP e throttle
  de POST. Responde **404**, não 403 — negar a existência entrega menos
  informação do que negar a permissão.
- `setup/settings.py` → pacote `base/dev/test/prod` com despacho por
  `DJANGO_ENV`, mantendo `DJANGO_SETTINGS_MODULE=setup.settings` intacto.
- `manage.py` força `DJANGO_ENV=test` quando o comando é `test`.

**Por que não django-axes / django-ratelimit:** o projeto tem quatro
dependências e roda em qualquer lugar. Um contador de 80 linhas resolvia o
problema real. Quando precisar de bloqueio persistente de conta, aí `django-axes`
passa a valer.

**PROBLEMAS ENCONTRADOS**
- **Limitação honesta:** o rate limiting depende do cache. Com
  `CACHE_BACKEND=locmem` e vários workers, cada processo tem o próprio contador
  e o limite efetivo se multiplica pelo número de workers. Documentado no
  módulo, no `.env.example` e no README. Em produção use `db` ou `redis`.

**TESTES:** `test_seguranca` (19).

---

## FASE 3 — IDENTIDADE ÓRBITAE → FINDE

**STATUS:** concluída — **zero ocorrências**

```
$ grep -rniI "orbitae\|órbitae" --exclude-dir=.git .
(nenhuma saída)
```

**ALTERAÇÕES**
- `static/css/orbitae.css` → `finde.css`
- `static/js/orbitae.js` → `finde.js`
- `img/logo-orbitae.png` → `logo-finde.png`
- `img/simbolo-orbitae.png` → `simbolo-finde.png`
- `templatetags/orbitae.py` → `finde.py`
- 15 `{% load orbitae %}` removidos: a biblioteca virou `builtins` no
  `TEMPLATES`, o que também elimina o risco de um `{% load %}` esquecido
  derrubar uma página só na hora de renderizar.
- 404: "Essa página saiu de órbita" → "Não encontramos essa página".

**O que NÃO foi renomeado, e por quê:** o app Django continua `eventos`, o
pacote continua `setup`, as tabelas e as migrations históricas ficaram intactas.
Nenhum deles dependia do nome do produto.

---

## FASES 4, 5, 6 — LOCAL, GEOLOCALIZAÇÃO E PRODUTOR

**STATUS:** concluídas

**ALTERAÇÕES**
- `Local`: nome, slug, `nome_normalizado` (chave de deduplicação), endereço,
  referência, região, cidade, CEP, coordenadas, `coordenada_aproximada`,
  acessibilidade, estacionamento, metrô mais próximo.
- `Produtor`: user, nome, slug, bio, logo, e-mail, site, Instagram, WhatsApp,
  verificado.
- `IntegracaoSympla`: token cedido pelo produtor.
- `Evento` ganhou `local_ref` e `produtor` como FK, **mantendo** `local` e
  `organizador` como texto sincronizado. Foi a decisão que preservou os 64
  testes originais e todos os templates existentes.
- `services/geocoding.py`: Nominatim via urllib, 1 requisição por segundo,
  cache de 30 dias, bounding box do DF, teto por execução.

**Deduplicação:** `normalizar()` (NFKD sem acento, minúsculo, espaços
colapsados) é a mesma função usada pela busca — assim busca e deduplicação nunca
divergem. "Cine Brasília", "Cine Brasilia" e "  cine   brasília " colidem em uma
chave só. A migration `0008` remove ainda sufixos de RA: "Cine Brasília - Asa
Sul" é o mesmo cinema.

**Fallback de coordenada:** endereço que não resolve recebe o centro da região
administrativa, marcado como `coordenada_aproximada`. Melhor um ponto aproximado
no mapa do que um local invisível — e a interface avisa que é aproximado.

**PROBLEMAS ENCONTRADOS**
- **As coordenadas das 26 RAs e das 26 estações de metrô são aproximadas**
  (4 casas decimais, ~11 m, de fontes públicas). Suficiente para centralizar
  mapa e calcular proximidade de metrô; **conferir antes de produção.**

**TESTES:** `test_geo` (27).

---

## FASE 7 — BANCO DE DADOS

**STATUS:** concluída

**ALTERAÇÕES**
- `DB_ENGINE=postgres` no `.env` basta para trocar de banco.
- `Evento.busca_texto`: coluna normalizada mantida no `save()`, consultada pela
  busca. Resolve acento e caixa **em qualquer banco**, com uma coluna indexável
  no lugar de cinco `LIKE` com `OR`.
- Migration `0009`: `pg_trgm` + `unaccent` + índices GIN, **condicionais por
  vendor**. Em SQLite não faz nada e o projeto continua funcionando.
- No PostgreSQL, `services/busca.py` acrescenta full-text em português com
  ranking, e mantém o `LIKE` normalizado como rede de segurança para o que o
  dicionário não cobre (nomes próprios, siglas).

**PROBLEMAS ENCONTRADOS**
- `CREATE EXTENSION` exige superusuário em algumas hospedagens. A migration
  registra aviso e segue: a busca continua correta, só sem o índice.

**TESTES:** `test_navegacao.BuscaTests` (5).

---

## FASES 8, 9 — RESERVAS E CAPACIDADE

**STATUS:** concluídas

**ALTERAÇÕES**
- `services/reservas.py`: `reservar`, `cancelar`, `marcar_utilizado`,
  `vagas_restantes`, `resumo_de_ocupacao`.
- `Evento.capacidade` e `Evento.limite_por_usuario`.
- `Ingresso.utilizado_em` e `cancelado_em`.
- Tela de check-in na porta (`/ingresso/<uuid>/validar/`), que dá uso ao status
  `UTILIZADO` — ele existia no modelo e nunca era atribuído.
- Lista de inscritos com exportação CSV para o produtor.

**Concorrência:** `select_for_update` na linha do evento dentro de
`@transaction.atomic`. Em SQLite não há lock de linha, mas o backend já roda em
`transaction_mode=IMMEDIATE`, que serializa a escrita.

**Pagamento:** **não implementado, de propósito.** O prompt mestre é explícito:
não implementar pagamento antes de a infraestrutura de reserva estar pronta. A
cadeia reserva → capacidade → estoque existe; pedido, webhook e reembolso não.

**TESTES:** `test_reservas` (20), incluindo `ConcorrenciaTests` com
`TransactionTestCase` e threads reais.

---

## FASE 10 — STORAGE DE IMAGENS

**STATUS:** concluída

**ALTERAÇÕES**
- `MEDIA_BACKEND=s3` funciona com S3, R2 e B2 via `django-storages`.
- `services/imagens.py`: variantes 400/800/1200 em WebP, geradas no upload.
- Tag `{% capa %}` e filtro `|srcset` no template.
- Comando `gerar_variantes_imagem` para as capas antigas.

**Por que importa:** o upload aceita até 5 MB. Sem variantes, um JPEG de 5 MB
era baixado inteiro para preencher um card de 400 px. Doze cards podiam
significar 60 MB.

**PROBLEMAS ENCONTRADOS**
- Falha de geração de variante **não** derruba o salvamento: sem variante, o
  template cai no original. Foi decisão consciente — impedir o produtor de
  publicar porque o Pillow engasgou seria pior.

---

## FASES 11, 13 — INGESTÃO E CONECTORES

**STATUS:** concluídas

**ALTERAÇÕES**
- `eventos/scraping/` → `eventos/ingestao/`. O nome antigo descrevia uma das
  fontes, não a arquitetura.
- `eventos/scraping.py`: atalho de compatibilidade com `DeprecationWarning`,
  para não quebrar script de deploy nem import de terceiro.
- Conectores: `mapa_nas_nuvens.py`, `jsonld.py`, `ics.py`, `parceiros.py`,
  `sympla_api.py`, mais `http.py` com robots.txt, timeout e teto de 5 MB.
- "Colar link" no formulário do produtor: lê JSON-LD, cai para Open Graph.

**Contrato preservado:** toda fonte produz `EventoImportado` e passa por
`salvar_importados()`. Quem grava no banco é só essa função.

**Sobre a Sympla:** a API pública devolve **apenas os eventos do dono do
token** — não tem busca por cidade. Isso descarta a Sympla como fonte de
agregação, mas abre uma porta melhor: o produtor conecta a conta dele e os
eventos passam a aparecer sozinhos. Vira argumento de aquisição em vez de risco
jurídico.

**PROBLEMAS ENCONTRADOS**
- **Os 9 parceiros do DF estão mapeados com `feed=None` e inativos.**
  Preencher URL sem falar com o parceiro é voltar a raspar, que é exatamente o
  que esta fase existe para evitar.

**TESTES:** `test_ingestao` (33).

---

## FASE 12 — MEDIR O MAPA NAS NUVENS

**STATUS:** **NÃO CUMPRIDA — [VERIFICAR NO AMBIENTE]**

O comando `medir_mapa_nas_nuvens` foi escrito e informa volume de eventos
futuros, preenchimento de cada campo, cobertura por RA, horizonte de datas e um
veredito objetivo (≥60 nos próximos 30 dias = fonte primária; ≥20 = uma das
fontes; abaixo = insuficiente).

**Mas sem rede eu não medi nada.** O volume real dessa fonte continua
desconhecido. O prompt mestre é explícito: não construa infraestrutura em cima
de uma fonte cujo volume ninguém verificou.

```bash
python manage.py medir_mapa_nas_nuvens
```

---

## FASE 14 — DESLIGAMENTO DO SELENIUM

**STATUS:** preparada, **não executada — corretamente**

O prompt mestre determina: não remover antes de as fontes novas funcionarem.
Como a FASE 12 não pôde ser medida, remover agora seria irresponsável.

**O que foi feito**
- `SYMPLA_SCRAPING_ATIVO=False` por padrão; o conector levanta `RuntimeError`
  explicando o que usar no lugar.
- Cabeçalho no arquivo com o prazo e a razão de ele ainda existir.
- Bug de fuso corrigido nele também.
- `requirements-scraping.txt` reescrito deixando claro que é legado.
- Comando `comparar_catalogo`: mostra o volume por fonte e dá o veredito de
  quando dá para apagar.
- Roteiro de remoção em 5 passos no README.

---

## FASE 15 — AGENDAMENTO

**STATUS:** concluída

`manutencao_catalogo` reúne a rotina diária: importar, geocodificar, arquivar
vencidos, limpar locais órfãos. As linhas de cron estão no docstring do comando
e no README.

**Decisão:** cron, não Celery. Subir broker e worker para três tarefas diárias é
infraestrutura que não se paga. A migração para Celery Beat é uma linha
(`call_command("manutencao_catalogo")`) quando o volume justificar.

---

## FASES 16, 17, 18 — DESCOBERTA HIPERLOCAL

**STATUS:** concluídas

**ALTERAÇÕES**
- `/mapa/` com Leaflet + OpenStreetMap, carregado sob demanda (~150 KB que não
  fazem sentido no orçamento de nenhuma outra página).
- `/mapa/dados/` devolve GeoJSON respeitando os filtros ativos.
- Botão "Perto de mim" com `navigator.geolocation`, raios de 1 a 20 km.
- Filtros novos: intervalo de datas, distância, acessibilidade, proximidade de
  metrô, estacionamento.
- `/locais/` e `/local/<slug>/` com endereço, mapa, metrô, acessibilidade,
  programação e espaços vizinhos.
- `/produtores/` e `/produtor/<slug>/` com logo, bio, redes, verificação,
  próximos e passados.

**Progressivo:** sem JavaScript, a lista continua acessível e o `<noscript>`
leva para ela.

---

## FASE 19 — CALENDÁRIO

**STATUS:** concluída

`services/calendario.py` gera `.ics` conforme RFC 5545 (CRLF, folding em 75
octetos, escape correto), sem biblioteca — um VEVENT é texto e o formato é
estável há vinte anos.

- `/evento/<slug>/agenda.ics` — um evento
- `/agenda.ics` — a agenda inteira ou o recorte de uma faceta, assinável
- Link direto para o Google Agenda

---

## FASE 20 — E-MAILS

**STATUS:** concluída

8 templates: evento recebido, publicado, rejeitado (com motivo), voltou para
revisão; reserva confirmada, cancelada; lembrete de véspera; conta excluída.

**Falha de SMTP nunca derruba a requisição** — registra no log e segue. A
interface já prometia "Avisaremos assim que for publicado" e nada era enviado.

---

## FASE 21 — LGPD

**STATUS:** concluída

A política prometia acesso, correção, portabilidade e exclusão, e apontava para
uma central de ajuda que **não tinha canal de contato nenhum**.

- `/conta/privacidade/` — painel de dados
- `/conta/privacidade/exportar/` — JSON completo, imediato
- `/conta/privacidade/excluir/` — exige senha e a palavra "EXCLUIR"
- `/contato/` — canal que faltava, com o encarregado de dados
- `AceiteDeTermos` registra versão dos termos, versão da política, data e IP

**Decisão de exclusão:** o usuário é apagado **de verdade**, não desativado.
Direito à exclusão com a linha continuando no banco não é exclusão. Já os
eventos publicados **ficam**, sem vínculo: apagá-los derrubaria compromissos
públicos que terceiros usaram para se planejar.

**TESTES:** `test_lgpd` (17).

---

## FASE 22 — OBSERVABILIDADE

**STATUS:** concluída

- `/saude/` — liveness, barato para o balanceador
- `/saude/detalhado/?token=…` — banco, cache, storage e métricas do catálogo;
  responde 404 sem token
- Logging estruturado com canais `eventos.seguranca` e `eventos.ingestao`
- Sentry opcional via `SENTRY_DSN`, com `send_default_pii=False`

---

## FASE 23 — SEO

**STATUS:** concluída

**O problema:** `FacetasSitemap` gerava 52 URLs com querystring apontando para a
**mesma página**, todas com o mesmo `<title>` e o mesmo `<h1>`. Para o Google,
conteúdo duplicado em massa — o oposto do que se queria.

**A correção:** páginas de faceta com caminho próprio
(`/eventos/categoria/<slug>/`, `/eventos/regiao/<slug>/`, `/eventos/hoje/`,
`/eventos/fim-de-semana/`, `/eventos/gratuitos/`), cada uma com título, texto
editorial e canônica próprios. Sitemaps separados para categorias, regiões,
locais e produtores — só o que tem evento.

Canônica ignora querystring. Schema.org/Event ganhou `geo`, `organizer.url` e
`availability` refletindo esgotamento.

**TESTES:** `test_navegacao.FacetasTests` (7).

---

## FASES 24, 25 — UX E ACESSIBILIDADE

**STATUS:** concluídas

- `--texto-fraco` de `#8a7d95` (3,2:1) para `#6d6178` (5,1:1) — estava abaixo do
  mínimo AA para texto normal.
- `AcessibilidadeMixin` liga erro e ajuda ao input por `aria-describedby`, com
  `aria-invalid` e `role="alert"`. Antes, um leitor de tela anunciava "campo
  obrigatório" sem nunca dizer qual era o problema.
- `prefers-reduced-motion` e `prefers-color-scheme: dark` respeitados.
- Bug corrigido: o botão "Compartilhar" contém um `<svg>`; trocar `textContent`
  apagava o ícone, que nunca voltava.
- Estados vazios com ação, `<datalist>` de locais conhecidos, selo de esgotado,
  trilha de navegação, folha de impressão.

---

## FASES 26, 27, 28, 29 — TESTES, MIGRATIONS, PERFORMANCE, LIMPEZA

**STATUS:** concluídas, **com a ressalva do topo**

**Testes:** `tests.py` virou pacote. Os 64 originais estão intactos em
`test_legado.py`; 153 novos distribuídos por área. Total: **217**.

**Migrations:** a `0006` importava `eventos.constants`. Como a correção de
`Categoria.UNIVERSITARIO` mudaria o comportamento dela retroativamente numa
instalação limpa, as listas foram congeladas por extenso dentro do arquivo — as
operações continuam idênticas. **Nenhuma das 9 migrations importa código do
app.** A `0008` é reversível e não apaga nada.

**Performance:** `para_cards()` com `select_related` nas listagens;
visualização deduplicada por sessão; separação de ingressos feita no banco (era
carregada inteira na memória); recorte por bounding box antes do cálculo exato
de distância; imagens em WebP com `srcset`.

**Limpeza:** `ATALHOS_PERIODO` e `CATEGORIAS_MENU` removidos do context
processor (nenhum template usava, e ele roda em toda requisição); imports mortos
removidos; `requirements` separados em núcleo, produção e legado.

---

## FASE 30 — VERIFICAÇÃO FINAL

**STATUS:** parcial — ver o aviso do topo

O que passou está na tabela da abertura. O que não pôde rodar:
`manage.py check`, `manage.py test`, `makemigrations --check`, `migrate`, e a
verificação manual das telas.
