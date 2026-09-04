# FALHAS E PENDÊNCIAS

Compilação honesta do que **não** foi possível fazer, do que ficou incompleto
por decisão, e do que precisa da sua ação. Ordenado por risco.

---

## ATUALIZAÇÃO — PRIMEIRA EXECUÇÃO REAL

Você rodou. Resultado:

```
python manage.py check                             -> System check identified no issues
python manage.py makemigrations --check --dry-run  -> No changes detected
python manage.py test                              -> 217 testes, 140 erros, 1 falha
```

### Resolvido

| Item | Situação |
|---|---|
| **BLOQUEIO 1** — `manage.py check` | passou, zero problemas |
| **BLOQUEIO 2** — migrations à mão | **`No changes detected`.** O estado bate exatamente com os modelos. Era o maior risco da entrega. |

### Os 140 erros não eram bug

Todos idênticos: `ModuleNotFoundError: No module named 'whitenoise'`. Dependência
declarada em `requirements.txt` que não foi instalada no seu ambiente.

```bash
pip install -r requirements.txt
```

Além disso, `setup/settings/test.py` passou a remover o `WhiteNoiseMiddleware`
da pilha: ele serve arquivo estático e não tem papel nenhum em teste. Deixar a
suíte inteira dependendo de um pacote de produção fazia 140 erros esconderem as
falhas de verdade.

### A falha real revelou dois bugs

Um teste falhou de verdade:
`test_legado.ImportacaoTests.test_regiao_vazia_e_preenchida_na_reimportacao`.

Investigando, encontrei **dois** bugs, e o segundo é pior que o primeiro.

**Bug A — `save(update_fields=...)` descartava os campos derivados.**

Desde o Django 4.2, `update_or_create()` chama
`save(update_fields=<chaves de defaults>)`. Tudo que `Evento.save()` deriva —
coordenada herdada do local, região inferida, `busca_texto` — era calculado em
memória e **silenciosamente descartado** na escrita, porque não estava na lista.

Na prática: um evento reimportado nunca recebia a coordenada do local nem a
região inferida. O mapa e o "perto de mim" ficariam permanentemente vazios para
tudo que veio de importação.

Corrigido: cada derivação agora declara o que mexeu, e o conjunto é somado a
`update_fields` antes do `super().save()`.

**Bug B — a correção do BUG 8 não funcionava.**

O widget de data é `<input type="datetime-local">`, com precisão de **minuto**.
O banco guarda o que veio da importação, que costuma ter **segundos**.
Comparar os dois crus faz `20:00:37` e `20:00:00` parecerem datas diferentes:

```
valor no banco     : 2026-09-08 20:00:37.481923
valor do formulário: 2026-09-08 20:00:00
são diferentes?    : True
```

Duas consequências, ambas reais:

1. `alteracoes_sensiveis()` via "data" alterada em **toda** edição — um evento
   publicado voltava para revisão só por ter a descrição corrigida.
2. `clean_data()` achava que a data tinha mudado, então **o evento passado
   continuava impossível de editar**. Ou seja: o BUG 8, que eu declarei
   corrigido no relatório anterior, não estava corrigido.

Corrigido com `Evento._comparavel()`, que trunca datetime no minuto antes de
comparar — a precisão que o formulário realmente oferece. Mudança real de
horário continua devolvendo o evento para revisão.

**6 testes de regressão** foram acrescentados para os dois bugs
(`PrecisaoDeDataTests` e `CamposDerivadosTests`). Total: **223**.

### Ainda não verificado

Os 140 testes que erraram por falta do whitenoise **nunca chegaram a rodar a
lógica que testam**. Depois de instalar a dependência, é bem possível que
apareçam outras falhas — a primeira execução real de uma suíte raramente sai
limpa. Mande a saída que eu corrijo.

---

## BLOQUEIO 1 — O ambiente não tinha Django nem rede

**Impacto: alto. Afeta a confiança em tudo o que está neste entrega.**

```
$ pip install "Django>=6.0,<6.1"
ERROR: Could not find a version that satisfies the requirement Django
ERROR: No matching distribution found for Django
```

Sem Django instalado e sem rede, quatro coisas que o prompt mestre exige em toda
etapa **não aconteceram nenhuma vez**:

| Comando | Situação |
|---|---|
| `python manage.py check` | nunca executado |
| `python manage.py test` | nunca executado |
| `python manage.py makemigrations --check` | nunca executado |
| `python manage.py migrate` | nunca executado |

**Nenhum dos 217 testes rodou.** Eles têm sintaxe válida e a lógica foi escrita
com cuidado, mas "tem sintaxe válida" e "passa" são coisas diferentes, e o
prompt mestre foi explícito sobre não confundir as duas.

### O que rodou no lugar

Escrevi três verificadores estáticos, que passaram limpos:

