#!/bin/bash
echo "🚀 Mac Setup startet..."

# Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
eval "$(/opt/homebrew/bin/brew shellenv zsh)"

# CLI Tools
echo "📦 Installiere CLI Tools..."
brew install kubectl helm terraform awscli k9s kubectx stern kind git watch

# GUI Apps
echo "🖥️ Installiere Apps..."
brew install --cask docker visual-studio-code

# Python PATH
echo 'export PATH="/opt/homebrew/opt/python@3.13/bin:$PATH"' >> ~/.zprofile

# VS Code Extensions
echo "🔧 Installiere VS Code Extensions..."
code --install-extension ms-kubernetes-tools.vscode-kubernetes-tools
code --install-extension ms-azuretools.vscode-docker
code --install-extension hashicorp.terraform
code --install-extension redhat.vscode-yaml
code --install-extension redhat.vscode-openshift-connector

# Aliases
echo 'alias ollama-start="~/ollama-k8s/start.sh"' >> ~/.zshrc
echo 'alias ollama-stop="~/ollama-k8s/stop.sh"' >> ~/.zshrc

echo "✅ Fertig! Starte Docker Desktop und aktiviere Kubernetes."
