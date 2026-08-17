#!/usr/bin/env python3
"""
mensurar — mede a qualidade do trabalho em progresso (WIP) contra padroes de mercado.

Escopo: SEMPRE o diff da branch atual contra a branch-base do projeto — nunca o repositorio
inteiro. Ver README.md nesta pasta para a documentacao completa (instalacao, configuracao e
como cada medicao funciona por dentro).

Uso:
  python3 mensurar_runner.py [--project PATH] [--base-branch BRANCH] [--config PATH]
                              [--mutation] [--e2e] [--all] [--json]
"""
import argparse
import csv
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV_DIR = os.path.join(SKILL_DIR, ".venv")

# Defaults genericos — todos sobrescrevíveis por mensurar.config.json na raiz do repo medido
# (ou por --base-branch / variavel de ambiente MENSURAR_BASE_BRANCH, no caso da branch-base).
# Ver README.md, secao "Configuracao".
DEFAULT_BASE_BRANCH = "main"
GENERIC_LOC_THRESHOLDS = {"warn": 400, "refactor": 1000}

# faixas de mercado — (limite_superior_inclusive, rotulo), a ultima faixa e o teto
COMPLEXITY_BANDS = [(10, "saudavel"), (20, "atencao"), (float("inf"), "critico")]
COVERAGE_BANDS = [(60, "critico"), (75, "atencao"), (90, "saudavel"), (float("inf"), "exemplar")]
MUTATION_BANDS = [(60, "critico"), (80, "atencao"), (float("inf"), "saudavel")]

CODE_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".py"}


def band(value, bands):
    for limit, label in bands:
        if value <= limit:
            return label
    return bands[-1][1]


def run(cmd, cwd=None, timeout=300):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout apos {timeout}s"
    except FileNotFoundError as e:
        return 127, "", str(e)


# ---------------------------------------------------------------------------
# Configuracao opcional (mensurar.config.json na raiz do projeto medido)
# ---------------------------------------------------------------------------

def load_config(root, explicit_path):
    """Le mensurar.config.json (opcional). Ausencia/erro de parse = config vazia, sem travar."""
    path = explicit_path or os.path.join(root, "mensurar.config.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        print(f"aviso: nao foi possivel ler {path} ({e}) — seguindo com defaults genericos.", file=sys.stderr)
        return {}


# ---------------------------------------------------------------------------
# Contexto: raiz do projeto, branch-base, arquivos tocados
# ---------------------------------------------------------------------------

def find_project_root(start):
    code, out, _ = run(["git", "rev-parse", "--show-toplevel"], cwd=start)
    return out.strip() if code == 0 else None


def detect_default_branch(root):
    """Tenta achar a branch-base sem precisar de config: HEAD remoto do origin -> main -> master."""
    code, out, _ = run(["git", "symbolic-ref", "refs/remotes/origin/HEAD"], cwd=root)
    if code == 0 and out.strip():
        return out.strip().rsplit("/", 1)[-1]
    for candidate in ("main", "master"):
        code, _, _ = run(["git", "rev-parse", "--verify", candidate], cwd=root)
        if code == 0:
            return candidate
    return DEFAULT_BASE_BRANCH


def base_branch_for(root, config, cli_override):
    # prioridade: --base-branch > env MENSURAR_BASE_BRANCH > config > auto-deteccao > default
    return (
        cli_override
        or os.environ.get("MENSURAR_BASE_BRANCH")
        or config.get("base_branch")
        or detect_default_branch(root)
    )


def current_branch(root):
    code, out, _ = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root)
    return out.strip() if code == 0 else None


def changed_files(root, base):
    files = set()
    code, out, _ = run(["git", "merge-base", base, "HEAD"], cwd=root)
    merge_base = out.strip() if code == 0 else base
    for args in (
        ["git", "diff", "--name-only", merge_base, "HEAD"],
        ["git", "diff", "--name-only"],
        ["git", "diff", "--name-only", "--cached"],
    ):
        code, out, _ = run(args, cwd=root)
        if code == 0:
            files.update(l for l in out.splitlines() if l.strip())
    return sorted(f for f in files if os.path.exists(os.path.join(root, f)))


def find_manifest(root, filepath):
    """Sobe diretorios a partir do arquivo ate achar package.json/pyproject.toml/requirements.txt."""
    d = os.path.dirname(os.path.join(root, filepath))
    while d and (d == root or d.startswith(root + os.sep)):
        if os.path.exists(os.path.join(d, "package.json")):
            return d, "node"
        if os.path.exists(os.path.join(d, "pyproject.toml")) or os.path.exists(os.path.join(d, "requirements.txt")):
            return d, "python"
        if d == root:
            break
        d = os.path.dirname(d)
    return None, None


