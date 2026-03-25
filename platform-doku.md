# Lokale Kubernetes Platform — Dokumentation

> Gebaut auf Docker Desktop (Kubernetes) auf einem MacBook Pro M5 Pro (64GB RAM)  
> Ziel: Multi-Tenant Platform lokal nachbauen — analog zu ROSA auf der Arbeit

---

## Architektur Überblick

```
Cluster (docker-desktop)
├── phoenix-dev      → Tenant "Phoenix" (Entwicklungsumgebung)
├── phoenix-prod     → Tenant "Phoenix" (Produktionsumgebung)
├── atlas-dev        → Tenant "Atlas" (Entwicklungsumgebung)
├── atlas-prod       → Tenant "Atlas" (Produktionsumgebung)
├── monitoring       → Prometheus + Grafana + OpenCost
├── ingress-nginx    → NGINX Ingress Controller
├── argocd           → GitOps Continuous Deployment
└── ollama           → Lokales LLM (Ollama + Open WebUI)
```

**Erreichbare Services:**
- http://grafana.local → Grafana Dashboard
- http://opencost.local → OpenCost Chargeback
- http://ollama.local → Open WebUI (Ollama)
- https://argocd.local → ArgoCD UI

---

## ⚠️ Wichtig: Cluster Kontext

Dieser Stack läuft auf **docker-desktop**. Wenn du auch CRC (OpenShift Local) nutzt:

```bash
kubectl config current-context   # sollte "docker-desktop" zeigen

# Falls CRC aktiv ist, zurück zu docker-desktop:
export KUBECONFIG=~/.kube/config
```

**NIEMALS** `export KUBECONFIG=~/.crc/machines/crc/kubeconfig` in `~/.zshrc` eintragen!

Für CRC nur temporär setzen:
```bash
export KUBECONFIG=~/.crc/machines/crc/kubeconfig   # nur für diese Terminal Session
```

---

## Phase 1 — Fundament (Namespaces, Quotas, RBAC, LimitRange, NetworkPolicy)

### 1.1 Namespaces erstellen

```bash
kubectl create namespace phoenix-dev
kubectl create namespace phoenix-prod
kubectl create namespace atlas-dev
kubectl create namespace atlas-prod
kubectl create namespace ollama
```

### 1.2 Labels setzen

Tenant-Labels sind wichtig für OpenCost — nur so kann nach Kostenstelle abgerechnet werden.

```bash
# Tenant Namespaces
kubectl label namespace phoenix-dev tenant=phoenix
kubectl label namespace phoenix-prod tenant=phoenix
kubectl label namespace atlas-dev tenant=atlas
kubectl label namespace atlas-prod tenant=atlas

# Platform Namespaces
kubectl label namespace ollama tenant=platform
kubectl label namespace monitoring tenant=platform
kubectl label namespace argocd tenant=platform
kubectl label namespace ingress-nginx tenant=platform

kubectl get namespaces --show-labels
```

**Erwartetes Ergebnis:**

| Namespace | Label |
|-----------|-------|
| phoenix-dev, phoenix-prod | tenant=phoenix |
| atlas-dev, atlas-prod | tenant=atlas |
| ollama, monitoring, argocd, ingress-nginx | tenant=platform |
| default, kube-* | kein Label (nie benutzen) |

### 1.3 ResourceQuotas

```bash
kubectl apply -f ~/quotas.yaml
kubectl get resourcequota -A
```

### 1.4 LimitRange

```bash
kubectl apply -f ~/limitrange.yaml
kubectl get limitrange -A
```

### 1.5 RBAC

```bash
kubectl apply -f ~/rbac.yaml
kubectl get roles,rolebindings -A
```

### 1.6 NetworkPolicies

```bash
kubectl apply -f ~/networkpolicy.yaml
kubectl apply -f ~/networkpolicy-atlas.yaml
kubectl get networkpolicy -A
```

---

