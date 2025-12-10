# DNS Fix for VPN Issues with Vertex AI

## Problem

When using a VPN, DNS resolution for GCP/Vertex AI endpoints may fail, causing connection errors.

## Solution

This project includes DNS utilities that configure custom DNS resolution to bypass VPN DNS issues.

## Installation

For best results, install `dnspython`:

```bash
pip install dnspython
```

Or install with the optional DNS dependency:

```bash
pip install -e ".[dns]"
```

## Usage

The DNS fix is automatically applied when importing Vertex AI related modules. The fix:

1. Configures DNS to use Google's DNS servers (8.8.8.8, 8.8.4.4)
2. Patches `socket.getaddrinfo` to use custom DNS resolution (if dnspython is installed)
3. Sets environment variables that may help with DNS resolution

### Manual Setup

If you need to apply the DNS fix manually:

```python
from linkedin_api.dns_utils import setup_gcp_dns_fix

# Apply DNS fix before importing Google libraries
setup_gcp_dns_fix(use_custom_resolver=True)

# Now import and use Vertex AI
import vertexai
from vertexai.preview.generative_models import GenerativeModel
```

### Testing DNS Resolution

Test if DNS resolution works:

```python
from linkedin_api.dns_utils import test_dns_resolution

# Test Vertex AI endpoint
result = test_dns_resolution("europe-west9-aiplatform.googleapis.com")
print(f"DNS resolution: {'OK' if result else 'FAILED'}")
```

## Alternative Solutions

If the Python-level DNS fix doesn't work, consider:

### 1. System-Level DNS Configuration (macOS)

Configure your system to use Google DNS for GCP endpoints:

1. Open System Preferences → Network
2. Select your VPN connection
3. Click "Advanced" → "DNS"
4. Add Google DNS servers: `8.8.8.8`, `8.8.4.4`
5. Ensure they're listed before VPN DNS servers

### 2. VPN Split-Tunneling

Configure your VPN to exclude GCP endpoints from VPN routing:

- Add `*.googleapis.com` and `*.googlecloud.com` to VPN bypass list
- This routes GCP traffic directly, bypassing VPN DNS

### 3. Environment Variables

Set DNS-related environment variables before running:

```bash
export DNS_SERVERS="8.8.8.8,8.8.4.4"
export GRPC_DNS_RESOLVER="native"
```

### 4. Hosts File (Last Resort)

If DNS continues to fail, you can manually add entries to `/etc/hosts`:

```bash
# Get IP address for Vertex AI endpoint
nslookup europe-west9-aiplatform.googleapis.com 8.8.8.8

# Add to /etc/hosts (requires sudo)
sudo nano /etc/hosts
# Add: <IP_ADDRESS> europe-west9-aiplatform.googleapis.com
```

**Note:** This is not recommended as IP addresses may change.

## Troubleshooting

1. **Check if dnspython is installed:**
   ```bash
   python -c "import dns.resolver; print('OK')"
   ```

2. **Test DNS resolution:**
   ```bash
   python -m linkedin_api.dns_utils
   ```

3. **Verify VPN DNS servers:**
   ```bash
   scutil --dns | grep nameserver
   ```

4. **Test direct DNS query:**
   ```bash
   dig @8.8.8.8 europe-west9-aiplatform.googleapis.com
   ```

## How It Works

The DNS fix works by:

1. **Environment Variables**: Sets `DNS_SERVERS` and `GRPC_DNS_RESOLVER` that some libraries respect
2. **Socket Patching**: Intercepts `socket.getaddrinfo()` calls and resolves hostnames using Google DNS servers directly
3. **Fallback**: If custom DNS resolution fails, falls back to system DNS

This ensures that even if your VPN's DNS servers can't resolve GCP endpoints, the application will use reliable public DNS servers.