def group_by_manifest(root, files):
    groups = {}
    for f in files:
        manifest, stack = find_manifest(root, f)
        if not manifest:
            continue
        groups.setdefault((manifest, stack), []).append(f)
    return groups


# ---------------------------------------------------------------------------
# Complexidade ciclomatica (lizard, venv dedicado da skill)
# ---------------------------------------------------------------------------

def ensure_lizard():
    """Devolve (caminho_do_lizard, None) ou (None, motivo_real_da_falha)."""
    binpath = os.path.join(VENV_DIR, "bin", "lizard")
    if os.path.exists(binpath):
        return binpath, None
    if shutil.which("lizard"):
        return "lizard", None
    code, out, err = run([sys.executable, "-m", "venv", VENV_DIR], timeout=60)
    if code != 0:
        return None, f"falha ao criar o venv em {VENV_DIR}: {(err or out).strip()[-300:]}"
    pip = os.path.join(VENV_DIR, "bin", "pip")
    code, out, err = run([pip, "install", "-q", "lizard"], timeout=120)
    if os.path.exists(binpath):
        return binpath, None
    return None, f"falha ao instalar lizard via `{pip} install lizard`: {(err or out).strip()[-300:]}"


def measure_complexity(root, files):
    code_files = [f for f in files if os.path.splitext(f)[1] in CODE_EXTENSIONS]
    if not code_files:
        return {"skipped": True, "motivo": "nenhum arquivo em ts/tsx/js/jsx/py no diff"}
    lizard_bin, erro = ensure_lizard()
    if not lizard_bin:
        return {"skipped": True, "motivo": f"lizard indisponivel — {erro}", "como_resolver": f"python3 -m venv {VENV_DIR} && {os.path.join(VENV_DIR, 'bin', 'pip')} install lizard"}
    abs_files = [os.path.join(root, f) for f in code_files]
    code, out, err = run([lizard_bin, "--csv"] + abs_files, timeout=120)
    rows = []
    for row in csv.reader(io.StringIO(out)):
        if len(row) < 8:
            continue
        try:
            nloc, ccn = int(float(row[0])), int(float(row[1]))
        except ValueError:
            continue
        rows.append({
            "arquivo": os.path.relpath(row[6], root) if row[6] else "?",
            "funcao": row[7],
            "nloc": nloc,
            "ccn": ccn,
            "veredito": band(ccn, COMPLEXITY_BANDS),
        })
    piores = sorted(rows, key=lambda r: -r["ccn"])[:10]
    criticos = [r for r in rows if r["veredito"] == "critico"]
    return {
        "funcoes_analisadas": len(rows),
        "criticos": len(criticos),
        "piores_10": piores,
        "fonte_padrao": "McCabe (NIST 500-235): 1-10 saudavel, 11-20 atencao, 21+ critico",
    }


# ---------------------------------------------------------------------------
# Dependencias (graphify affected — opcional, requer config + grafo pre-construido)
# ---------------------------------------------------------------------------

def measure_dependencies(root, files, config):
    if not shutil.which("graphify"):
        return {"skipped": True, "motivo": "CLI 'graphify' nao encontrada no PATH (medicao opcional — ver README, secao Dependencias)"}
    graph_map = config.get("dependency_graphs", {})
    if not graph_map:
        return {"skipped": True, "motivo": "nenhum grafo configurado em mensurar.config.json (chave dependency_graphs) — ver README"}
    resultados = []
    grafos_usados = set()
    consultados = 0
    for f in files:
        if consultados >= 15:
            break
        top = f.split("/", 1)[0]
        graph_path = graph_map.get(top)
        if not graph_path or not os.path.exists(graph_path):
            continue
        consultados += 1
        grafos_usados.add(graph_path)
        node = os.path.basename(f)
        code, out, err = run(["graphify", "affected", node, "--graph", graph_path, "--depth", "1"], timeout=30)
        if code != 0 or "No unique node match" in out or "No unique node match" in err:
            resultados.append({"arquivo": f, "afetados_diretos": None, "nota": "sem match unico no grafo"})
            continue
        afetados = [l for l in out.splitlines() if l.strip().startswith("-")]
        resultados.append({"arquivo": f, "afetados_diretos": len(afetados)})
    if not grafos_usados:
        return {"skipped": True, "motivo": "diff nao cobre nenhum diretorio presente em dependency_graphs"}
    return {"grafos": sorted(grafos_usados), "arquivos_consultados": resultados}


