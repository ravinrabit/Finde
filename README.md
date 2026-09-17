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
└── ingestao/        "colar link": preenche o formulário a partir de uma URL
    ├── base.py              EventoImportado (o preview de um link colado)
    ├── http.py              urllib com robots.txt, SSRF, timeout e teto de tamanho
    └── jsonld.py            lê schema.org/Event e Open Graph da página colada
```

Não há mais ingestão automática em segundo plano (Sympla, Mapa nas Nuvens,
feeds de parceiro). Eventos entram no catálogo só de dois jeitos: o produtor
cadastra (com ajuda opcional de "colar link", que só pré-preenche o
formulário — quem revisa e envia é sempre uma pessoa) ou a equipe cadastra
pelo painel administrativo. Todo evento criado por um produtor entra como
**PENDENTE** e espera moderação; o que a equipe cria pelo painel já nasce
publicado.

---

## Áreas administrativas

- **Área do produtor** (`/meus-eventos/`): shell próprio com navegação lateral
  (Meus eventos, Publicar evento, Meus ingressos, Perfil de produtor),
  reaproveitando as mesmas views de sempre — só ganhou uma segunda camada de
  navegação (`eventos/templates/eventos/produtor/_base.html`).
- **Painel admin** (`/painel-admin/`): além de moderar (publicar/rejeitar/
  arquivar), agora tem CRUD de verdade para Evento, Local e Produtor, com a
  cara do site — `/admin/` do Django continua existindo como acesso de
  emergência, mas deixou de ser necessário no dia a dia. Apagar de vez exige
  digitar o nome do registro (mesmo padrão de confirmação da exclusão de
  conta); "Arquivar" continua sendo a opção reversível.

---

## Fontes de eventos

| Fonte | Como funciona |
|---|---|
| Cadastro manual (produtor) | Formulário em `/criar-evento/`. Entra como PENDENTE. |
| Colar link | O produtor cola o link do próprio evento; lemos JSON-LD ou Open Graph só para pré-preencher o formulário — nada é gravado sem revisão. |
| Cadastro pela equipe | Painel admin (`/painel-admin/`), já publica direto. |

---

## Automação

```cron
# geocodificar pendentes, arquivar vencidos e limpar órfãos
0 6 * * *  cd /app && python manage.py manutencao_catalogo >> /var/log/finde-cron.log 2>&1
# lembrete de véspera para quem reservou
0 10 * * * cd /app && python manage.py enviar_lembretes >> /var/log/finde-cron.log 2>&1
# limpeza de sessões
0 3 * * 0  cd /app && python manage.py clearsessions
```

Cron dá conta do tamanho atual. Com Celery Beat, a mesma rotina vira uma task
periódica chamando `call_command("manutencao_catalogo")` — não vale subir broker
e worker só por isso enquanto cron resolve.

Geocodificação também acontece na hora: ao salvar um evento com um `Local`
novo (sem coordenada), `catalogo.salvar_evento_do_produtor` já chama o
geocodificador antes de devolver a resposta, então o marcador aparece no mapa
sem esperar o cron. `manutencao_catalogo`/`geocodificar` continuam servindo
para reprocessar em lote o que falhou ou ficou aproximado.

### Comandos disponíveis

| Comando | O que faz |
|---|---|
| `geocodificar` | Preenche coordenadas via Nominatim, respeitando 1 req/s. |
| `manutencao_catalogo` | Rotina diária: geocodifica pendentes, arquiva vencidos, limpa órfãos. |
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
| `0013` | Remove IntegracaoSympla — ingestão automática (Sympla/scraping) saiu do produto |

A `0008` é reversível e **não apaga nada**: a reversão desfaz os vínculos e
remove só as linhas que ela criou.

---

## Acessibilidade

- Erros de formulário ligados ao input por `aria-describedby`, com
  `aria-invalid` e `role="alert"`.
- `--texto-fraco` foi de `#8a7d95` (3,2:1) para `#6d6178` (5,1:1), acima do
  mínimo AA.
- `prefers-reduced-motion` e `prefers-color-scheme: dark` respeitados, com
  alternância manual de tema (claro/escuro/sistema), tamanho de fonte e alto
  contraste no botão de preferências do cabeçalho — persistido em
  `localStorage`, aplicado antes do primeiro paint para não piscar.
  `color-scheme` é declarado explicitamente (`:root` e por tema), o que também
  corrige o combo de região aparecendo com texto claro sobre fundo claro no
  modo escuro.
- Mapa e geolocalização são progressivos: sem JavaScript, a lista continua
  acessível.
- Página dedicada em `/acessibilidade/`.

---

## Destaque pago

`Evento.plano_destaque` (normal/destaque/destaque-plus/premium) e
`Evento.destaque_pago_ate` controlam uma ordenação adicional (por trás de
`EventoQuerySet.com_rank_destaque()`) que só entra como critério de desempate
antes da data — não afeta ordenação explícita por preço/recência/distância.

Fluxo, hoje sem gateway de pagamento (de propósito — ver "O que ainda não foi
feito"): o produtor pede um plano em `/evento/<slug>/destacar/`, cria um
`SolicitacaoDestaque`; a equipe combina o pagamento por fora (Pix, por
exemplo) e confirma em `/painel-admin/destaques/`, o que ativa o plano por
`DIAS_DESTAQUE_PADRAO` (30) dias. Preços e a página pública de vendas ficam em
`/anuncie/` (`eventos/constants.py:PRECO_POR_PLANO`).

---

## Assistente de IA

`eventos/services/assistente.py` fala com qualquer endpoint compatível com a
API de chat da OpenAI — o padrão aponta para um **Ollama local**
(`http://localhost:11434/v1`), sem custo por token e sem chave. Troca de
provedor é só variável de ambiente (`IA_API_BASE`, `IA_API_KEY`, `IA_MODELO`),
sem mudar código.

O contexto passado ao modelo vem de `services/busca.aplicar()` (o mesmo motor
de busca do site) sobre os eventos visíveis — o prompt deixa explícito para
não inventar evento fora dessa lista. Endpoint em `/assistente/perguntar/`,
com rate limit próprio (`RATELIMITS["assistente"]`) por ser uma chamada
cara/lenta. Sem Ollama rodando, a view responde 503 e o widget mostra um
aviso — o recurso é opcional e nunca derruba o site.

**Em produção (Render), isso só funciona se o Django conseguir alcançar um
Ollama pela internet** (sua própria máquina exposta com cuidado, ou um
servidor/VPS rodando o Ollama) — `IA_ATIVO=False` desliga o recurso por
completo.

---

## O que ainda não foi feito

- **Pagamento não existe.** A cadeia reserva → capacidade → estoque está
  pronta; pedido, webhook e reembolso não. Deliberado: não faz sentido antes de
  a infraestrutura de reserva rodar em produção. Isso inclui o destaque pago:
  a confirmação de pagamento hoje é manual, pela equipe.
- **Coordenadas do metrô e das RAs são aproximadas** (4 casas decimais, de
  fontes públicas). Conferir antes de produção.