| Verificação | Resultado |
|---|---|
| `ast.parse` em 74 arquivos Python | limpo |
| `node --check` no JavaScript | limpo |
| Chaves do CSS | 477/477 |
| Nomes de URL usados x declarados | 48 usados, 52 declarados, nenhum órfão |
| Tags e filtros de template x biblioteca | limpo |
| 52 templates referenciados x disco | todos existem |
| Imports internos x módulos | limpo |
| 56 views x referências em `urls.py` | limpo |
| **Campos dos modelos x estado das migrations** | 7 modelos coerentes |
| Índices e constraints x `AddIndex`/`AddConstraint` | coerentes |
| `admin.py` e `forms.py` x campos reais | coerentes |
| `Evento.CAMPOS_SENSIVEIS` x campos reais | coerente |
| Migrations importando código do app | zero |
| Ocorrências de "Orbitae" | zero |

### O que fazer primeiro

```bash
pip install -r requirements.txt
python manage.py check
python manage.py makemigrations --check --dry-run    # ← o mais importante
python manage.py test
```

---

## BLOQUEIO 2 — As migrations 0007–0009 foram escritas à mão

**Impacto: alto. É o ponto de maior risco técnico da entrega.**

Sem `makemigrations`, escrevi as três migrations manualmente. Para reduzir o
risco, nomeei **todos** os índices explicitamente no `Meta` dos modelos e usei
exatamente os mesmos nomes nas migrations — assim o estado não depende do
algoritmo de auto-nomeação do Django.

Depois escrevi um verificador que compara campo a campo:

```
AceiteDeTermos     modelo= 5  migration= 5  ok
Evento             modelo=36  migration=36  ok
Favorito           modelo= 3  migration= 3  ok
Ingresso           modelo= 9  migration= 9  ok
IntegracaoSympla   modelo= 6  migration= 6  ok
Local              modelo=21  migration=21  ok
Produtor           modelo=14  migration=14  ok
```

**O que isso NÃO garante:** o verificador compara **nomes** de campo, índice e
constraint. Ele **não** compara os kwargs (`max_length`, `help_text`,
`default`, `on_delete`). Uma divergência nesses faria `makemigrations --check`
acusar diferença — o que gera uma migration extra, não perda de dados, mas
precisa ser resolvido antes do deploy.

```bash
python manage.py makemigrations --check --dry-run
```

Se acusar diferença, gere a migration `0010` e revise o que ela contém antes de
aplicar.

---

## BLOQUEIO 3 — FASE 12 não foi cumprida

**Impacto: alto para o roadmap de produto.**

O prompt mestre determina, em maiúsculas: *"NÃO implemente toda a infraestrutura
baseada nessa fonte antes de medir seu volume real."*

O comando `medir_mapa_nas_nuvens` está escrito e dá um veredito objetivo. **Sem
rede, não rodou.** O volume real da API do GDF continua desconhecido.

O conector `mapa_nas_nuvens.py` foi escrito de forma defensiva (campo que não vem
é ignorado, evento sem data é descartado em vez de receber data inventada), mas
o formato de resposta do Mapas Culturais varia entre versões da plataforma. **O
parser pode precisar de ajuste no primeiro contato real com a API.**

```bash
python manage.py medir_mapa_nas_nuvens
```

Se o veredito for "volume insuficiente", a estratégia muda: priorize parceiros e
"colar link" antes de qualquer coisa.

---

## PENDÊNCIA 1 — Nenhum parceiro está ativo

**Impacto: médio. Deliberado.**

`eventos/ingestao/parceiros.py` mapeia 9 espaços do DF (Cine Brasília, Clube do
Choro, Teatro Nacional, CCBB, Caixa Cultural, Sesc-DF, Complexo Cultural de
Planaltina, Casa do Cantador, UnB) — **todos com `feed=None` e inativos.**

Preencher a URL sem falar com o parceiro é exatamente voltar a raspar, que é o
que esta fase existe para evitar. Preencha `feed` e marque `ativo=True` conforme
cada acordo for fechado.

---

## PENDÊNCIA 2 — O Selenium continua no repositório

**Impacto: baixo. Correto.**

O prompt mestre determina não remover antes de as fontes novas funcionarem. Como
a FASE 12 não pôde ser medida, remover agora esvaziaria o catálogo.

Está desligado por padrão (`SYMPLA_SCRAPING_ATIVO=False`). A régua:

```bash
python manage.py comparar_catalogo
```

Roteiro de remoção em 5 passos no README, seção "Desligamento do Selenium".

---

## PENDÊNCIA 3 — A SECRET_KEY antiga continua no histórico do Git

**Impacto: alto. Só você pode resolver.**

Trocar a chave no `.env` **não basta**. Enquanto ela estiver no histórico,
qualquer pessoa com acesso ao repositório forja cookie de sessão e token de
recuperação de senha.

```bash
python manage.py gerar_secret_key     # imprime a chave e o roteiro
```

Os 4 passos (trocar, derrubar sessões, `git filter-repo`, rotacionar SMTP/banco/
storage) estão no comando e no README. **Não dá para fazer isso a partir de uma
cópia extraída do zip** — precisa ser no seu repositório.