# ---------------------------------------------------------------------------
# Tamanho de modulo (wc -l nos arquivos tocados)
# ---------------------------------------------------------------------------

def measure_module_size(root, files, thresholds):
    itens = []
    for f in files:
        path = os.path.join(root, f)
        try:
            with open(path, "r", errors="ignore") as fh:
                loc = sum(1 for _ in fh)
        except OSError:
            continue
        if loc <= thresholds["warn"]:
            veredito = "saudavel"
        elif loc <= thresholds["refactor"]:
            veredito = "atencao"
        else:
            veredito = "critico"
        itens.append({"arquivo": f, "loc": loc, "veredito": veredito})
    itens.sort(key=lambda i: -i["loc"])
    return {
        "arquivos": itens,
        "fonte_padrao": (
            f"generico de mercado: warn {thresholds['warn']}/refactor {thresholds['refactor']} LOC "
            "(ajustavel via mensurar.config.json, chave loc_thresholds)"
        ),
    }


# ---------------------------------------------------------------------------
# Coverage + regressao (por manifest/stack)
# ---------------------------------------------------------------------------

def package_scripts(manifest_dir):
    pkg_path = os.path.join(manifest_dir, "package.json")
    try:
        with open(pkg_path) as fh:
            return json.load(fh).get("scripts", {})
    except (OSError, json.JSONDecodeError):
        return {}


def find_project_venv(manifest_dir):
    for name in (".venv", "venv", "env"):
        candidate = os.path.join(manifest_dir, name, "bin", "python")
        if os.path.exists(candidate):
            return os.path.join(manifest_dir, name)
    return None


def measure_node_group(manifest_dir, files, base_branch, want_coverage):
    scripts = package_scripts(manifest_dir)
    result = {"manifest": manifest_dir, "stack": "node"}

    test_script = "test:unit" if "test:unit" in scripts else ("test" if "test" in scripts else None)
    if not test_script:
        result["regressao"] = {"skipped": True, "motivo": "sem script de teste no package.json"}
    else:
        code, out, err = run(["npm", "run", test_script], cwd=manifest_dir, timeout=600)
        result["regressao"] = {"comando": f"npm run {test_script}", "passou": code == 0, "resumo": (out + err)[-1500:]}

    has_vitest = want_coverage and ("vitest" in json.dumps(scripts) or os.path.exists(os.path.join(manifest_dir, "vitest.config.ts")))
    if has_vitest:
        code, out, err = run(["npx", "vitest", "run", "--coverage", "--changed", base_branch], cwd=manifest_dir, timeout=600)
        m = re.search(r"All files\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)", out)
        if m:
            pct_lines = float(m.group(4))
            result["coverage"] = {
                "pct_stmts": float(m.group(1)), "pct_branch": float(m.group(2)),
                "pct_funcs": float(m.group(3)), "pct_lines": pct_lines,
                "veredito": band(pct_lines, COVERAGE_BANDS),
                "fonte_padrao": "Google Testing Blog: <60% critico, 60-75% atencao, 75-90% saudavel, >90% exemplar",
            }
        else:
            result["coverage"] = {"skipped": True, "motivo": "vitest rodou mas nao foi possivel parsear a tabela de coverage", "saida": (out + err)[-800:]}
    elif want_coverage:
        result["coverage"] = {"skipped": True, "motivo": "projeto sem vitest configurado"}

    return result


def measure_python_group(manifest_dir, files, want_coverage):
    result = {"manifest": manifest_dir, "stack": "python"}
    venv = find_project_venv(manifest_dir)
    if not venv:
        result["regressao"] = {"skipped": True, "motivo": "nenhum venv encontrado no projeto (.venv/venv/env) — crie um com as deps do projeto antes de usar esta skill aqui"}
        if want_coverage:
            result["coverage"] = {"skipped": True, "motivo": "mesma causa: sem venv do projeto"}
        return result

    py = os.path.join(venv, "bin", "python")
    pytest_bin = os.path.join(venv, "bin", "pytest")
    if not os.path.exists(pytest_bin):
        result["regressao"] = {"skipped": True, "motivo": "pytest nao instalado no venv do projeto"}
        return result

    if want_coverage:
        code, _, _ = run([py, "-c", "import pytest_cov"], cwd=manifest_dir, timeout=20)
        if code != 0:
            run([os.path.join(venv, "bin", "pip"), "install", "-q", "pytest-cov"], cwd=manifest_dir, timeout=120)
        code, out, err = run([pytest_bin, "--cov", "--cov-report=term"], cwd=manifest_dir, timeout=600)
        m = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", out)
        if m:
            pct = float(m.group(1))
            result["coverage"] = {"pct_lines": pct, "veredito": band(pct, COVERAGE_BANDS),
                                   "fonte_padrao": "Google Testing Blog: <60% critico, 60-75% atencao, 75-90% saudavel, >90% exemplar"}
        else:
            result["coverage"] = {"skipped": True, "motivo": "pytest-cov rodou mas nao foi possivel parsear TOTAL", "saida": (out + err)[-800:]}
        result["regressao"] = {"comando": "pytest --cov", "passou": code == 0, "resumo": (out + err)[-1500:]}
    else:
        code, out, err = run([pytest_bin], cwd=manifest_dir, timeout=600)
        result["regressao"] = {"comando": "pytest", "passou": code == 0, "resumo": (out + err)[-1500:]}

    return result


