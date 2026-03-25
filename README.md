# Local Kubernetes Platform 🚀

> Multi-tenant platform engineering lab — built on Docker Desktop (Kubernetes) on a MacBook Pro M5 Pro (64GB RAM).
> Mirrors a production ROSA (Red Hat OpenShift on AWS) setup for hands-on platform engineering practice.

---

## Architecture

```
Cluster (docker-desktop)
├── phoenix-dev      → Tenant "Phoenix" (Development)
├── phoenix-prod     → Tenant "Phoenix" (Production)
├── atlas-dev        → Tenant "Atlas" (Development)
├── atlas-prod       → Tenant "Atlas" (Production)
├── monitoring       → Prometheus + Grafana + OpenCost
├── ingress-nginx    → NGINX Ingress Controller
└── ollama           → Local LLM (Ollama + Open WebUI)
```

**Reachable Services:**

| URL | Service |
|-----|---------|
| http://grafana.local | Grafana Dashboard |
| http://opencost.local | OpenCost Chargeback |
| http://ollama.local | Open WebUI (Ollama) |

---

## Stack

| Tool | Purpose |
|------|---------|
| **Docker Desktop** | Local Kubernetes cluster |
| **Helm** | Package management (Prometheus, OpenCost, NGINX, Ollama) |
| **ArgoCD** | GitOps continuous deployment |
| **Prometheus + Grafana** | Monitoring & observability |
| **OpenCost** | Chargeback & cost allocation per tenant |
| **NGINX Ingress** | Ingress controller with local DNS via `/etc/hosts` |
| **Ollama + Open WebUI** | Local LLM inference |

---

## Repository Structure

```
mac-setup/
├── charts/
│   └── ollama/              # Custom Helm Chart: Ollama + Open WebUI
│       ├── Chart.yaml
│       ├── values.yaml
│       └── templates/
├── setup-mac.sh             # Full Mac bootstrap script
├── start.sh                 # Start Ollama stack + port-forward
├── ingress.yaml             # Ingress resources (grafana, opencost, ollama)
├── rbac.yaml                # RBAC roles & bindings per tenant
├── quotas.yaml              # ResourceQuotas per namespace
├── limitrange.yaml          # LimitRange per namespace
├── networkpolicy.yaml       # NetworkPolicy for Phoenix tenants
├── networkpolicy-atlas.yaml # NetworkPolicy for Atlas tenants
├── platform-doku.md         # Full platform documentation (German)
└── openshift-local-setup.md # CRC / OpenShift Local setup notes
```

---

## GitOps with ArgoCD

This repo is the **GitOps source of truth**. ArgoCD watches the `charts/ollama` path and automatically syncs changes to the cluster.

```
Git Push → ArgoCD detects change → Auto-sync to Kubernetes
```

### Deploy Ollama via ArgoCD

```bash
argocd app create ollama-app \
  --repo https://github.com/yavuzselim28/mac-setup \
  --path charts/ollama \
  --dest-server https://kubernetes.default.svc \
  --dest-namespace default \
  --sync-policy automated
```

```bash
argocd app get ollama-app   # verify: all resources Synced + Healthy
```

---

## Getting Started

### Prerequisites

```bash
brew install kubectl helm argocd k9s
```

### 1. Bootstrap Mac environment

```bash
chmod +x setup-mac.sh && ./setup-mac.sh
```

### 2. Tenant namespaces + policies

```bash
kubectl create namespace phoenix-dev
kubectl create namespace phoenix-prod
kubectl create namespace atlas-dev
kubectl create namespace atlas-prod

kubectl label namespace phoenix-dev tenant=phoenix
kubectl label namespace phoenix-prod tenant=phoenix
kubectl label namespace atlas-dev tenant=atlas
kubectl label namespace atlas-prod tenant=atlas

kubectl apply -f quotas.yaml
kubectl apply -f limitrange.yaml
kubectl apply -f rbac.yaml
kubectl apply -f networkpolicy.yaml
kubectl apply -f networkpolicy-atlas.yaml
```

### 3. Monitoring (Prometheus + Grafana)

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
kubectl create namespace monitoring

helm install monitoring prometheus-community/kube-prometheus-stack -n monitoring \
  --set "prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.accessModes[0]=ReadWriteOnce" \
  --set "prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.resources.requests.storage=10Gi" \
  --set "grafana.persistence.enabled=true" \
  --set "grafana.persistence.size=2Gi"
```

### 4. Chargeback (OpenCost)

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

### 5. Ingress + local DNS

```bash
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm install ingress-nginx ingress-nginx/ingress-nginx -n ingress-nginx --create-namespace

sudo sh -c 'echo "127.0.0.1 grafana.local opencost.local ollama.local" >> /etc/hosts'

kubectl apply -f ingress.yaml
```

### 6. Ollama + Open WebUI

```bash
ollama-start   # starts pods + stable port-forward on port 80
ollama-stop    # stops pods + frees RAM
```

---

## Persistent Storage

| Component | PVC | Size | Contents |
|-----------|-----|------|----------|
| Ollama | ollama-pvc | 10Gi | LLM models |
| Prometheus | auto-generated | 10Gi | Metrics history |
| Grafana | auto-generated | 2Gi | Dashboard configs |

---

## Recommended LLM Models (M5 Pro 64GB)

| Model | Size | Notes |
|-------|------|-------|
| llama3.2:3b | ~2GB | Fast, good for testing |
| llama3.1:8b | ~5GB | Best balance ✅ |
| mistral:7b | ~4GB | Great for code |
| mixtral:8x7b | ~26GB | Most powerful that runs comfortably |

---

## Mapping: Local → ROSA (Production)

| Local | ROSA / Work |
|-------|-------------|
| docker-desktop cluster | ROSA cluster on AWS |
| Namespace phoenix-dev | Namespace kunde-a-dev |
| ResourceQuota | ResourceQuota |
| LimitRange | LimitRange |
| RBAC | RBAC + OpenShift Groups |
| NetworkPolicy | NetworkPolicy |
| Prometheus + PVC | Dedicated Prometheus instance |
| OpenCost (simulated costs) | OpenCost (real AWS costs) |
| NGINX Ingress | HAProxy / OpenShift Router |
| grafana.local | grafana.firma.de |

---

## Skills Demonstrated

- **Multi-tenant Kubernetes** — Namespace isolation, RBAC, NetworkPolicy, ResourceQuota, LimitRange
- **Helm** — Custom Chart development, kube-prometheus-stack, OpenCost, NGINX Ingress
- **GitOps** — ArgoCD with automated sync policies
- **Observability** — Prometheus + Grafana with persistent storage
- **FinOps / Chargeback** — OpenCost for per-tenant cost allocation
- **Local LLM** — Ollama + Open WebUI deployed via Helm on Kubernetes
- **Platform Engineering** — Reproducible environment mirroring production ROSA setup

---

## Author

Yavuz — Cloud Platform Engineer
