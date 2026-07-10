---
title: Dispatcharr Integration
parent: User Guide
nav_order: 3
docs_version: "2.3.1"
---

# Dispatcharr Integration

Apex creates and manages channels in Dispatcharr automatically. This guide covers initial setup and how the integration works day-to-day.

## Initial Setup

### 1. Connect to Dispatcharr

1. Go to **Settings > Dispatcharr**
2. Enable the integration toggle
3. Enter your Dispatcharr URL (e.g., `http://dispatcharr:9191`)
4. Enter your Dispatcharr username and password
5. Click **Test** to verify the connection shows "Connected"
6. Click **Save**

### 2. Set Up EPG Source

1. Go to the **EPG** page in Apex and copy the **XMLTV URL** (e.g., `http://apex:9195/api/v1/epg/xmltv`)
2. In **Dispatcharr**, add a new EPG source using that URL
3. Back in **Apex Settings > Dispatcharr**, select your Apex EPG source from the dropdown
4. Click **Save**

### 3. Configure Defaults

While still in Settings > Dispatcharr, configure:

- **Default Channel Profiles** — which Dispatcharr profiles Apex channels appear in
- **Default Stream Profile** — which stream profile to assign to streams
- **Default Channel Group** — which channel group to assign channels to (static, dynamic by sport/league, or custom pattern)

See [Settings > Dispatcharr](settings/dispatcharr) for details on each option.

## How It Works

Once connected, Apex manages the full channel lifecycle in Dispatcharr:

1. **EPG Generation** runs (manually or on schedule)
2. Apex matches streams to events and resolves templates
3. **Channels are created** in Dispatcharr with names, logos, EPG data, streams, and profile/group assignments
4. **Channels are updated** when event data changes (scores, status, streams)
5. **Channels are deleted** when events end (based on [lifecycle timing](settings/channels#channel-lifecycle))

### M3U Account Refresh

Before matching streams, Apex refreshes your M3U accounts in Dispatcharr to get the latest stream data. This happens automatically at the start of each EPG generation run.

### Profile & Group Sync

Apex enforces profile and group assignments on every generation run. If someone manually changes a channel's profiles in Dispatcharr, Apex will correct it on the next run. This self-healing behavior ensures your configuration stays consistent.

Dynamic wildcards (`{sport}`, `{league}`) automatically create profiles and groups in Dispatcharr if they don't exist.

### Reconciliation

The [Channels page](channels) can detect drift between Apex's expected state and Dispatcharr's actual state:

- **Drifted** channels have mismatched profiles, streams, or settings — corrected on next generation
- **Orphaned** channels exist in Dispatcharr but aren't tracked by Apex — can be cleaned up manually

## Network Configuration

Apex and Dispatcharr need to be able to reach each other over the network.

### Docker Compose (Same Host)

If both containers are on the same Docker network, use the container name as the hostname:

```yaml
# Apex Settings > Dispatcharr URL:
http://dispatcharr:9191

# Dispatcharr EPG source URL:
http://apex:9195/api/v1/epg/xmltv
```

### Separate Hosts

Use the IP address or hostname of each server:

```
# Apex → Dispatcharr
http://192.168.1.100:9191

# Dispatcharr → Apex EPG
http://192.168.1.101:9195/api/v1/epg/xmltv
```

## Troubleshooting Connection Issues

| Problem | Solution |
|---------|----------|
| "Disconnected" status | Verify the URL is correct and Dispatcharr is running. Check Docker networking. |
| "Error" status | Hover over the badge for details. Common causes: wrong credentials, firewall blocking port. |
| EPG source dropdown empty | Make sure you've added the Apex XMLTV URL as an EPG source in Dispatcharr first. |
| Channels not appearing | Run EPG generation. Check that you have templates assigned and streams available. |
