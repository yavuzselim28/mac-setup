#!/bin/bash
echo "🚀 Starting Ollama + Open WebUI..."
kubectl scale deployment ollama-ollama -n ollama --replicas=1
kubectl scale deployment ollama-open-webui -n ollama --replicas=1
echo "⏳ Warte bis Pods ready sind..."
kubectl wait --for=condition=ready pod -l app=ollama-ollama -n ollama --timeout=120s
kubectl wait --for=condition=ready pod -l app=ollama-open-webui -n ollama --timeout=120s
sleep 10

# Ingress IP automatisch erkennen und /etc/hosts updaten
INGRESS_IP=$(kubectl get svc ingress-nginx-controller -n ingress-nginx -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo "🌐 Ingress IP: $INGRESS_IP"

if [ -n "$INGRESS_IP" ]; then
  sudo sed -i '' "s/.*grafana.local.*/$INGRESS_IP        grafana.local opencost.local ollama.local/" /etc/hosts
  echo "✅ /etc/hosts aktualisiert"
else
  echo "⚠️ Keine Ingress IP gefunden — Port-Forward wird genutzt"
  kubectl port-forward svc/ingress-nginx-controller 8080:80 -n ingress-nginx &
fi

echo "✅ Done!"
echo "🤖 Open WebUI: http://ollama.local"
echo "🔗 Grafana: http://grafana.local"
echo "🔗 OpenCost: http://opencost.local"
echo ""
echo "Press Ctrl+C to stop"
wait
