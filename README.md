# Finde

**Plataforma de descoberta de eventos em Brasília e no Distrito Federal.**

Um app Django que responde, nessa ordem: o que está acontecendo, onde é, o
que tem perto de mim e quem está organizando. Venda de ingresso é
consequência do catálogo, não o ponto de partida do produto.

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-6.x-092E20?logo=django&logoColor=white)
![Status](https://img.shields.io/badge/status-em%20desenvolvimento-yellow)
![Licença](https://img.shields.io/badge/licença-a%20definir-lightgrey)

---

## Sumário

- [Visão geral](#visão-geral)
- [Funcionalidades](#funcionalidades)
- [Stack técnica](#stack-técnica)
- [Arquitetura](#arquitetura)
- [Como rodar localmente](#como-rodar-localmente)
- [Variáveis de ambiente](#variáveis-de-ambiente)
- [Testes](#testes)
- [Painel administrativo](#painel-administrativo)
- [Fontes de eventos](#fontes-de-eventos)
- [Automação e comandos](#automação-e-comandos)
- [Banco de dados](#banco-de-dados)
- [Armazenamento de mídia](#armazenamento-de-mídia)
- [Segurança](#segurança)
- [LGPD](#lgpd)
- [Observabilidade](#observabilidade)
- [Acessibilidade](#acessibilidade)
- [Roadmap](#roadmap)
- [Equipe](#equipe)
- [Licença](#licença)

---

## Visão geral

O Finde é uma agenda hiperlocal: a home é uma lista de eventos ordenada por
relevância e proximidade, não uma vitrine de compra. Locais e produtores são
entidades de primeira classe, com página própria e SEO próprio — não apenas
metadado de um evento.

O catálogo é alimentado por múltiplas fontes (importação automática, link
colado pelo produtor, integração com Sympla) e passa por uma fila de
moderação antes de qualquer coisa ir ao ar.

## Funcionalidades

- Busca e listagem de eventos com filtro por categoria, região, data e preço
- Páginas dedicadas para eventos, locais e produtores, com dados estruturados
  (`schema.org`) para SEO
- Mapa interativo (Leaflet) com geolocalização e seletor de região como
  fallback
- Reserva de ingresso com controle de capacidade e limite por pessoa
- Favoritos, exportação de agenda (`.ics`) e lembrete por e-mail
- PWA instalável, com service worker e página offline
- Painel administrativo dedicado para moderação de eventos e verificação de
  produtores (ver [seção própria](#painel-administrativo))
- Exportação e exclusão de dados pessoais em autoatendimento (LGPD)
- Rate limiting em login, cadastro, recuperação de senha, reserva e busca

## Stack técnica

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.12, Django 6.x |
| Banco de dados | SQLite (padrão) ou PostgreSQL |
| Cache / rate limit | Cache do Django (`locmem`, `db` ou Redis) |
| Frontend | CSS e JS próprios, sem framework — Leaflet.js para mapas |
| Arquivos estáticos | WhiteNoise |
| Mídia | Disco local ou S3-compatível (S3, Cloudflare R2, Backblaze B2) |
| E-mail transacional | SMTP configurável via `.env` |
| Observabilidade | Sentry (opcional), healthchecks próprios |
| PWA | Service worker e manifest nativos |

## Arquitetura

App único, `eventos`, com a lógica de negócio isolada em serviços — views
tratam só HTTP, services concentram regra testável sem cliente HTTP.

```
eventos/
├── models.py         Evento, Local, Produtor, Ingresso, Favorito, AceiteDeTermos
├── views.py          views públicas: recebem, delegam, respondem
├── views_painel.py   views do painel administrativo
├── forms.py          validação de entrada e acessibilidade dos campos
├── decorators.py     staff_requerido — 404 para quem não é staff
├── ratelimit.py      limite de tentativas sobre o cache
├── middleware.py      endurecimento do admin nativo
├── signals.py          User.username sincronizado com User.email
├── emails.py           e-mails transacionais
├── services/           regra de negócio testável sem cliente HTTP
│   ├── busca.py           busca tolerante a acento e caixa
│   ├── reservas.py        capacidade, limite por pessoa, concorrência
│   ├── catalogo.py        resolução de Local/Produtor e política de moderação
│   ├── moderacao.py       publicar/rejeitar/arquivar evento, verificar produtor
│   ├── painel.py          estatísticas e filas do painel administrativo
│   ├── calendario.py      exportação .ics (RFC 5545)
│   ├── geocoding.py       Nominatim com cache e limite de taxa
│   ├── imagens.py         variantes WebP 400/800/1200
│   └── lgpd.py            exportação e exclusão de dados
└── ingestao/            entrada de eventos externos
    ├── base.py               EventoImportado + salvar_importados
    ├── http.py               urllib com robots.txt, timeout e teto de tamanho
    ├── mapa_nas_nuvens.py    API pública do GDF
    ├── jsonld.py             schema.org/Event e "colar link"
    ├── ics.py                feeds iCalendar
    ├── parceiros.py          espaços com acordo
    ├── sympla_api.py         token cedido pelo produtor
    └── sympla.py             legado, por Selenium, desligado por padrão
```

**Contrato de ingestão:** toda fonte produz `EventoImportado` e passa por
`salvar_importados()`. É esse ponto único de gravação que torna trocar de
fonte um detalhe e não uma reescrita — e garante que todo evento importado
entra como **pendente**, sem exceção.

## Como rodar localmente

### Pré-requisitos

- Python 3.12+
- pip e venv

### Instalação

```bash
git clone https://github.com/ravinrabit/Finde.git
cd Finde

python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\Activate.ps1

pip install -r requirements.txt

cp .env.example .env              # ajuste as variáveis (ver seção abaixo)
python manage.py gerar_secret_key # cole a SECRET_KEY gerada no .env

python manage.py migrate
python manage.py createsuperuser
python manage.py semear_demo      # opcional: catálogo de exemplo

python manage.py runserver
```

O site sobe em `http://localhost:8000`. O admin nativo do Django fica em
`/admin/` por padrão, ou no caminho definido em `ADMIN_URL`.

## Variáveis de ambiente

Todas as chaves ficam documentadas e comentadas em `.env.example`. Resumo por
categoria:

| Categoria | Variáveis |
|---|---|
| Núcleo | `DJANGO_ENV`, `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SITE_NOME`, `SITE_DOMINIO` |
| Banco de dados | `DB_ENGINE`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` |
| Cache | `CACHE_BACKEND`, `REDIS_URL` |
| E-mail | `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL`, `EMAIL_CONTATO`, `EMAIL_ENCARREGADO_LGPD` |
| Admin | `ADMIN_URL`, `ADMIN_IPS_PERMITIDOS` |
| Mídia | `MEDIA_BACKEND`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_STORAGE_BUCKET_NAME` |
| Integrações | `MAPA_NAS_NUVENS_URL`, `SYMPLA_SCRAPING_ATIVO`, `GEOCODING_URL`, `GEOCODING_USER_AGENT`, `GEOCODING_LIMITE_POR_EXECUCAO`, `GEOCODING_PAUSA_SEGUNDOS` |
| Segurança/rede | `SECURE_SSL_REDIRECT`, `RATELIMIT_ATIVO` |
| Observabilidade | `SENTRY_DSN`, `SENTRY_TRACES`, `LOG_LEVEL`, `HEALTHCHECK_TOKEN` |

A escolha de ambiente (`dev`, `test`, `prod`) vem de `DJANGO_ENV`:

```
setup/settings/
├── base.py    comum a todos os ambientes
├── dev.py     DEBUG ligado, estáticos sem manifesto
├── test.py    banco em memória, sem rede, sem rate limit
└── prod.py    HTTPS obrigatório, HSTS, cookies seguros, Sentry
```

## Testes

```bash
python manage.py test
```

`manage.py test` força `DJANGO_ENV=test` automaticamente: banco em memória,
hasher de senha rápido, e-mail em memória, nenhuma chamada de rede real.

## Painel administrativo

Área dedicada à moderação, separada do admin nativo do Django — restrita a
usuários `is_staff` (404, não redirecionamento, para quem não é).

| Rota | Função |
|---|---|
| `/painel-admin/` | estatísticas gerais (eventos por status, produtores pendentes, ingressos da semana) |
| `/painel-admin/moderacao/` | fila de eventos com filtro por status e busca; publicar, rejeitar (com motivo) ou arquivar |
| `/painel-admin/produtores/` | verificação de identidade do produtor |

A regra de publicar/rejeitar/arquivar vive em `eventos/services/moderacao.py`
— fonte única, usada tanto pelas ações do admin nativo quanto pelas views do
painel, para as duas superfícies nunca divergirem. `eventos/services/painel.py`
cuida só das consultas de estatística e fila.

`eventos/signals.py` sincroniza `User.username` com `User.email` em todo
`save()`, resolvendo na origem o caso clássico de um superuser criado via
`createsuperuser` ficar sem conseguir logar (o formulário de login espera
e-mail no campo de usuário).

## Fontes de eventos

| Fonte | Situação | Observação |
|---|---|---|
| Mapa nas Nuvens | conector pronto, volume não medido | API pública do GDF — rode `medir_mapa_nas_nuvens` antes de confiar |
| Parceiros | arquitetura pronta, todos inativos | 9 espaços do DF mapeados, aguardando acordo |
| Colar link | funcionando | lê JSON-LD ou Open Graph do link enviado pelo produtor |
| Sympla por token | funcionando | o produtor conecta a própria conta; a API só devolve os eventos do dono do token |
| Sympla por Selenium | legado, desligado | ver `SYMPLA_SCRAPING_ATIVO` e o roteiro de desligamento no código |

## Automação e comandos

```cron
0 6 * * *  cd /app && python manage.py manutencao_catalogo >> /var/log/finde-cron.log 2>&1
0 10 * * * cd /app && python manage.py enviar_lembretes >> /var/log/finde-cron.log 2>&1
0 3 * * 0  cd /app && python manage.py clearsessions
```

| Comando | Função |
|---|---|
| `importar_eventos` | importa de uma fonte ou de todas (`--simular` para conferir sem gravar) |
| `medir_mapa_nas_nuvens` | mede volume e qualidade da API do GDF |
| `comparar_catalogo` | avalia se já dá para desligar o Selenium |
| `geocodificar` | preenche coordenadas via Nominatim, 1 req/s |
| `manutencao_catalogo` | rotina diária completa |
| `enviar_lembretes` | e-mail de véspera para quem reservou |
| `gerar_variantes_imagem` | gera WebP 400/800/1200 das capas antigas |
| `gerar_secret_key` | gera chave nova e imprime o roteiro de rotação |
| `semear_demo` | popula catálogo de exemplo para desenvolvimento |

## Banco de dados

SQLite por padrão; `DB_ENGINE=postgres` no `.env` habilita PostgreSQL.

`Evento.busca_texto` mantém nome, resumo, descrição, local, endereço,
organizador, cidade, categoria e região em minúsculo e sem acento — a mesma
consulta cobre `rock`/`Rock`, `cinema`/`cinéma`, `brasilia`/`Brasília` em
qualquer banco. No PostgreSQL, `services/busca.py` acrescenta full-text em
português com ranking, e a migration `0009` cria os índices GIN de trigrama
(condicional — em SQLite não faz nada, e a busca continua correta).

## Armazenamento de mídia

`MEDIA_BACKEND=local` grava no disco do servidor — **não sobrevive** a um
deploy que troque de máquina ou contêiner. Em produção, use
`MEDIA_BACKEND=s3` (S3, Cloudflare R2 ou Backblaze B2,
`pip install -r requirements-prod.txt`).

Toda capa enviada gera variantes de 400, 800 e 1200 px em WebP, servidas via
`srcset`.

## Segurança

- **`ADMIN_URL`** move o admin nativo para um caminho não óbvio;
  **`ADMIN_IPS_PERMITIDOS`** restringe por origem e responde 404, não 403.
- **Rate limiting** próprio (`eventos/ratelimit.py`, ~80 linhas sobre o cache
  do Django) protege login, cadastro, recuperação de senha, reserva, busca,
  favoritar, colar link e exclusão de conta. Limites em `settings.RATELIMITS`.
  Com `CACHE_BACKEND=locmem` e múltiplos workers, cada processo tem seu
  próprio contador — em produção use `db` ou `redis`.
- **`IntegracaoSympla.token`** nunca aparece em listagem, nunca entra na
  exportação LGPD e é write-only no admin. Em produção, use criptografia em
  repouso (o campo guarda o valor em texto no banco).

> **Se o `.env` já esteve versionado no Git em algum momento**, a
> `SECRET_KEY` correspondente deve ser tratada como pública e trocada — ela
> permite forjar cookie de sessão e token de recuperação de senha. Trocar só
> no `.env` não basta enquanto ela seguir no histórico do repositório; nesse
> caso, rode `git filter-repo` (ou equivalente) antes de considerar o
> repositório seguro.

## LGPD

A página **Meus dados** (`/conta/privacidade/`) resolve em autoatendimento:

- **Acesso e portabilidade** — JSON com conta, ingressos, favoritos, eventos
  publicados e registro de consentimento
- **Exclusão** — remove a conta, ingressos e favoritos do banco de verdade
  (sem desativação)
- **Consentimento** — cada cadastro grava versão dos termos, versão da
  política, data e IP em `AceiteDeTermos`

Eventos publicados continuam no ar após a exclusão da conta, sem vínculo com
a pessoa — apagá-los derrubaria compromissos públicos que terceiros já usaram
para se planejar.

## Observabilidade

| Endpoint | Uso |
|---|---|
| `/saude/` | liveness — barato o bastante para o balanceador chamar |
| `/saude/detalhado/?token=…` | readiness: aplicação, banco, cache e storage; protegido por `HEALTHCHECK_TOKEN` |

Logs estruturados no console, com canais separados para `eventos.seguranca` e
`eventos.ingestao`. Com `SENTRY_DSN` configurado, exceções vão para o Sentry
(`send_default_pii=False`).

## Acessibilidade

- Erros de formulário ligados ao input por `aria-describedby`, com
  `aria-invalid` e `role="alert"`
- Contraste de texto secundário acima do mínimo AA (5,1:1)
- `prefers-reduced-motion` e `prefers-color-scheme: dark` respeitados
- Mapa e geolocalização são progressivos — sem JavaScript, a lista de eventos
  continua acessível

## Roadmap

- [ ] Medir volume real do Mapa nas Nuvens (`medir_mapa_nas_nuvens`)
- [ ] Ativar parceiros conforme acordos forem fechados
- [ ] Pagamento online (reserva → capacidade → estoque já existe; pedido,
      webhook e reembolso ainda não)
- [ ] Conferir coordenadas do metrô e das regiões administrativas antes de
      produção (hoje aproximadas, 4 casas decimais)

## Equipe

Projeto desenvolvido por uma equipe de 6 pessoas, colegas de curso no SENAC.

## Licença

Ainda não definida.
