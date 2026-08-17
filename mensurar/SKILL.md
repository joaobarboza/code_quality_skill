---
name: mensurar
description: >
  Use quando precisar medir a qualidade do trabalho em progresso (WIP) de uma branch/worktree —
  coverage, testes de mutação, regressão, e2e, dependências afetadas, tamanho de módulo e
  complexidade ciclomática — com veredito contra faixas de mercado (McCabe, Google Testing Blog,
  defaults do Stryker). Gatilhos — "mede a qualidade disso", "cobertura tá boa?", "complexidade
  desse módulo", "roda os testes e mede", antes de abrir PR.
user-invocable: true
allowed-tools:
  - Bash
  - Read
---

# /mensurar — medição de qualidade do trabalho em progresso

**Propósito**: rodar 7 medições de qualidade — coverage, mutação, regressão, e2e, dependências,
tamanho de módulo, complexidade ciclomática — só nos arquivos tocados no diff atual, e comparar
cada número contra faixas conhecidas de mercado (com fonte citada). Ver [README.md](README.md)
para a documentação completa: instalação, configuração e como cada medição funciona por dentro.

**Escopo**: SEMPRE o trabalho em progresso — `git diff` da branch atual contra a branch-base do
projeto. Nunca varre o repositório inteiro. Se você estiver na própria branch-base (sem branch de
feature), a skill recusa rodar — não há "progresso" pra medir.

## Quando chamar

- Antes de abrir PR, pra saber se o que você fez está dentro do padrão.
- Quando pedirem "mede a qualidade disso", "cobertura tá boa?", "complexidade desse módulo".
- Como uma etapa do seu próprio pipeline de qualidade, se você tiver um.

## Uso

```bash
python3 lib/mensurar_runner.py                  # 5 medições rápidas (default)
python3 lib/mensurar_runner.py --mutation        # + mutação (lento)
python3 lib/mensurar_runner.py --e2e             # + e2e (lento, pode tocar ambiente real)
python3 lib/mensurar_runner.py --all             # tudo
python3 lib/mensurar_runner.py --json            # só o relatório JSON, sem resumo
python3 lib/mensurar_runner.py --base-branch develop
python3 lib/mensurar_runner.py --project /caminho/do/repo
```

Roda de dentro do diretório do repositório/worktree que você quer medir (`--project PATH` pra
apontar outro). Configuração opcional (branch-base, thresholds, grafos de dependência) via
`mensurar.config.json` na raiz do projeto medido — ver [README.md](README.md#configuração).

**Mutação e E2E são sempre opt-in** — nunca rodam por padrão, porque são lentos e/ou tocam
ambiente vivo.

## As 7 medições (resumo — detalhe completo no README)

| Medição | Ferramenta | Régua (fonte) |
|---|---|---|
| Complexidade ciclomática | `lizard` (venv própria da skill, cobre TS/JS/Python) | McCabe/NIST 500-235: 1-10 saudável · 11-20 atenção · 21+ crítico |
| Coverage | `vitest --coverage --changed` (Node) / `pytest-cov` (Python, se o projeto já tiver venv) | Google Testing Blog: <60% crítico · 60-75% atenção · 75-90% saudável · >90% exemplar |
| Mutação (`--mutation`) | Stryker (Node) / mutmut (Python, ainda não implementado) | defaults oficiais do Stryker: <60% crítico · 60-80% atenção · >80% saudável |
| Regressão | suíte de testes existente do projeto | pass/fail, sem margem numérica |
| E2E (`--e2e`) | Playwright, se configurado no projeto | pass/fail, sem margem numérica |
| Dependências | `graphify affected <arquivo>` num grafo pré-construído (opcional, ver README) | nº de nós afetados em profundidade 1 |
| Tamanho de módulo | `wc -l` nos arquivos tocados | genérico de mercado: warn 400 / refactor 1000 LOC (ajustável) |

## Reportar

Resumo formatado no chat + relatório completo em `/tmp/mensurar-<repo>-<timestamp>.json`. Emoji
por veredito: ✅ saudável/exemplar · ⚠️ atenção · 🛑 crítico. Qualquer medição que não pôde rodar
(ferramenta ausente, projeto sem test runner configurado, sem venv) aparece como **pulada com
motivo explícito** — nunca finge um resultado que não mediu de verdade.

## Casos especiais

- **Diff vazio**: aborta com aviso, não gera relatório vazio como se fosse "tudo ok".
- **Na própria branch-base**: aborta — rodar fora de uma branch de feature não faz sentido.
- **Sem test runner configurado**: pula coverage/regressão com aviso, não trava a skill.
- **Python sem venv no projeto**: pula coverage/regressão/mutação Python com instrução de criar
  o venv primeiro — a skill nunca instala dependências de teste soltas fora de um venv do projeto.
- **Mutação sem Stryker configurado**: reporta a ausência e instrui `npx stryker init` como passo
  manual — a skill não inventa config de mutação por você.

## Limitações conhecidas (v0.1.0)

- `mutmut` (mutação Python) ainda não está implementado nesta versão — pendência conhecida.
- `--e2e` só tem efeito se o projeto tiver Playwright configurado (`playwright.config.ts`).
- Consulta de dependências limita a 15 arquivos por chamada (performance) — o resto do diff é
  sinalizado, não descartado silenciosamente.
- Medição de dependências é opcional e exige a ferramenta externa `graphify` (não incluída) +
  um grafo pré-construído — ver [README.md](README.md#dependências-opcional).