## Phase 2 — Monitoring (Prometheus + Grafana)

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
kubectl create namespace monitoring
```

### Installation mit persistentem Speicher

Prometheus und Grafana bekommen beide PVCs — Daten und Dashboard-Konfigurationen  
bleiben dauerhaft erhalten, auch nach Pod-Neustarts oder Docker Desktop Neustart.

```bash
helm install monitoring prometheus-community/kube-prometheus-stack -n monitoring \
  --set "prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.accessModes[0]=ReadWriteOnce" \
  --set "prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.resources.requests.storage=10Gi" \
  --set "grafana.persistence.enabled=true" \
  --set "grafana.persistence.size=2Gi"
```

Falls bereits installiert (Upgrade):
```bash
helm upgrade monitoring prometheus-community/kube-prometheus-stack -n monitoring \
  --set "prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.accessModes[0]=ReadWriteOnce" \
  --set "prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.resources.requests.storage=10Gi" \
  --set "grafana.persistence.enabled=true" \
  --set "grafana.persistence.size=2Gi"

kubectl get pvc -n monitoring   # PVCs sollten "Bound" sein
```

### Grafana öffnen

```bash
grafana-password   # Passwort holen
# Browser: http://grafana.local
# Login: admin / <passwort>
```

**Dashboard:** Dashboards → Kubernetes / Compute Resources / Namespace

---

## Phase 3 — Chargeback (OpenCost)

```bash
helm repo add opencost https://opencost.github.io/opencost-helm-chart
helm repo update

helm install opencost opencost/opencost -n monitoring \
  --set opencost.exporter.defaultClusterId=local \
  --set opencost.prometheus.internal.enabled=true \
  --set opencost.prometheus.internal.serviceName=monitoring-kube-prometheus-prometheus \
  --set opencost.prometheus.internal.namespaceName=monitoring \
  --set opencost.prometheus.internal.port=9090
```

**Browser:** http://opencost.local

OpenCost rechnet automatisch nach Namespace ab. Durch die Tenant-Labels aus Phase 1  
können Kosten sauber nach `phoenix`, `atlas` und `platform` gruppiert werden.

---

## Phase 4 — Ingress (NGINX)

```bash
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update

# SSL Passthrough aktivieren — benötigt für argocd.local
helm install ingress-nginx ingress-nginx/ingress-nginx -n ingress-nginx --create-namespace \
  --set controller.extraArgs.enable-ssl-passthrough=""

# /etc/hosts einmalig anpassen — dauerhaft auf 127.0.0.1
sudo sh -c 'echo "127.0.0.1 grafana.local opencost.local ollama.local argocd.local" >> /etc/hosts'

# Ingress Ressourcen anwenden
kubectl apply -f ~/ingress.yaml
kubectl get ingress -A
```

### Warum 127.0.0.1 und Port-Forward?

Docker Desktop's LoadBalancer IP ist instabil und ändert sich nach Neustarts.  
Die Lösung: `/etc/hosts` dauerhaft auf `127.0.0.1` — der `ollama-start` Script startet  
immer einen `sudo kubectl port-forward` auf Port 80 als stabilen Tunnel.

### Falls NGINX bereits installiert ist (Upgrade für SSL Passthrough):

```bash
helm upgrade ingress-nginx ingress-nginx/ingress-nginx \
  -n ingress-nginx \
  --set controller.extraArgs.enable-ssl-passthrough=""
```

---

## Phase 5 — GitOps (ArgoCD)

ArgoCD übernimmt das automatische Deployment — dieses Git Repository ist die **einzige Source of Truth**.  
Kein manuelles `kubectl apply` mehr: jeder `git push` triggert automatisch einen Sync auf den Cluster.

### Installation

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Warten bis alle Pods laufen
kubectl get pods -n argocd -w
```

### ArgoCD UI öffnen

```bash
# ollama-start muss laufen (Port-Forward auf Port 80)
# Browser: https://argocd.local
# SSL-Warnung wegklicken — selbstsigniertes Zertifikat, normal
```

