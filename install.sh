#!/usr/bin/env bash
# Copia el framework SecQA dentro de otro proyecto.
# Uso: ./install.sh /ruta/al/proyecto-objetivo
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Uso: $0 /ruta/al/proyecto-objetivo"
  exit 1
fi

TARGET="$1"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -d "$TARGET" ]; then
  echo "No existe el directorio: $TARGET"
  exit 1
fi

mkdir -p "$TARGET/.claude/skills"
cp -R "$HERE/.claude/skills/." "$TARGET/.claude/skills/"
cp -R "$HERE/tools" "$TARGET/"
cp "$HERE/scope.yml.example" "$TARGET/scope.yml.example"

if [ ! -f "$TARGET/.gitignore" ]; then
  cp "$HERE/.gitignore" "$TARGET/.gitignore"
else
  cat "$HERE/.gitignore" >> "$TARGET/.gitignore"
  echo "[ok] reglas de SecQA añadidas a .gitignore existente"
fi

echo "[ok] SecQA copiado en $TARGET"
echo "Siguiente paso dentro de ese proyecto:"
echo "  cp scope.yml.example scope.yml   # y edítalo"
echo "  python3 tools/db/init_db.py --db-path findings.db"
echo "  (en Claude Code) /pentest-run"
