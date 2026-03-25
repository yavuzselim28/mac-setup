# mac-setup 🚀

> Platform Engineering local development environment — Kubernetes, Helm, GitOps with ArgoCD.

## Overview

This repository serves as the **GitOps source of truth** for a local Kubernetes platform engineering setup on macOS. It includes Helm Charts, Kubernetes manifests, and bootstrap scripts for a fully reproducible environment.

## Stack

| Tool | Purpose |
|---|---|
| **Docker Desktop** | Local Kubernetes cluster |
| **Helm** | Package management for Kubernetes |
| **ArgoCD** | GitOps continuous deployment |
| **Ollama** | Local LLM inference engine |
| **Open WebUI** | Web UI for interacting with LLMs |

## Repository Structure

```
mac-setup/
├── charts/
│   └── ollama/              # Helm Chart: Ollama + Open WebUI
│       ├── Chart.yaml
│       ├── values.yaml
│       └── templates/
├── setup-mac.sh             # Bootstrap script for full Mac setup
├── ingress.yaml             # Ingress configuration
├── rbac.yaml                # RBAC policies
├── quotas.yaml              # Resource quotas
├── networkpolicy.yaml       # Network policies
└── platform-doku.md         # Platform documentation
```

## GitOps Workflow

This repo follows a **GitOps pattern** — ArgoCD watches this repository and automatically syncs any changes to the local Kubernetes cluster.

```
Git Push → ArgoCD detects change → Auto-sync to Kubernetes cluster
```

No manual `kubectl apply` needed. Git is the single source of truth.

## Getting Started

### Prerequisites

- macOS with Docker Desktop (Kubernetes enabled)
- `kubectl`, `helm`, `argocd` CLI installed

### 1. Bootstrap Mac environment

```bash
chmod +x setup-mac.sh
./setup-mac.sh
```

### 2. Install ArgoCD

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```

### 3. Access ArgoCD UI

```bash
kubectl port-forward svc/argocd-server -n argocd 8080:443
```

Open https://localhost:8080 and login with:
- **User:** `admin`
- **Password:** `kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d`

### 4. Deploy Ollama + Open WebUI via ArgoCD

```bash
argocd app create ollama-app \
  --repo https://github.com/yavuzselim28/mac-setup \
  --path charts/ollama \
  --dest-server https://kubernetes.default.svc \
  --dest-namespace default \
  --sync-policy automated
```

ArgoCD will automatically deploy Ollama and Open WebUI to your local cluster.

### 5. Verify deployment

```bash
argocd app get ollama-app
```

All resources should show `Synced` and `Healthy`.

## Architecture

```
┌─────────────────────────────────────────┐
│           GitHub Repository             │
│         (Source of Truth)               │
└──────────────────┬──────────────────────┘
                   │ GitOps sync
                   ▼
┌─────────────────────────────────────────┐
│               ArgoCD                    │
│         (Continuous Deployment)         │
└──────────────────┬──────────────────────┘
                   │ deploys
                   ▼
┌─────────────────────────────────────────┐
│     Kubernetes (Docker Desktop)         │
│                                         │
│  ┌─────────────┐  ┌──────────────────┐  │
│  │   Ollama    │  │   Open WebUI     │  │
│  │  (LLM API)  │  │   (Frontend)     │  │
│  └─────────────┘  └──────────────────┘  │
└─────────────────────────────────────────┘
```

## Skills Demonstrated

- **Kubernetes** — Deployments, Services, PVCs, RBAC, Network Policies, Resource Quotas
- **Helm** — Custom Chart development, templating, values management
- **GitOps** — ArgoCD setup, automated sync policies, Git as source of truth
- **Platform Engineering** — Reproducible environments, infrastructure as code

## Author

Yavuz — Cloud Platform Engineer