### Initial-Passwort holen & ändern

```bash
# Passwort holen
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d && echo

# Login via CLI (über argocd.local)
argocd login argocd.local --username admin --insecure

# Passwort ändern
argocd account update-password
```

### Ollama App deployen

```bash
argocd app create ollama-app \
  --repo https://github.com/yavuzselim28/mac-setup \
  --path charts/ollama \
  --dest-server https://kubernetes.default.svc \
  --dest-namespace ollama \
  --sync-policy automated
```

### Status prüfen

```bash
argocd app get ollama-app
# Alle Ressourcen sollten "Synced" und "Healthy" zeigen
```

### GitOps Workflow

```
Änderung in charts/ollama/ → git push → ArgoCD erkennt Änderung → Auto-Sync auf Cluster
```

Ab sofort gilt: **Git ist die einzige Source of Truth.** Änderungen am Cluster werden von ArgoCD  
automatisch wieder auf den Stand im Repo zurückgesetzt (Self-Healing).

---

## Ollama + Open WebUI (Helm Chart)

```bash
ollama-start   # Pods starten + stabiler Port-Forward auf Port 80
ollama-stop    # Pods stoppen + RAM freigeben
```

### Modell pullen

```bash
# Im zweiten Terminal
kubectl port-forward svc/ollama-app-ollama 11434:11434 -n ollama &
curl http://localhost:11434/api/pull -d '{"model": "llama3.1:8b"}'
```

### Modell löschen

```bash
curl -X DELETE http://localhost:11434/api/delete -d '{"model": "modellname"}'
```

### Empfohlene Modelle für M5 Pro 64GB

| Modell | Größe | Empfehlung |
|--------|-------|------------|
| llama3.2:3b | ~2GB | Schnell, gut für Tests |
| llama3.1:8b | ~5GB | Beste Balance ✅ |
| mistral:7b | ~4GB | Sehr gut für Code |
| mixtral:8x7b | ~26GB | Stärkstes was komfortabel läuft |
| llama3.3:70b | ~43GB | Zu groß mit laufendem Stack |

---

## Start/Stop Scripts

### ~/ollama-k8s/start.sh

```bash
#!/bin/bash
echo "🚀 Starting Ollama + Open WebUI..."
kubectl scale deployment ollama-app-ollama -n ollama --replicas=1
kubectl scale deployment ollama-app-open-webui -n ollama --replicas=1
echo "⏳ Warte bis Pods ready sind..."
kubectl wait --for=condition=ready pod -l app=ollama-app-ollama -n ollama --timeout=120s
kubectl wait --for=condition=ready pod -l app=ollama-app-open-webui -n ollama --timeout=120s
sleep 10

# Alten Port-Forward killen falls noch aktiv
sudo pkill -f "port-forward svc/ingress-nginx" 2>/dev/null
sleep 2

# Stabiler Port-Forward auf Port 80 — /etc/hosts bleibt immer 127.0.0.1
sudo kubectl port-forward svc/ingress-nginx-controller 80:80 -n ingress-nginx &

echo "✅ Done!"
echo "🤖 Open WebUI: http://ollama.local"
echo "🔗 Grafana: http://grafana.local"
echo "🔗 OpenCost: http://opencost.local"
echo "🔗 ArgoCD: https://argocd.local"
echo ""
echo "Press Ctrl+C to stop"
wait
```

### ~/ollama-k8s/stop.sh

```bash
#!/bin/bash
echo "🛑 Stopping Ollama + Open WebUI..."
sudo pkill -f "port-forward svc/ingress-nginx" 2>/dev/null
kubectl scale deployment ollama-app-ollama -n ollama --replicas=0
kubectl scale deployment ollama-app-open-webui -n ollama --replicas=0
echo "✅ Done! RAM freigegeben."
```

---

## Aliases (~/.zshrc)

