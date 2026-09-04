# Finde

Plataforma de descoberta de eventos de Brasília e do Distrito Federal.

O Finde responde a quatro perguntas, nessa ordem de prioridade:

> O que está acontecendo em Brasília?
> Onde é?
> O que tem perto de mim?
> Quem está organizando?

Vender ingresso é consequência, não o ponto de partida. Isso explica várias
decisões deste código: a home é uma agenda, não uma vitrine; locais e produtores
são entidades de primeira classe com página própria; e a busca por proximidade
existe no núcleo, não como funcionalidade futura.

---

## Como rodar

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
python manage.py gerar_secret_key      # cole a chave no .env

python manage.py migrate
python manage.py createsuperuser
python manage.py semear_demo           # catálogo de exemplo, opcional
python manage.py runserver
```

O site sobe em `http://localhost:8000`. O painel administrativo fica em
`/admin/` por padrão, ou no caminho que você definir em `ADMIN_URL`.

### Testes

```bash
python manage.py test
```

`manage.py test` força `DJANGO_ENV=test` sozinho: banco em memória, hasher
rápido, e-mail em memória, nenhuma chamada de rede.

---

## Configuração por ambiente

```
setup/settings/
├── base.py    tudo o que é comum
├── dev.py     DEBUG ligado, arquivos estáticos sem manifesto
├── test.py    banco em memória, sem rede, sem rate limit
└── prod.py    HTTPS obrigatório, HSTS, cookies seguros, Sentry
```

A escolha vem de `DJANGO_ENV` (`dev`, `test`, `prod`). O
`DJANGO_SETTINGS_MODULE` continua sendo `setup.settings`, então nenhum script
de deploy existente precisa mudar.

Todas as chaves estão em `.env.example`, comentadas.

---

## Segurança

### A SECRET_KEY antiga está comprometida

O `.env` esteve versionado no Git. **A chave que estava lá deve ser
considerada pública**: com ela, qualquer pessoa forja cookie de sessão e token
de recuperação de senha. Trocar a chave no `.env` não basta, porque ela
continua no histórico do repositório.

```bash
python manage.py gerar_secret_key      # imprime a chave e o roteiro completo

# 1. cole a chave nova no .env e reinicie
# 2. derrube as sessões existentes
python manage.py shell -c "from django.contrib.sessions.models import Session; Session.objects.all().delete()"

# 3. limpe o histórico do Git
pip install git-filter-repo
git filter-repo --path .env --invert-paths --force
git push --force --all                 # combine com quem já clonou

# 4. rotacione o resto: senha de SMTP, credencial de banco, token de storage
```

Se o repositório for público ou já tiver sido clonado por terceiros, considere-o
queimado e recrie.

### Rate limiting

`eventos/ratelimit.py` implementa um contador de janela fixa sobre o cache do
Django. Protege login, cadastro, recuperação de senha, reserva, busca,
favoritar, colar link e exclusão de conta. Os limites ficam em
`settings.RATELIMITS`.

Não usa `django-ratelimit` nem `django-axes` de propósito: o projeto inteiro
tem quatro dependências, e um contador de 80 linhas resolvia o problema real.

**Limitação:** depende do cache. Com `CACHE_BACKEND=locmem` e vários workers,
cada processo tem o próprio contador e o limite efetivo se multiplica. Em
produção use `db` (`manage.py createcachetable`, sem pacote novo) ou `redis`.

### Admin

`ADMIN_URL` move o painel para um caminho não óbvio — não substitui
autenticação, mas tira o `/admin/` das varreduras automatizadas.
`ADMIN_IPS_PERMITIDOS` restringe por origem e responde **404**, não 403: negar
a existência entrega menos informação do que negar a permissão.

---

## Arquitetura

App único, `eventos`, com a lógica de negócio separada em serviços.

```
eventos/
├── models.py        Evento, Local, Produtor, Ingresso, Favorito, AceiteDeTermos
├── views.py         só HTTP: recebe, delega, responde
├── forms.py         validação de entrada e acessibilidade dos campos
├── ratelimit.py     limite de tentativas sobre o cache
├── middleware.py    endurecimento do admin
├── emails.py        e-mails transacionais
├── services/        regra de negócio testável sem cliente HTTP
│   ├── busca.py         busca tolerante a acento e caixa
│   ├── reservas.py      capacidade, limite por pessoa, concorrência
│   ├── catalogo.py      resolução de Local/Produtor e política de moderação
│   ├── calendario.py    exportação .ics (RFC 5545)
│   ├── geocoding.py     Nominatim com cache e limite de taxa
│   ├── imagens.py       variantes WebP 400/800/1200
│   └── lgpd.py          exportação e exclusão de dados
└── ingestao/        entrada de eventos externos
    ├── base.py              EventoImportado + salvar_importados
    ├── http.py              urllib com robots.txt, timeout e teto de tamanho
    ├── mapa_nas_nuvens.py   API pública do GDF
    ├── jsonld.py            schema.org/Event e "colar link"
    ├── ics.py               feeds iCalendar
    ├── parceiros.py         espaços com acordo
    ├── sympla_api.py        token cedido pelo produtor
    └── sympla.py            LEGADO, por Selenium, desligado por padrão
```

