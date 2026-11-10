#!/bin/zsh
set -euo pipefail
cd -- "$(dirname "$0")/.."
exec /usr/local/bin/node scripts/open-overnight-qa.mjs
