# mensurar

Skill do [Claude Code](https://claude.com/claude-code) que mede a qualidade do **trabalho em
progresso** (WIP) de uma branch de feature/worktree — nunca do repositório inteiro — e devolve um
veredito por medição contra faixas conhecidas de mercado, cada uma com fonte citada. Funciona
também como script Python standalone, fora do Claude Code, para qualquer repositório git.

Ela nunca inventa um número que não mediu: quando uma ferramenta não está disponível ou o projeto
não tem test runner configurado, a medição correspondente aparece como **pulada, com motivo
explícito** — nunca como um resultado silenciosamente ausente ou fingido.

Este pacote é autocontido e genérico: não depende de nenhuma infraestrutura, convenção de branch
ou ferramenta proprietária de uma empresa específica. Tudo que varia de projeto pra projeto
(branch-base, thresholds, grafos de dependência) é configurável — ver [Configuração](#configuração).

---

## Sumário

- [O que ela mede](#o-que-ela-mede)
- [Requisitos](#requisitos)
- [Instalação](#instalação)
- [Uso](#uso)
- [Configuração](#configuração)
- [Como cada medição funciona por dentro](#como-cada-medição-funciona-por-dentro)
- [Formato do relatório](#formato-do-relatório)
- [Casos especiais e mensagens de erro](#casos-especiais-e-mensagens-de-erro)
- [Limitações conhecidas](#limitações-conhecidas)
- [Troubleshooting](#troubleshooting)
- [Estrutura dos arquivos](#estrutura-dos-arquivos)

---

## O que ela mede

Sete medições, sempre restritas aos arquivos que aparecem no `git diff` da branch atual contra a
branch-base — nunca ao repositório inteiro:

| # | Medição | O que responde |
|---|---|---|
| 1 | Complexidade ciclomática | As funções que eu toquei estão fáceis de entender/testar, ou virou espaguete? |
| 2 | Coverage | Que fração do código tocado tem teste cobrindo? |
| 3 | Regressão | A suíte de testes existente ainda passa depois da minha mudança? |
| 4 | Mutação (opt-in) | Os testes existentes realmente pegam bug, ou só "tocam" o código sem afirmar nada? |
| 5 | E2E (opt-in) | O fluxo ponta-a-ponta que depende disso ainda funciona? |
| 6 | Dependências (opcional) | Se eu mexer aqui, o que mais no código pode quebrar? |
| 7 | Tamanho de módulo | Esse arquivo ainda está num tamanho saudável, ou já é hora de quebrar em pedaços? |

As 5 primeiras (exceto mutação) rodam por padrão. Mutação e E2E são **sempre opt-in** — precisam
da flag `--mutation` e/ou `--e2e` — porque são lentas e/ou podem tocar um ambiente real.

Cada medição usa uma régua pública, citada na saída:

- **Complexidade ciclomática** — McCabe / NIST Special Publication 500-235: 1–10 saudável,
  11–20 atenção, 21+ crítico.
- **Coverage** — [Google Testing Blog](https://testing.googleblog.com/), guia público sobre
  cobertura de código: <60% crítico, 60–75% atenção, 75–90% saudável, >90% exemplar.
- **Mutation score** — defaults oficiais do [Stryker](https://stryker-mutator.io/): <60% crítico,
  60–80% atenção, >80% saudável.
- **Tamanho de módulo** — sem norma única de mercado; esta skill usa 400 LOC (warn) / 1000 LOC
  (refactor) como default genérico, mas o valor é ajustável por projeto (ver Configuração).
- **Regressão e E2E** — pass/fail, sem faixa numérica.

---

## Requisitos

**Obrigatórios** (sem eles a skill não roda de forma útil):

- **Um ambiente POSIX** — Linux, macOS ou WSL. A skill monta caminhos de venv no formato POSIX
  (`venv/bin/python`, `venv/bin/pytest`) e grava o relatório em `/tmp`, nada disso existe no
  Windows nativo (lá seria `venv\Scripts\python.exe`). No Windows, rode dentro do WSL.
- `python3` 3.8 ou mais recente
- `git`, e o diretório onde você rodar precisa ser um repositório git com pelo menos duas branches
  (a atual e a branch-base)

**Opcionais** — cada um habilita só a medição correspondente; a ausência de qualquer um deles
faz *só aquela medição* ser pulada, com aviso, nunca trava as demais:

| Ferramenta | Habilita | Se ausente |
|---|---|---|
| `pip`/acesso à internet na primeira execução | Complexidade ciclomática (`lizard`) | pulada, com instrução de instalar manualmente |
| Node.js + `npm`/`npx` | Coverage e regressão JS/TS, mutação JS, E2E | puladas |
| Script `test` ou `test:unit` no `package.json` | Regressão JS/TS | pulada |
| `vitest` configurado no projeto | Coverage JS/TS | pulada |
| [Stryker](https://stryker-mutator.io/) configurado (`stryker.conf.*`) | Mutação JS/TS (`--mutation`) | pulada, com instrução `npx stryker init` |
| [Playwright](https://playwright.dev/) configurado (`playwright.config.ts`) | E2E (`--e2e`) | pulada |
| `venv` do projeto Python com `pytest` instalado | Coverage e regressão Python | puladas |
| CLI [`graphify`](https://github.com/Graphify-Labs/graphify) + um grafo pré-construído | Dependências afetadas | pulada (é a única medição desligada por padrão mesmo com a ferramenta presente, até você configurar) |

Nenhuma dessas ferramentas opcionais vem dentro deste pacote — a skill só as invoca se já
estiverem disponíveis no ambiente ou no projeto que você está medindo.

---

## Instalação

1. **Descompacte** o zip onde preferir.
2. **Instale** a pasta `mensurar/` num dos diretórios de skills do Claude Code:
   - Escopo de usuário (disponível em qualquer projeto que você abrir):
     ```bash
     ./mensurar/install.sh
     # copia para ~/.claude/skills/mensurar
     ```
   - Escopo de um projeto específico (só quem abrir o Claude Code dentro desse repositório vê a skill):
     ```bash
     cd /caminho/do/seu/repositorio
     /caminho/do/zip/descompactado/mensurar/install.sh --project
     # copia para ./.claude/skills/mensurar
     ```
   - Ou copie manualmente, sem o script: `cp -r mensurar ~/.claude/skills/mensurar` (ou para
     `.claude/skills/mensurar` dentro do repositório).
3. **Reabra ou recarregue** o Claude Code. A skill aparece como `/mensurar` na lista de skills
   disponíveis.
4. **Primeiro uso**: na primeira vez que a medição de complexidade ciclomática rodar, a skill cria
   sozinha um ambiente virtual Python interno (`mensurar/.venv`, dentro da própria pasta da skill,
   nunca dentro do seu projeto) e instala o pacote `lizard` nele — precisa de acesso à internet/pip
   nesse momento. Isso acontece uma única vez; execuções seguintes reaproveitam o mesmo venv.

Também funciona sem o Claude Code, como script solto:

```bash
python3 /caminho/onde/instalou/mensurar/lib/mensurar_runner.py --help
```

### Desinstalação

Apague a pasta onde copiou (`~/.claude/skills/mensurar` ou `<repo>/.claude/skills/mensurar`). Não
há nenhum outro arquivo, registro ou processo instalado fora dessa pasta.

---

## Uso

Rode de dentro do diretório do repositório/worktree que você quer medir — a skill detecta a raiz
do git automaticamente a partir do diretório atual (ou de `--project`).

```bash
python3 lib/mensurar_runner.py                        # 5 medições rápidas (default)
python3 lib/mensurar_runner.py --mutation              # + mutação (lento)
python3 lib/mensurar_runner.py --e2e                   # + e2e (lento, pode tocar ambiente real)
python3 lib/mensurar_runner.py --all                    # tudo (--mutation --e2e)
python3 lib/mensurar_runner.py --json                   # só o relatório JSON, sem resumo formatado
python3 lib/mensurar_runner.py --project /outro/repo    # mede outro repositório, não o atual
python3 lib/mensurar_runner.py --base-branch develop    # força a branch-base do diff
python3 lib/mensurar_runner.py --config ./ci/mensurar.json  # usa um config em outro caminho
```

No Claude Code, basta chamar `/mensurar` na conversa — a skill invoca o mesmo script por trás.

| Flag | Efeito |
|---|---|
| `--project PATH` | raiz do repositório a medir (default: diretório atual) |
| `--base-branch BRANCH` | branch-base do diff (default: ver [Configuração](#configuração)) |
| `--config PATH` | caminho explícito pro `mensurar.config.json` (default: na raiz do projeto medido) |
| `--mutation` | inclui a medição de mutação (lenta) |
| `--e2e` | inclui a medição de e2e (lenta, pode tocar um ambiente real — a skill avisa antes de rodar) |
| `--all` | equivalente a `--mutation --e2e` |
| `--json` | imprime só o relatório em JSON, sem o resumo formatado no terminal |

---

## Configuração

Tudo que varia de projeto pra projeto tem um default genérico funcional, mas pode ser ajustado por
um arquivo opcional `mensurar.config.json` **na raiz do repositório que você está medindo** (não
na pasta da skill). Se o arquivo não existir, a skill segue com os defaults abaixo sem reclamar.

```json
{
  "base_branch": "develop",
  "loc_thresholds": {
    "warn": 500,
    "refactor": 1200
  },
  "dependency_graphs": {
    "src": "/caminho/absoluto/para/graph.json",
    "backend": "/outro/caminho/absoluto/para/graph.json"
  }
}
```

Um exemplo comentado equivalente está em [`mensurar.config.example.json`](mensurar.config.example.json).

### `base_branch`

Contra qual branch comparar o diff (a "branch-base" do projeto — normalmente `main`, `master` ou
`develop`). Ordem de prioridade, do mais específico ao mais genérico:

1. Flag `--base-branch` na chamada
2. Variável de ambiente `MENSURAR_BASE_BRANCH`
3. Chave `base_branch` no `mensurar.config.json`
4. Auto-detecção: HEAD remoto do `origin` (`git symbolic-ref refs/remotes/origin/HEAD`) → branch
   local `main` → branch local `master` → `"main"` como último recurso

Na prática, se o seu repositório segue a convenção comum (branch padrão no remoto `origin`), você
não precisa configurar nada — a auto-detecção resolve.

### `loc_thresholds`

Limites de LOC (linhas de código) usados no veredito de **tamanho de módulo**. Default genérico:
`{"warn": 400, "refactor": 1000}` — abaixo de 400 linhas é "saudável", entre 400 e 1000 é
"atenção", acima de 1000 é "crítico". Ajuste para os padrões do seu próprio time/linguagem.

### `dependency_graphs` (opcional)

Mapa `"<diretório de topo do repositório>": "<caminho absoluto para um graph.json>"`. Só tem
efeito se a CLI [`graphify`](https://github.com/Graphify-Labs/graphify) (ferramenta de código
aberto para gerar grafos de dependência de código a partir de AST) estiver instalada no PATH **e**
você já tiver gerado o grafo daquele diretório com `graphify update <dir>`. A skill não gera o
grafo por você — só consulta um que já existe.

Sem essa configuração (ou sem a CLI instalada), a medição de dependências é simplesmente pulada
com aviso — nenhuma das outras 6 medições depende dela.

---

## Como cada medição funciona por dentro

### 1. Complexidade ciclomática

- Roda `lizard --csv <arquivos tocados em .ts/.tsx/.js/.jsx/.py>`.
- `lizard` é instalado automaticamente num venv Python dedicado dentro da própria pasta da skill
  (`mensurar/.venv`) na primeira execução — nunca no seu projeto, nunca globalmente.
- Parseia o CSV de saída (NLOC e CCN por função), classifica cada função contra as faixas de McCabe
  e reporta as 10 funções com maior complexidade + a contagem de funções "críticas" (CCN ≥ 21).
- Se nenhum arquivo tocado for de uma extensão suportada, ou se `lizard` não puder ser instalado
  (sem internet/pip na primeira vez), a medição é pulada com o motivo.

### 2. Coverage

- **Node/TS/JS**: se o `package.json` do diretório-manifesto tiver `vitest` nas dependências/scripts
  ou existir `vitest.config.ts`, roda `npx vitest run --coverage --changed <branch-base>` e faz
  parse da linha "All files" da tabela de saída padrão do Vitest.
- **Python**: só roda se o projeto já tiver um venv próprio (`.venv`, `venv` ou `env` na raiz do
  manifesto, com `pytest` instalado) — a skill nunca cria ou instala dependências de teste fora de
  um venv que já existe no projeto medido. Instala `pytest-cov` nesse venv se faltar, roda
  `pytest --cov --cov-report=term` e faz parse da linha `TOTAL`.
- Cada stack usa a mesma régua (Google Testing Blog).

### 3. Regressão

- **Node**: roda o script `test:unit` (se existir) ou `test` do `package.json`, com `npm run`.
- **Python**: roda `pytest` (ou `pytest --cov` quando coverage também for medida) dentro do venv
  do próprio projeto.
- Resultado é só pass/fail (código de saída do processo), com as últimas ~1500 linhas de saída
  guardadas no relatório JSON para diagnóstico.

### 4. Mutação (`--mutation`, opt-in)

- **Node**: exige um dos arquivos de config do Stryker (`stryker.conf.json`, `stryker.conf.mjs`,
  `stryker.config.mjs`) já existir no projeto. Se existir, roda
  `npx stryker run --mutate {arquivo1,arquivo2,...}` restrito aos arquivos tocados, e faz parse do
  "X% mutation score" da saída. Se não existir configuração, a skill **não tenta criar uma** — só
  instrui `npx stryker init` como passo manual, fora do escopo dela.
- **Python**: reservado para `mutmut`; **ainda não implementado nesta versão** (pendência
  conhecida) — sempre pulado com esse motivo.

### 5. E2E (`--e2e`, opt-in)

- Só roda se existir `playwright.config.ts` no diretório-manifesto. Roda `npx playwright test` e
  reporta pass/fail. Antes de rodar, imprime um aviso explícito de que a suíte pode apontar para um
  ambiente real (a configuração de para onde o Playwright aponta é do próprio projeto, não desta
  skill) — por isso o flag é sempre opt-in, nunca default.

### 6. Dependências (opcional, ver [Configuração](#dependency_graphs-opcional))

- Requer a CLI `graphify` no PATH **e** `dependency_graphs` configurado apontando para grafos já
  gerados.
- Para cada arquivo tocado (limite de 15 por chamada, por performance — o restante do diff fica
  sinalizado, não descartado silenciosamente), roda
  `graphify affected <nome-do-arquivo> --graph <graph.json> --depth 1` e conta quantos nós
  aparecem como afetados diretos.
- Sem match único no grafo (ex.: nome de arquivo ambíguo), o item entra no relatório com
  `afetados_diretos: null` e uma nota, em vez de ser descartado.

### 7. Tamanho de módulo

- `wc -l`-equivalente (contagem de linhas em Python) em cada arquivo tocado, classificado contra
  `loc_thresholds` (configurável — ver [Configuração](#loc_thresholds)).

---

## Formato do relatório

Toda execução sem `--json` grava o relatório completo em
`/tmp/mensurar-<nome-do-repo>-<timestamp-unix>.json` e imprime um resumo no terminal. Com `--json`,
o mesmo objeto vai direto para stdout, sem o resumo.

Estrutura de alto nível do JSON:

```jsonc
{
  "projeto": "/caminho/absoluto/do/repo",
  "branch_base": "main",
  "branch_atual": "minha-feature",
  "arquivos_tocados": 7,
  "timestamp": 1755000000,
  "complexidade": { /* ver seção 1 acima */ },
  "dependencias": { /* ver seção 6 acima */ },
  "tamanho_modulo": { /* ver seção 7 acima */ },
  "por_projeto": [
    {
      "manifest": "/caminho/do/subprojeto",
      "stack": "node",
      "regressao": { "comando": "npm run test:unit", "passou": true, "resumo": "..." },
      "coverage": { "pct_lines": 82.3, "veredito": "saudavel", "fonte_padrao": "..." },
      "mutacao": { "...": "só presente com --mutation" },
      "e2e": { "...": "só presente com --e2e" }
    }
  ]
}
```

Qualquer medição pulada aparece como `{"skipped": true, "motivo": "..."}` no lugar do objeto de
resultado — nunca omitida silenciosamente nem com um valor inventado.

---

## Casos especiais e mensagens de erro

| Situação | Comportamento |
|---|---|
| Diretório atual não é um repositório git | Aborta com mensagem clara, código de saída 1 |
| Você está na própria branch-base (ex.: rodou em `main`) | Aborta — o escopo é sempre "trabalho em progresso" comparado a uma base; medir a base contra ela mesma não tem sentido |
| Diff vazio contra a branch-base | Aborta com aviso "nada pra medir" — nunca gera um relatório vazio como se fosse "tudo ok" |
| Projeto sem test runner configurado | Coverage/regressão daquele stack pulados com aviso, resto do relatório segue normalmente |
| Projeto Python sem venv próprio | Coverage/regressão/mutação Python pulados, com instrução de criar o venv primeiro |
| `--mutation` sem Stryker configurado | Pulado, com instrução de rodar `npx stryker init` manualmente |
| `--e2e` sem Playwright configurado | Pulado |
| `graphify` ausente ou sem `dependency_graphs` configurado | Medição de dependências pulada; as outras 6 seguem normalmente |

---

## Limitações conhecidas

- **Windows nativo não é suportado** — os caminhos de venv (`venv/bin/…`) e o destino do relatório
  (`/tmp`) são POSIX. Use WSL, Linux ou macOS.
- **Mutação Python (`mutmut`)** ainda não está implementada nesta versão (v0.1.0) — sempre
  reportada como pulada. Fica registrado como pendência conhecida, não como bug.
- **`--e2e`** só tem efeito real em projetos com Playwright já configurado; não há suporte a outros
  frameworks de e2e nesta versão.
- **Consulta de dependências** limita a 15 arquivos por chamada (custo de performance); o restante
  do diff aparece sinalizado no relatório, não é descartado sem aviso.
- **Não autoconfigura** Stryker, mutmut, Vitest, Playwright ou grafos de dependência — a skill só
  usa o que já estiver configurado no projeto medido. Configurar essas ferramentas é decisão de
  cada projeto, fora do escopo desta skill.
- **Não roda em mais de um repositório por chamada** — o escopo é sempre o trabalho em progresso
  do repositório apontado por `--project` (ou o diretório atual).

---

## Troubleshooting

**"lizard indisponivel — falha ao criar o venv…" / "…falha ao instalar lizard via pip…"** — a
primeira execução tenta criar um venv e instalar `lizard` via pip; se o ambiente não tem acesso à
internet nesse momento, isso falha. A mensagem traz o erro real do `venv`/`pip` (últimos 300
caracteres) e o campo `como_resolver` no relatório repete o comando manual:

```bash
python3 -m venv mensurar/.venv
mensurar/.venv/bin/pip install lizard
```

(ajuste `mensurar/` para o caminho onde você instalou a skill).

**"CLI 'graphify' nao encontrada no PATH"** — normal e esperado se você não usa essa ferramenta;
a medição de dependências é opcional e todas as outras seis continuam funcionando. Para habilitá-la,
instale a CLI a partir de [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify),
gere um grafo do seu código com `graphify update <diretório>` e aponte para o `graph.json` gerado
em `dependency_graphs` no `mensurar.config.json`.

**"nao estou dentro de um repositorio git"** — rode o comando de dentro de um clone/worktree git
válido, ou passe `--project /caminho/do/repo`.

**"voce esta na propria branch-base"** — crie ou troque para uma branch de feature antes de rodar;
o propósito da skill é medir trabalho em progresso, não o estado da branch-base.

**Coverage/regressão sempre pulados no seu projeto Node** — confirme que o `package.json` tem um
script `test` ou `test:unit`, e que o Vitest está configurado (`vitest.config.ts` ou nas
dependências) se você quer a medição de coverage.

**Coverage/regressão sempre pulados no seu projeto Python** — a skill exige um venv já existente
na raiz do manifesto (`.venv`, `venv` ou `env`) com `pytest` instalado. Crie um antes de rodar.

---

## Estrutura dos arquivos

```
mensurar/
├── SKILL.md                        # definição da skill para o Claude Code (curta, operacional)
├── README.md                       # este arquivo — documentação completa
├── mensurar.config.example.json    # exemplo de configuração opcional
├── install.sh                      # instalador de conveniência (copia a pasta pro lugar certo)
└── lib/
    └── mensurar_runner.py           # implementação — único script, só biblioteca padrão do Python
```

Não há dependências externas empacotadas dentro do zip: o único pacote de terceiros que a skill
usa (`lizard`) é instalado sozinho, num venv isolado, na primeira execução.

---

**Versão**: v0.1.0 (empacotamento standalone).