Se ele for público ou já tiver sido clonado por terceiros, considere-o queimado
e recrie.

---

## PENDÊNCIA 4 — Rate limiting depende do cache

**Impacto: médio em produção.**

`eventos/ratelimit.py` usa contador de janela fixa sobre o cache do Django. Com
`CACHE_BACKEND=locmem` (o padrão) e vários workers, **cada processo tem o
próprio contador** e o limite efetivo se multiplica pelo número de workers.

Em produção:

```bash
# opção sem dependência nova
CACHE_BACKEND=db
python manage.py createcachetable

# ou, com Redis disponível
CACHE_BACKEND=redis
REDIS_URL=redis://127.0.0.1:6379/1
```

Segunda limitação, menor: janela fixa, não deslizante. Em teoria dá para gastar
2× o limite na virada da janela. Aceitável para o que se está protegendo.

---

## PENDÊNCIA 5 — Coordenadas aproximadas

**Impacto: baixo.**

As 26 estações do Metrô-DF e os 26 centroides de RA em `constants.py` têm 4
casas decimais (~11 m) e vieram de fontes públicas. Servem para centralizar
mapa e calcular "perto do metrô". **Conferir antes de produção**, especialmente
as estações — um erro ali gera um selo "Metrô X, a 300 m" que não corresponde à
realidade.

---

## PENDÊNCIA 6 — Token da Sympla em texto no banco

**Impacto: médio se houver integrações reais.**

`IntegracaoSympla.token` é credencial de terceiro. Já está protegido no
aplicativo: nunca aparece em listagem, nunca entra na exportação LGPD, é
write-only no admin.

**Mas está em texto no banco.** Em produção, use criptografia em repouso
(pgcrypto ou disco criptografado). Documentado no docstring do modelo e no
README.

---

## NÃO IMPLEMENTADO POR DECISÃO

| Item | Por quê |
|---|---|
| **Pagamento** | O prompt mestre determina não implementar antes de a infraestrutura de reserva estar pronta. A cadeia reserva → capacidade → estoque existe; pedido, webhook, confirmação e reembolso não. |
| **Celery / Celery Beat** | Cron dá conta de três tarefas diárias. Subir broker e worker é infraestrutura que não se paga agora. A migração é uma linha quando o volume justificar. |
| **DRF** | O prompt proíbe adicionar "para modernizar". Nenhum endpoint atual precisa: `/mapa/dados/` é um `JsonResponse` de 20 linhas. |
| **PWA, app nativo, IA, avaliações** | Lista explícita de "o que não fazer agora" do prompt mestre (seção 35). |
| **Divisão em vários apps** | O prompt proíbe sem necessidade. `services/` e `ingestao/` resolveram a organização sem fragmentar o `INSTALLED_APPS`. |

---

## O QUE NÃO CONSEGUI VERIFICAR DE JEITO NENHUM

Coisas que só aparecem rodando, e que valem uma passada manual:

1. **Renderização de cada template.** A verificação estática confere tags,
   filtros e nomes de URL — não confere se uma variável de contexto existe.
   Se uma view não passar algo que o template usa, o Django renderiza vazio em
   silêncio.
2. **O mapa Leaflet no navegador.** O JS passou no `node --check`; a
   integração com a API do Leaflet e o carregamento do CDN não foram vistos.
3. **A migration 0008 com dados reais.** Ela foi escrita para ser segura e
   reversível, mas rodou zero vezes. **Faça backup do banco antes:**
   ```bash
   cp db.sqlite3 db.sqlite3.bak      # ou pg_dump
   python manage.py migrate
   ```
4. **Envio real de e-mail.** Os 8 templates renderizam variáveis que existem
   nos objetos passados, mas nenhum foi enviado.
5. **Responsividade e o modo escuro.** O CSS está balanceado; a aparência em
   telas reais, não conferida.
6. **A API do Mapa nas Nuvens.** Ver BLOQUEIO 3.

---

## ORDEM SUGERIDA PARA VOCÊ RETOMAR

```bash
# 1. instalar e conferir o básico
pip install -r requirements.txt
python manage.py check

# 2. o ponto de maior risco
python manage.py makemigrations --check --dry-run

# 3. os 217 testes
python manage.py test

# 4. backup antes de migrar dados de verdade
cp db.sqlite3 db.sqlite3.bak
python manage.py migrate

# 5. rotacionar a chave comprometida
python manage.py gerar_secret_key

# 6. medir a fonte antes de decidir o roadmap
python manage.py medir_mapa_nas_nuvens

# 7. preencher as coordenadas dos locais existentes
python manage.py geocodificar

# 8. gerar as variantes das capas antigas
python manage.py gerar_variantes_imagem

# 9. ver se já dá para desligar o Selenium
python manage.py comparar_catalogo
```

Se algum teste falhar, me mande a saída — corrijo em cima do erro real, que
vale muito mais do que qualquer verificação estática.
