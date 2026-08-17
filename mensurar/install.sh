#!/usr/bin/env bash
# Instala a skill "mensurar" para o Claude Code.
#
# Uso:
#   ./install.sh              instala para o usuario atual (~/.claude/skills/mensurar)
#   ./install.sh --project    instala so para o repositorio atual (./.claude/skills/mensurar)
#
# Depois de instalar, reabra (ou recarregue) o Claude Code dentro de um repositorio git
# e chame /mensurar. Ver README.md para configuracao opcional e detalhes de funcionamento.
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" == "--project" ]]; then
  DEST_ROOT="$(pwd)/.claude/skills"
else
  DEST_ROOT="$HOME/.claude/skills"
fi
DEST="$DEST_ROOT/mensurar"

if [[ -e "$DEST" ]]; then
  echo "Já existe algo em '$DEST' — remova ou faça backup antes de reinstalar." >&2
  exit 1
fi

mkdir -p "$DEST_ROOT"
cp -r "$SRC_DIR" "$DEST"
rm -f "$DEST/install.sh"

echo "Instalado em: $DEST"

command -v python3 >/dev/null 2>&1 || echo "Aviso: python3 não encontrado no PATH — instale antes de usar a skill."
command -v git >/dev/null 2>&1 || echo "Aviso: git não encontrado no PATH — a skill precisa rodar dentro de um repositório git."

echo "Reabra (ou recarregue) o Claude Code para a skill /mensurar ficar disponível."
