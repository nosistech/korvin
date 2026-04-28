#!/bin/bash
set -euo pipefail
BACKUP_DIR="/home/korvin/.backup-repo"
TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)
mkdir -p "$BACKUP_DIR/snapshots/$TIMESTAMP"
for item in docs/activity.md data/ logs/; do
  src="/home/korvin/korvin/$item"
  [ -e "$src" ] && cp -r "$src" "$BACKUP_DIR/snapshots/$TIMESTAMP/" && echo "  ✅ $item"
done
cd "$BACKUP_DIR"
git add -A
git commit -m "State snapshot $TIMESTAMP" 2>/dev/null || true
git push origin main 2>/dev/null
echo "Backup completed."
