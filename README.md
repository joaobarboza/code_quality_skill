<div align="center">

# 📏 mensurar

**Skill de qualidade de código para o [Claude Code](https://claude.com/claude-code)**

Mede a qualidade do *trabalho em progresso* — o diff da sua branch contra a branch-base —
e devolve um veredito por medição contra faixas públicas de mercado, com a fonte citada.

[![Licença: MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Plataforma: Linux · macOS · WSL](https://img.shields.io/badge/plataforma-Linux%20%C2%B7%20macOS%20%C2%B7%20WSL-lightgrey.svg)](#-requisitos-e-plataformas)
[![Claude Code Skill](https://img.shields.io/badge/Claude%20Code-skill-D97757.svg)](https://claude.com/claude-code)

</div>

---

## 💡 A ideia

A metodologia é a do **Uncle Bob** (Robert C. Martin), em *Clean Code* e *The Clean Coder*:
funções pequenas e fáceis de raciocinar, módulos que cabem na cabeça, testes que de fato afirmam
alguma coisa, e a **Boy Scout Rule** — deixe o código melhor do que você o encontrou.

O problema é que princípio não é número. A `mensurar` fecha essa lacuna: pega cada princípio e
mede ele no código que você **acabou de escrever**, usando réguas públicas e citáveis (McCabe,
Google Testing Blog, defaults do Stryker) em vez de opinião.

Três decisões de design que valem entender antes de instalar:

- **Escopo é sempre o WIP.** Só os arquivos do `git diff` da sua branch contra a base — nunca o
  repositório inteiro. Você mede o que fez, não a dívida herdada dos outros.
- **Ela nunca inventa um número.** Se a ferramenta não está instalada ou o projeto não tem test
  runner, a medição aparece como **pulada, com o motivo explícito** — jamais como um resultado
  silenciosamente ausente ou fingido.
- **Nada de surpresa cara.** Mutação e E2E são sempre opt-in, porque são lentos e podem tocar
  ambiente real.

---

## 📊 O que ela mede

| # | Medição | A pergunta que responde | Régua (fonte) |
|:-:|---|---|---|
| 1 | **Complexidade ciclomática** | As funções que toquei ainda são fáceis de entender e testar? | McCabe / [NIST SP 500-235](https://www.nist.gov/publications/structured-testing-testing-methodology-using-cyclomatic-complexity-metric) — 1–10 saudável · 11–20 atenção · 21+ crítico |
| 2 | **Coverage** | Que fração do código tocado tem teste cobrindo? | [Google Testing Blog](https://testing.googleblog.com/) — <60% crítico · 60–75% atenção · 75–90% saudável · >90% exemplar |
| 3 | **Regressão** | A suíte existente ainda passa depois da minha mudança? | pass/fail |
| 4 | **Mutação** `--mutation` | Os testes pegam bug de verdade, ou só "tocam" o código? | defaults do [Stryker](https://stryker-mutator.io/) — <60% crítico · 60–80% atenção · >80% saudável |
| 5 | **E2E** `--e2e` | O fluxo ponta-a-ponta ainda funciona? | pass/fail ([Playwright](https://playwright.dev/)) |
| 6 | **Dependências** *(opcional)* | Se eu mexer aqui, o que mais pode quebrar? | nº de nós afetados a profundidade 1 ([graphify](https://github.com/Graphify-Labs/graphify)) |
| 7 | **Tamanho de módulo** | Esse arquivo ainda cabe na cabeça, ou já é hora de quebrar? | limite configurável — 400 LOC (warn) / 1000 LOC (refactor) |

---

## 🖥️ Como fica na prática

```text
📏 mensurar — /home/dev/meu-projeto (7 arquivos tocados vs main)

  Complexidade: 42 funcoes, 1 criticas — McCabe (NIST 500-235): 1-10 saudavel, 11-20 atencao, 21+ critico
    🛑 processarPedido (CCN 24) — src/pedidos/processar.ts
    ⚠️ validarPayload (CCN 13) — src/pedidos/validar.ts
    ✅ formatarTotal (CCN 4) — src/pedidos/formatar.ts
  Dependencias: pulado — CLI 'graphify' nao encontrada no PATH (medicao opcional — ver README, secao Dependencias)
  Tamanho de modulo: generico de mercado: warn 400/refactor 1000 LOC (ajustavel via mensurar.config.json, chave loc_thresholds)
    ⚠️ src/pedidos/processar.ts — 612 LOC
    ✅ src/pedidos/validar.ts — 188 LOC

  Projeto: /home/dev/meu-projeto (node)
    Regressao: ✅ passou (npm run test:unit)
    Coverage: ⚠️ 71.4% linhas — Google Testing Blog: <60% critico, 60-75% atencao, 75-90% saudavel, >90% exemplar

Relatorio completo: /tmp/mensurar-meu-projeto-1755000000.json
```

Repare no `Dependencias: pulado — …`: a ferramenta não estava lá, e a skill **disse isso** em vez
de omitir a linha. É essa a garantia.

---

## 🚀 Instalação

```bash
git clone https://github.com/joaobarboza/code_quality_skill.git
./code_quality_skill/mensurar/install.sh
```

Isso instala em `~/.claude/skills/mensurar` (escopo de usuário — disponível em qualquer projeto).
Para instalar só num repositório específico:

```bash
cd /caminho/do/seu/repositorio
/caminho/do/clone/mensurar/install.sh --project   # → ./.claude/skills/mensurar
```

Recarregue o Claude Code e chame **`/mensurar`** na conversa.

> **Primeira execução:** a medição de complexidade cria sozinha um venv interno
> (`mensurar/.venv`, dentro da própria pasta da skill — nunca no seu projeto) e instala o
> `lizard` nele. Precisa de acesso a pip/internet **uma única vez**.

**Desinstalar:** apague a pasta. Não há nenhum outro arquivo, registro ou processo fora dela.

---

## ⚙️ Uso

Funciona dentro do Claude Code (`/mensurar`) ou como script solto, em qualquer repositório git:

```bash
python3 mensurar/lib/mensurar_runner.py                  # as 5 medições rápidas (default)
python3 mensurar/lib/mensurar_runner.py --mutation       # + mutação (lento)
python3 mensurar/lib/mensurar_runner.py --e2e            # + e2e (pode tocar ambiente real)
python3 mensurar/lib/mensurar_runner.py --all            # tudo
```

| Flag | Efeito |
|---|---|
| `--project PATH` | raiz do repositório a medir (default: diretório atual) |
| `--base-branch BRANCH` | branch-base do diff (default: auto-detectada do `origin`) |
| `--config PATH` | caminho explícito pro `mensurar.config.json` |
| `--mutation` | inclui a medição de mutação (lenta) |
| `--e2e` | inclui a medição de e2e (lenta, avisa antes de rodar) |
| `--all` | equivalente a `--mutation --e2e` |
| `--json` | só o relatório JSON, sem o resumo formatado |

**Configuração é opcional.** Sem nenhum arquivo de config, a branch-base é auto-detectada do
`origin` e os thresholds usam os defaults genéricos. Para ajustar, crie um `mensurar.config.json`
na raiz do repositório medido — modelo em
[`mensurar/mensurar.config.example.json`](mensurar/mensurar.config.example.json), explicação em
[`mensurar/README.md`](mensurar/README.md#configuração).

---

## 🖥️ Requisitos e plataformas

> [!IMPORTANT]
> **Windows nativo não é suportado.** A skill monta caminhos de venv no formato POSIX
> (`venv/bin/python`, `venv/bin/pytest`) e grava o relatório em `/tmp` — nada disso existe no
> Windows, onde seria `venv\Scripts\python.exe`. **No Windows, rode dentro do WSL.**
> Linux e macOS funcionam direto.

**Obrigatório:** `python3` 3.8+ · `git` · um repositório git com uma branch de feature.

**Opcional** — cada item habilita *só* a medição correspondente; a ausência de qualquer um deles
nunca trava as outras:

| Ferramenta | Habilita |
|---|---|
| pip/internet na 1ª execução | complexidade ciclomática (`lizard`) |
| Node.js + `npm`/`npx` | coverage, regressão, mutação e e2e JS/TS |
| `vitest` configurado | coverage JS/TS |
| [Stryker](https://stryker-mutator.io/) configurado | mutação JS/TS |
| [Playwright](https://playwright.dev/) configurado | e2e |
| venv do projeto com `pytest` | coverage e regressão Python |
| [graphify](https://github.com/Graphify-Labs/graphify) + grafo pronto | dependências afetadas |

Nenhuma delas vem empacotada aqui — a skill só invoca o que já existe no seu ambiente.

---

## 📚 Documentação

| Arquivo | O que tem dentro |
|---|---|
| [`mensurar/README.md`](mensurar/README.md) | documentação completa: como cada medição funciona por dentro, configuração, formato do relatório, casos especiais, limitações e troubleshooting |
| [`mensurar/SKILL.md`](mensurar/SKILL.md) | a definição da skill lida pelo Claude Code |
| [`mensurar/lib/mensurar_runner.py`](mensurar/lib/mensurar_runner.py) | a implementação inteira — um script só, biblioteca padrão do Python, zero dependências empacotadas |

---

## 👤 Autor

Desenvolvido por **João Pedro Barboza** — **@_joaoplbarboza**

Baseado na metodologia do **Uncle Bob** (Robert C. Martin) para manutenção de qualidade de código,
com as faixas numéricas ancoradas em fontes públicas (McCabe/NIST, Google Testing Blog, Stryker).

## 📄 Licença

[MIT](LICENSE) — use, modifique e distribua à vontade.
