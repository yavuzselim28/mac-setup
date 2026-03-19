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
└── ollama           → Lokales LLM (Ollama + Open WebUI)
```

---

## Phase 1 — Fundament (Namespaces, Quotas, RBAC)

### 1.1 Namespaces erstellen

Ein Namespace ist eine logische Isolationsschicht im Cluster.  
Jeder Tenant bekommt eigene Namespaces — dev und prod getrennt.

```bash
kubectl create namespace phoenix-dev
kubectl create namespace phoenix-prod
kubectl create namespace atlas-dev
kubectl create namespace atlas-prod
```

### 1.2 Labels setzen

Labels verbinden alle Namespaces eines Tenants.  
OpenCost nutzt diese Labels später um Kosten pro Tenant zu aggregieren.

```bash
kubectl label namespace phoenix-dev tenant=phoenix
kubectl label namespace phoenix-prod tenant=phoenix
kubectl label namespace atlas-dev tenant=atlas
kubectl label namespace atlas-prod tenant=atlas
```

Verifizieren:
```bash
kubectl get namespaces --show-labels
```

### 1.3 ResourceQuotas

ResourceQuotas begrenzen wie viel CPU, RAM und Pods ein Tenant verbrauchen darf.  
Das ist der technische Unterbau des Chargeback Modells — Quota = gebuchte Kapazität.

**Wichtig:** Quotas werden pro Namespace gesetzt. In der Praxis entspricht das dem SLA mit dem Kunden.

```yaml
# ~/quotas.yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: phoenix-quota
  namespace: phoenix-dev
spec:
  hard:
    requests.cpu: "2"       # Minimum reserviert
    requests.memory: 4Gi   # Minimum reserviert
    limits.cpu: "4"         # Maximum erlaubt
    limits.memory: 8Gi     # Maximum erlaubt
    pods: "10"              # Maximale Pod-Anzahl
---
apiVersion: v1
kind: ResourceQuota
metadata:
  name: phoenix-quota
  namespace: phoenix-prod
spec:
  hard:
    requests.cpu: "4"
    requests.memory: 8Gi
    limits.cpu: "8"
    limits.memory: 16Gi
    pods: "20"
---
apiVersion: v1
kind: ResourceQuota
metadata:
  name: atlas-quota
  namespace: atlas-dev
spec:
  hard:
    requests.cpu: "1"
    requests.memory: 2Gi
    limits.cpu: "2"
    limits.memory: 4Gi
    pods: "5"
---
apiVersion: v1
kind: ResourceQuota
metadata:
  name: atlas-quota
  namespace: atlas-prod
spec:
  hard:
    requests.cpu: "2"
    requests.memory: 4Gi
    limits.cpu: "4"
    limits.memory: 8Gi
    pods: "10"
```

```bash
kubectl apply -f ~/quotas.yaml
kubectl get resourcequota -A   # Verbrauch vs. Limit anzeigen
```

**Logik:**
- Phoenix ist ein größerer Kunde → mehr Quota
- Atlas ist ein kleinerer Kunde → weniger Quota
- Prod hat immer mehr Kapazität als Dev

### 1.4 RBAC (Role Based Access Control)

RBAC steuert wer was im Cluster darf.  
Jeder Tenant bekommt eine Role (Berechtigungen) und ein RoleBinding (wer bekommt diese Role).

**Konzept:**
- **Role** → definiert Berechtigungen (get, list, create, delete etc.)
- **RoleBinding** → verbindet einen User mit einer Role
- **Scope** → Roles gelten nur im jeweiligen Namespace

```yaml
# ~/rbac.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: tenant-role
  namespace: phoenix-dev
