# DNS Fix for VPN Issues with Vertex AI

## Problem

When using a VPN, DNS resolution for GCP/Vertex AI endpoints may fail, causing connection errors.

## Solution

Use one of the alternatives below. Run `uv run python scripts/verify_vertex_ai.py` to smoke-test Vertex AI connectivity.

## Alternative Solutions

### 1. System-Level DNS Configuration (macOS)

1. Open System Preferences → Network
2. Select your VPN connection
3. Click "Advanced" → "DNS"
4. Add Google DNS servers: `8.8.8.8`, `8.8.4.4`
5. Ensure they're listed before VPN DNS servers

### 2. VPN Split-Tunneling

- Add `*.googleapis.com` and `*.googlecloud.com` to VPN bypass list
- Routes GCP traffic directly, bypassing VPN DNS

### 3. Environment Variables

```bash
export DNS_SERVERS="8.8.8.8,8.8.4.4"
export GRPC_DNS_RESOLVER="native"
```

### 4. Hosts File (Last Resort)

```bash
nslookup <region>-aiplatform.googleapis.com 8.8.8.8
# Add result to /etc/hosts (IP addresses may change)
```

## Troubleshooting

1. **Verify VPN DNS servers:** `scutil --dns | grep nameserver`
2. **Test direct DNS query:** `dig @8.8.8.8 <region>-aiplatform.googleapis.com`