# ---------------------------------------------------------------------------
# Mutacao e E2E (opt-in via flag)
# ---------------------------------------------------------------------------

def measure_mutation(manifest_dir, stack, files):
    if stack == "node":
        has_config = any(os.path.exists(os.path.join(manifest_dir, c)) for c in ("stryker.conf.json", "stryker.conf.mjs", "stryker.config.mjs"))
        if not has_config:
            return {"skipped": True, "motivo": "Stryker nao configurado neste repo — rode `npx stryker init` uma vez (fora do escopo desta skill) antes de usar --mutation"}
        mutate_glob = "{" + ",".join(files) + "}"
        code, out, err = run(["npx", "stryker", "run", "--mutate", mutate_glob], cwd=manifest_dir, timeout=900)
        m = re.search(r"(\d+\.\d+)% mutation score", out)
        if m:
            pct = float(m.group(1))
            return {"mutation_score_pct": pct, "veredito": band(pct, MUTATION_BANDS),
                     "fonte_padrao": "defaults oficiais do Stryker: <60% critico, 60-80% atencao, >80% saudavel"}
        return {"skipped": True, "motivo": "Stryker rodou mas nao foi possivel parsear o score", "saida": (out + err)[-800:]}
    if stack == "python":
        venv = find_project_venv(manifest_dir)
        if not venv:
            return {"skipped": True, "motivo": "sem venv do projeto — mutmut precisa rodar dentro das deps reais do projeto"}
        return {"skipped": True, "motivo": "mutmut ainda nao implementado nesta skill para Python (v0) — pendencia conhecida"}
    return {"skipped": True, "motivo": f"stack {stack} sem suporte a mutacao ainda"}