```bash
alias ollama-start="~/ollama-k8s/start.sh"
alias ollama-stop="~/ollama-k8s/stop.sh"
alias grafana-pass="kubectl --namespace monitoring get secrets monitoring-grafana -o jsonpath=\"{.data.admin-password}\" | base64 -d ; echo"
alias grafana-password="kubectl --namespace monitoring get secrets monitoring-grafana -o jsonpath=\"{.data.admin-password}\" | base64 -d ; echo"
alias monitoring-start="kubectl scale deployment monitoring-grafana monitoring-kube-state-metrics opencost -n monitoring --replicas=1 && kubectl scale statefulset prometheus-monitoring-kube-prometheus-prometheus alertmanager-monitoring-kube-prometheus-alertmanager -n monitoring --replicas=1"
alias monitoring-stop="kubectl scale deployment monitoring-grafana monitoring-kube-state-metrics opencost -n monitoring --replicas=0 && kubectl scale statefulset prometheus-monitoring-kube-prometheus-prometheus alertmanager-monitoring-kube-prometheus-alertmanager -n monitoring --replicas=0"
alias argocd-apps="argocd app list"
alias argocd-sync="argocd app sync ollama-app"
```

---

## Persistenter Speicher Übersicht

| Komponente | PVC | Größe | Inhalt |
|------------|-----|-------|--------|
| Ollama | ollama-app-pvc | 10Gi | LLM Modelle |
| Prometheus | auto-generiert | 10Gi | Metriken Historie |
| Grafana | auto-generiert | 2Gi | Dashboard Konfigurationen |

---

## Nützliche Befehle

```bash
# Cluster Überblick
kubectl get nodes
kubectl get namespaces --show-labels
kubectl get pods -A

# PVCs anzeigen
kubectl get pvc -A

# Quota Verbrauch
kubectl get resourcequota -A

# Ingress
kubectl get ingress -A
kubectl get svc -n ingress-nginx

# Logs
kubectl logs <pod-name> -n <namespace>

# Deployment neu starten
kubectl rollout restart deployment/<name> -n <namespace>

# Interaktive Cluster UI
k9s

# Grafana Passwort
grafana-password

# Monitoring starten/stoppen
monitoring-start
monitoring-stop

# Port-Forward manuell killen
sudo pkill -f "port-forward svc/ingress-nginx"

# ArgoCD
argocd app list
argocd app get ollama-app
argocd app sync ollama-app
```

---

## Helm Charts Übersicht

```bash
helm list -A
```

| Name | Namespace | Chart | Beschreibung |
|------|-----------|-------|--------------|
| ollama-app | ollama | ollama-chart | Ollama + Open WebUI (via ArgoCD) |
| monitoring | monitoring | kube-prometheus-stack | Prometheus + Grafana (beide mit PVC) |
| opencost | monitoring | opencost | Chargeback Tool |
| ingress-nginx | ingress-nginx | ingress-nginx | NGINX Ingress Controller (SSL Passthrough aktiv) |
| argocd | argocd | argocd (plain manifest) | GitOps Controller |

---

## Zusammenhang mit der Arbeit (ROSA)

| Lokal | ROSA/Arbeit |
|-------|-------------|
| docker-desktop Cluster | ROSA Cluster auf AWS |
| Namespace phoenix-dev | Namespace kunde-a-dev |
| ResourceQuota | ResourceQuota |
| LimitRange | LimitRange |
| RBAC | RBAC + OpenShift Groups |
| NetworkPolicy | NetworkPolicy |
| Prometheus + PVC | Eigene Prometheus Instanz |
| Grafana + PVC | Grafana mit persistentem Storage |
| OpenCost lokal | OpenCost auf ROSA |
| Simulierte Kosten | Echte AWS Kosten |
| NGINX Ingress | HAProxy / OpenShift Router |
| grafana.local | grafana.firma.de |
| ArgoCD | OpenShift GitOps (ArgoCD) |
| tenant=phoenix/atlas/platform Labels | Tenant Labels für Chargeback |