rules:
  - apiGroups: ["", "apps"]
    resources: ["pods", "deployments", "services", "configmaps"]
    verbs: ["get", "list", "watch", "create", "update", "delete"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: phoenix-binding
  namespace: phoenix-dev
subjects:
  - kind: User
    name: phoenix-user           # Dieser User bekommt die Role
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: tenant-role
  apiGroup: rbac.authorization.k8s.io
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: tenant-role
  namespace: atlas-dev
rules:
  - apiGroups: ["", "apps"]
    resources: ["pods", "deployments", "services", "configmaps"]
    verbs: ["get", "list", "watch", "create", "update", "delete"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: atlas-binding
  namespace: atlas-dev
subjects:
  - kind: User
    name: atlas-user
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: tenant-role
  apiGroup: rbac.authorization.k8s.io
```

```bash
kubectl apply -f ~/rbac.yaml
kubectl get roles,rolebindings -A   # Alle Roles und Bindings anzeigen
```

**Ergebnis:** `phoenix-user` kann nur in `phoenix-dev` arbeiten, `atlas-user` nur in `atlas-dev`. Kein Tenant sieht den anderen.

---

## Phase 2 — Monitoring (Prometheus + Grafana)

Prometheus sammelt Metriken aus dem Cluster.  
Grafana visualisiert diese Metriken in Dashboards.

**Warum kube-prometheus-stack?**  
Das Chart bringt Prometheus + Grafana + Alertmanager + node-exporter in einem Paket.  
Das ist der Standard in der Industrie.

```bash
# Helm Repo hinzufügen
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Namespace erstellen
kubectl create namespace monitoring

# Stack installieren
helm install monitoring prometheus-community/kube-prometheus-stack -n monitoring

# Status prüfen
kubectl get pods -n monitoring
```

**Was wird deployed:**
- `prometheus` → sammelt Metriken (CPU, RAM, Netzwerk etc.)
- `grafana` → Dashboard UI
- `alertmanager` → sendet Alerts (Email, Slack etc.)
- `kube-state-metrics` → Kubernetes-spezifische Metriken
- `node-exporter` → Hardware-Metriken vom Node

### Grafana öffnen

```bash
# Passwort holen
kubectl --namespace monitoring get secrets monitoring-grafana \
  -o jsonpath="{.data.admin-password}" | base64 -d ; echo

# Port-Forward
kubectl --namespace monitoring port-forward svc/monitoring-grafana 3000:80
```

Browser: `http://localhost:3000`  
Login: `admin` / (Passwort aus obigem Befehl)

**Dashboard:** Dashboards → Kubernetes / Compute Resources / Namespace  
→ Namespace auswählen → CPU/RAM/Netzwerk Verbrauch pro Tenant sehen

---

## Phase 3 — Chargeback (OpenCost)

OpenCost misst die Kosten pro Namespace/Tenant.  
In der Praxis auf ROSA: echte AWS Kosten. Lokal: simulierte Preise (AWS us-east-1 Standard).

**Verbindung zum PSF Modell:**
- ResourceQuota = gebuchte Kapazität (Nenner im PSF)
- OpenCost = tatsächlicher Verbrauch (Zähler im PSF)
- PSF = Verbrauch / Kapazität × Gewichtung

```bash
# Helm Repo hinzufügen
helm repo add opencost https://opencost.github.io/opencost-helm-chart
helm repo update

# OpenCost installieren und auf unseren Prometheus zeigen
helm install opencost opencost/opencost -n monitoring \
  --set opencost.exporter.defaultClusterId=local \
  --set opencost.prometheus.internal.enabled=true \
  --set opencost.prometheus.internal.serviceName=monitoring-kube-prometheus-prometheus \
  --set opencost.prometheus.internal.namespaceName=monitoring \
  --set opencost.prometheus.internal.port=9090

# Status prüfen
kubectl get pods -l app.kubernetes.io/instance=opencost -n monitoring
```

### OpenCost öffnen

```bash
kubectl port-forward svc/opencost 9090 -n monitoring
```

Browser: `http://localhost:9090`

**Was du siehst:** Kosten pro Namespace, aufgeteilt nach CPU/RAM/Storage/Netzwerk.

---

## Test-Deployments für Tenants

Damit OpenCost Daten hat, brauchen die Tenant-Namespaces laufende Pods.  
**Wichtig:** Pods müssen `resources.requests` und `resources.limits` haben,  
sonst werden sie von der ResourceQuota abgelehnt!

```yaml
# ~/test-deployment.yaml — Phoenix
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx
  namespace: phoenix-dev
spec:
  replicas: 2
  selector:
    matchLabels:
      app: nginx
  template:
    metadata:
      labels:
        app: nginx
        tenant: phoenix    # Label für OpenCost Aggregation
    spec:
      containers:
        - name: nginx
          image: nginx
          resources:
            requests:
              cpu: 100m      # 0.1 CPU Core
              memory: 128Mi
            limits:
              cpu: 200m      # 0.2 CPU Core
              memory: 256Mi
```

```bash
kubectl apply -f ~/test-deployment.yaml
kubectl apply -f ~/test-deployment-atlas.yaml
```

---

## Nützliche Befehle

```bash
# Cluster Überblick
kubectl get nodes
kubectl get namespaces --show-labels
kubectl get pods -A

# Quota Verbrauch anzeigen
kubectl get resourcequota -A

# Alle Roles und Bindings
kubectl get roles,rolebindings -A

# Services anzeigen
kubectl get svc -n monitoring

# Logs eines Pods
kubectl logs <pod-name> -n <namespace>

# Pod Details
kubectl describe pod <pod-name> -n <namespace>

# Deployment neu starten
kubectl rollout restart deployment/<name> -n <namespace>

# Interaktive Cluster UI
k9s
```

---

## Start/Stop Scripts

```bash
# Ollama + Open WebUI starten
ollama-start   # http://localhost:8080

# Ollama + Open WebUI stoppen
ollama-stop

# Monitoring Stack starten
kubectl port-forward svc/monitoring-grafana 3000:80 -n monitoring &
kubectl port-forward svc/opencost 9090 -n monitoring &

# Grafana: http://localhost:3000
# OpenCost: http://localhost:9090
```

---

## Helm Charts Übersicht

```bash
helm list -A   # Alle installierten Charts anzeigen
```

| Name | Namespace | Chart | Beschreibung |
|------|-----------|-------|--------------|
| ollama | ollama | ollama-chart | Ollama + Open WebUI (eigenes Chart) |
| monitoring | monitoring | kube-prometheus-stack | Prometheus + Grafana |
| opencost | monitoring | opencost | Chargeback Tool |

---

## Zusammenhang mit der Arbeit (ROSA)

| Lokal | ROSA/Arbeit |
|-------|-------------|
| docker-desktop Cluster | ROSA Cluster auf AWS |
| Namespace phoenix-dev | Namespace kunde-a-dev |
| ResourceQuota | ResourceQuota |
| RBAC | RBAC + OpenShift Groups |
| Prometheus (eigene Instanz) | Eigene Prometheus Instanz (CMO locked) |
| OpenCost lokal | OpenCost auf ROSA |
| Simulierte Kosten | Echte AWS Kosten |
| kind/docker CNI | OVN-Kubernetes |

Das Prinzip ist identisch — nur die Infrastruktur dahinter unterscheidet sich.