def measure_e2e(manifest_dir):
    has_playwright = os.path.exists(os.path.join(manifest_dir, "playwright.config.ts"))
    if not has_playwright:
        return {"skipped": True, "motivo": "sem playwright.config.ts neste projeto"}
    print("atencao: --e2e vai rodar contra o ambiente configurado no playwright.config.ts (pode ser um ambiente real).", file=sys.stderr)
    code, out, err = run(["npx", "playwright", "test"], cwd=manifest_dir, timeout=900)
    return {"comando": "npx playwright test", "passou": code == 0, "resumo": (out + err)[-1500:]}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Mede a qualidade do trabalho em progresso (WIP) de uma branch/worktree contra faixas de mercado. Ver README.md.",
    )
    ap.add_argument("--project", default=os.getcwd(), help="raiz do repositorio a medir (default: diretorio atual)")
    ap.add_argument("--base-branch", default=None, help="branch-base pro diff (default: config > env MENSURAR_BASE_BRANCH > auto-deteccao > main)")
    ap.add_argument("--config", default=None, help="caminho pro mensurar.config.json (default: <raiz-do-projeto>/mensurar.config.json)")
    ap.add_argument("--mutation", action="store_true", help="inclui a medicao de mutacao (lenta)")
    ap.add_argument("--e2e", action="store_true", help="inclui a medicao de e2e (lenta, pode tocar ambiente real)")
    ap.add_argument("--all", action="store_true", help="equivalente a --mutation --e2e")
    ap.add_argument("--json", action="store_true", help="so imprime o JSON, sem resumo formatado")
    args = ap.parse_args()
    if args.all:
        args.mutation = args.e2e = True

    root = find_project_root(args.project)
    if not root:
        print("nao estou dentro de um repositorio git — esta skill precisa rodar dentro de um repo/worktree.")
        sys.exit(1)

    config = load_config(root, args.config)
    base = base_branch_for(root, config, args.base_branch)
    branch = current_branch(root)
    if branch == base:
        print(f"voce esta na propria branch-base ({base}) — sem branch de feature nao ha 'trabalho em progresso' pra medir.")
        print("   esta skill mede o diff de uma branch de feature/worktree contra a branch-base, nunca a branch-base contra ela mesma.")
        sys.exit(1)

    files = changed_files(root, base)
    report = {"projeto": root, "branch_base": base, "branch_atual": branch, "arquivos_tocados": len(files), "timestamp": int(time.time())}

    if not files:
        report["aviso"] = "diff vazio contra a branch-base — nada pra medir"
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    loc_thresholds = config.get("loc_thresholds", GENERIC_LOC_THRESHOLDS)

    report["complexidade"] = measure_complexity(root, files)
    report["dependencias"] = measure_dependencies(root, files, config)
    report["tamanho_modulo"] = measure_module_size(root, files, loc_thresholds)

    groups = group_by_manifest(root, files)
    report["por_projeto"] = []
    for (manifest_dir, stack), group_files in groups.items():
        if stack == "node":
            g = measure_node_group(manifest_dir, group_files, base, want_coverage=True)
            if args.mutation:
                g["mutacao"] = measure_mutation(manifest_dir, "node", group_files)
            if args.e2e:
                g["e2e"] = measure_e2e(manifest_dir)
        elif stack == "python":
            g = measure_python_group(manifest_dir, group_files, want_coverage=True)
            if args.mutation:
                g["mutacao"] = measure_mutation(manifest_dir, "python", group_files)
        else:
            continue
        report["por_projeto"].append(g)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    out_path = f"/tmp/mensurar-{os.path.basename(root)}-{report['timestamp']}.json"
    with open(out_path, "w") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    print_summary(report)
    print(f"\nRelatorio completo: {out_path}")


def emoji(veredito):
    return {"saudavel": "✅", "atencao": "⚠️", "critico": "🛑", "exemplar": "✅"}.get(veredito, "ℹ️")


def print_summary(report):
    print(f"📏 mensurar — {report['projeto']} ({report['arquivos_tocados']} arquivos tocados vs {report['branch_base']})\n")

    c = report["complexidade"]
    if c.get("skipped"):
        print(f"  Complexidade: pulado — {c['motivo']}")
    else:
        print(f"  Complexidade: {c['funcoes_analisadas']} funcoes, {c['criticos']} criticas — {c['fonte_padrao']}")
        for f in c["piores_10"][:3]:
            print(f"    {emoji(f['veredito'])} {f['funcao']} (CCN {f['ccn']}) — {f['arquivo']}")

    d = report["dependencias"]
    if d.get("skipped"):
        print(f"  Dependencias: pulado — {d['motivo']}")
    else:
        print(f"  Dependencias: {len(d['arquivos_consultados'])} arquivos consultados nos grafos ({', '.join(d['grafos'])})")

    t = report["tamanho_modulo"]
    print(f"  Tamanho de modulo: {t['fonte_padrao']}")
    for f in t["arquivos"][:3]:
        print(f"    {emoji(f['veredito'])} {f['arquivo']} — {f['loc']} LOC")

    for g in report["por_projeto"]:
        print(f"\n  Projeto: {g['manifest']} ({g['stack']})")
        r = g.get("regressao", {})
        if r.get("skipped"):
            print(f"    Regressao: pulado — {r['motivo']}")
        else:
            print(f"    Regressao: {'✅ passou' if r.get('passou') else '🛑 falhou'} ({r.get('comando')})")
        cov = g.get("coverage", {})
        if cov.get("skipped"):
            print(f"    Coverage: pulado — {cov['motivo']}")
        elif cov:
            print(f"    Coverage: {emoji(cov['veredito'])} {cov.get('pct_lines')}% linhas — {cov['fonte_padrao']}")
        if "mutacao" in g:
            m = g["mutacao"]
            if m.get("skipped"):
                print(f"    Mutacao: pulado — {m['motivo']}")
            else:
                print(f"    Mutacao: {emoji(m['veredito'])} {m.get('mutation_score_pct')}% — {m['fonte_padrao']}")
        if "e2e" in g:
            e = g["e2e"]
            if e.get("skipped"):
                print(f"    E2E: pulado — {e['motivo']}")
            else:
                print(f"    E2E: {'✅ passou' if e.get('passou') else '🛑 falhou'}")


if __name__ == "__main__":
    main()
