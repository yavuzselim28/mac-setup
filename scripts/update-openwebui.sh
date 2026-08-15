#!/usr/bin/env bash
set -euo pipefail
# Manueller Fallback -- platform_agent.py macht das normalerweise automatisch (stuendlich per Cron).
RAW=$(curl -s https://api.github.com/repos/open-webui/open-webui/releases/latest | python3 -c "import json,sys; print(json.load(sys.stdin)['tag_name'])")
LATEST="${RAW#v}"   # ghcr.io taggt ohne "v" (z.B. 0.11.0), auch wenn der Release-Tag "v0.11.0" heisst
echo "Neueste Version: $LATEST"
docker pull "ghcr.io/open-webui/open-webui:$LATEST"
sed -i '' "s|open-webui:v\\{0,1\\}[0-9.]*|open-webui:${LATEST}|" ~/mac-setup/charts/ollama/values.yaml
helm upgrade ollama-app ~/ollama-k8s/ollama-chart -n phoenix -f ~/mac-setup/charts/ollama/values.yaml
kubectl rollout status deployment/ollama-app-open-webui -n phoenix
echo "Fertig: $LATEST ausgerollt (values.yaml geaendert, aber noch NICHT committet -- git add/commit/push separat)"