### O contrato de ingestão

Toda fonte, sem exceção, produz `EventoImportado` e passa por
`salvar_importados()`. É o que torna trocar de fonte um detalhe em vez de uma
reescrita. Quem grava no banco é só essa função, então a política de curadoria,
a idempotência e o vínculo com `Local`/`Produtor` ficam num lugar só.

Evento importado entra como **PENDENTE**. Nada vindo de fora vai ao ar sem
alguém olhar.

---

## Fontes de eventos

| Fonte | Situação | Observação |
|---|---|---|
| Mapa nas Nuvens | conector pronto, **volume não medido** | API pública do GDF. Rode `medir_mapa_nas_nuvens` antes de confiar. |
| Parceiros | arquitetura pronta, **todos inativos** | 9 espaços do DF mapeados com `feed=None`. Preencha conforme cada acordo. |
| Colar link | funcionando | O produtor cola o link do próprio evento; lemos JSON-LD ou Open Graph. |
| Sympla por token | funcionando | O produtor conecta a conta dele. A API só devolve os eventos do dono do token. |
| Sympla por Selenium | **legado, desligado** | Ver "Desligamento do Selenium". |

### Por que a Sympla não serve para agregação

A API pública da Sympla devolve apenas os eventos do dono do token — não tem
busca por cidade. Isso descarta a Sympla como fonte de catálogo, mas abre uma
porta melhor: o produtor que já usa Sympla conecta a conta e os eventos dele
passam a aparecer no Finde sozinhos. Vira argumento de aquisição em vez de
risco jurídico.

### Antes de confiar no Mapa nas Nuvens

```bash
python manage.py medir_mapa_nas_nuvens
```

O comando informa quantos eventos futuros existem, quais campos vêm
preenchidos, a cobertura por região administrativa e o horizonte de datas — e
dá um veredito. Enquanto isso não rodar, **o volume real dessa fonte é
desconhecido** e nenhuma decisão de roadmap deveria depender dela.

### Desligamento do Selenium

O importador legado continua no repositório por uma razão só: desligar antes de
as fontes novas terem volume deixaria o catálogo vazio, e catálogo vazio mata o
produto mais rápido do que qualquer risco jurídico.

Ele já vem desligado (`SYMPLA_SCRAPING_ATIVO=False`). A régua para removê-lo:

```bash
python manage.py comparar_catalogo
```

Quando o comando disser que as fontes legítimas sustentam a home:

1. `rm eventos/ingestao/sympla.py`
2. `rm requirements-scraping.txt`
3. tirar `sympla-legado` de `FONTES` em `management/commands/importar_eventos.py`
4. remover `SYMPLA_SCRAPING_ATIVO` de `settings/base.py` e do `.env.example`
5. `rm eventos/scraping.py` (o atalho de compatibilidade)

---

## Automação

Nada aqui depende de alguém lembrar de rodar comando na mão.

```cron
# importar, geocodificar, arquivar vencidos e limpar órfãos
0 6 * * *  cd /app && python manage.py manutencao_catalogo >> /var/log/finde-cron.log 2>&1
# lembrete de véspera para quem reservou
0 10 * * * cd /app && python manage.py enviar_lembretes >> /var/log/finde-cron.log 2>&1
# limpeza de sessões
0 3 * * 0  cd /app && python manage.py clearsessions
```

Cron dá conta do tamanho atual. Com Celery Beat, a mesma rotina vira uma task
periódica chamando `call_command("manutencao_catalogo")` — não vale subir broker
e worker só por isso enquanto cron resolve.

### Comandos disponíveis

| Comando | O que faz |
|---|---|
| `importar_eventos` | Importa de uma fonte ou de todas. `--simular` para conferir sem gravar. |
| `medir_mapa_nas_nuvens` | Mede volume e qualidade da API do GDF antes de confiar nela. |
| `comparar_catalogo` | Diz se já dá para desligar o Selenium. |
| `geocodificar` | Preenche coordenadas via Nominatim, respeitando 1 req/s. |
| `manutencao_catalogo` | Rotina diária completa. |
| `enviar_lembretes` | E-mail de véspera. |
| `gerar_variantes_imagem` | Gera os WebP 400/800/1200 das capas antigas. |
| `gerar_secret_key` | Chave nova e roteiro de rotação. |
| `semear_demo` | Catálogo de exemplo para desenvolvimento. |

---

## Banco de dados

SQLite por padrão. Para PostgreSQL, basta `DB_ENGINE=postgres` no `.env`.

### Busca

`Evento.busca_texto` guarda nome, resumo, descrição, local, endereço,
organizador, cidade, categoria e região — tudo minúsculo e sem acento,
mantido no `save()`. Buscar nessa coluna resolve, em qualquer banco:

```
rock / Rock / ROCK        -> mesma consulta
cinema / cinéma           -> mesma consulta
brasilia / Brasília       -> mesma consulta
```

No PostgreSQL, `services/busca.py` acrescenta full-text em português com
ranking, e a migration `0009` cria os índices GIN de trigrama que fazem o
`LIKE` usar índice. A migration é condicional: em SQLite ela simplesmente não
faz nada, e o projeto continua funcionando — só sem o ganho de desempenho.

`CREATE EXTENSION` exige superusuário em algumas hospedagens. Se falhar, a
migration registra um aviso e segue: a busca continua correta.

---

## Armazenamento de mídia

`MEDIA_BACKEND=local` guarda no disco do servidor. **Isso não sobrevive a um
deploy que troque de máquina ou contêiner** — as capas enviadas somem.

Para produção, `MEDIA_BACKEND=s3` funciona com S3, Cloudflare R2 e Backblaze
B2 (`pip install -r requirements-prod.txt`).

Toda capa enviada gera versões de 400, 800 e 1200 px em WebP, servidas por
`srcset`. Um JPEG de 5 MB deixou de ser baixado inteiro para preencher um card
de 400 px.

---

## LGPD

A página **Meus dados** (`/conta/privacidade/`) entrega, sem depender de pedido
por e-mail:

- **Acesso e portabilidade:** JSON com conta, ingressos, favoritos, eventos
  publicados e o registro de consentimento.
- **Exclusão:** apaga conta, ingressos e favoritos. O usuário é removido do
  banco de verdade, não desativado.
- **Consentimento:** cada cadastro grava versão dos termos, versão da política,
  data e IP em `AceiteDeTermos`.

Os eventos publicados **continuam no ar** depois da exclusão, sem vínculo com a
pessoa. Apagá-los derrubaria compromissos públicos que terceiros já usaram para
se planejar, e prejudicaria quem reservou.

---

## Integrações

`IntegracaoSympla.token` é credencial de terceiro. Ele nunca aparece em
listagem, nunca entra na exportação LGPD e é write-only no admin.

**Em produção, use criptografia em repouso** (pgcrypto ou disco criptografado).
O campo guarda o token em texto no banco.

---

## Observabilidade

| Endpoint | Uso |
|---|---|
| `/saude/` | Liveness. Barato o bastante para o balanceador chamar. |
| `/saude/detalhado/?token=…` | Readiness: aplicação, banco, cache e storage. Protegido por `HEALTHCHECK_TOKEN`. |

Sem `HEALTHCHECK_TOKEN` configurado, o endpoint detalhado responde 404.

Logs vão para o console em formato estruturado, com canais separados para
`eventos.seguranca` e `eventos.ingestao`. Com `SENTRY_DSN`, as exceções vão
para o Sentry (`send_default_pii=False`).

---

## Migrations

Uma migration é o retrato do banco naquele momento. Ela **não pode importar
código do app**: se a constante mudar depois, a migration antiga passa a se
comportar de outro jeito numa instalação limpa.

A `0006` importava `eventos.constants`. Como a correção de
`Categoria.UNIVERSITARIO` (`"universitário"` → `"universitario"`) mudaria o
comportamento dela retroativamente, as listas foram congeladas por extenso
dentro do arquivo. As operações continuam idênticas — o estado do schema não
mudou.

| Migration | Conteúdo |
|---|---|
| `0007` | Schema: Local, Produtor, IntegracaoSympla, AceiteDeTermos, capacidade, busca |
| `0008` | Dados: extrai locais e produtores do texto livre, deduplica, corrige categoria |
| `0009` | Índices de busca do PostgreSQL, condicionais por vendor |

A `0008` é reversível e **não apaga nada**: a reversão desfaz os vínculos e
remove só as linhas que ela criou.

---

## Acessibilidade

- Erros de formulário ligados ao input por `aria-describedby`, com
  `aria-invalid` e `role="alert"`.
- `--texto-fraco` foi de `#8a7d95` (3,2:1) para `#6d6178` (5,1:1), acima do
  mínimo AA.
- `prefers-reduced-motion` e `prefers-color-scheme: dark` respeitados.
- Mapa e geolocalização são progressivos: sem JavaScript, a lista continua
  acessível.

---

## O que ainda não foi feito

- **Volume do Mapa nas Nuvens não foi medido.** Rode `medir_mapa_nas_nuvens`.
- **Nenhum parceiro está ativo.** Preencher `feed` sem acordo seria voltar a
  raspar.
- **Pagamento não existe.** A cadeia reserva → capacidade → estoque está
  pronta; pedido, webhook e reembolso não. Deliberado: não faz sentido antes de
  a infraestrutura de reserva rodar em produção.
- **Coordenadas do metrô e das RAs são aproximadas** (4 casas decimais, de
  fontes públicas). Conferir antes de produção.
