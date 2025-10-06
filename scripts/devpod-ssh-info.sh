#!/bin/bash
# Get DevPod SSH connection information

echo "🔍 DevPod SSH Connection Information"
echo "=================================="

# Check if DevPod is running
if ! devpod list | grep -q "Running"; then
    echo "❌ No running DevPod workspaces found."
    echo "   Start your workspace first: devpod up ."
    exit 1
fi

echo "📋 Available workspaces:"
devpod list

echo ""
echo "🔑 SSH connection details:"
echo "========================="

# Get SSH server info
devpod ssh-server . --print-config

echo ""
echo "🚀 Quick connection options:"
echo "============================"
echo "1. Direct SSH via DevPod:"
echo "   devpod ssh ."
echo ""
echo "2. Manual SSH connection:"
SSH_INFO=$(devpod ssh-server . --print-config | grep -E "(HostName|Port|IdentityFile)")
if [ ! -z "$SSH_INFO" ]; then
    HOST=$(echo "$SSH_INFO" | grep HostName | awk '{print $2}')
    PORT=$(echo "$SSH_INFO" | grep Port | awk '{print $2}')
    KEY=$(echo "$SSH_INFO" | grep IdentityFile | awk '{print $2}')
    echo "   ssh -i $KEY -p $PORT vscode@$HOST"
fi

echo ""
echo "3. For VSCodium Remote-SSH, add this to ~/.ssh/config:"
echo "   Host devpod-amai-lab"
devpod ssh-server . --print-config | sed 's/^/   /'

echo ""
echo "✅ Ready to connect!"