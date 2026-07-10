# Apex

Motorsports EPG Generator for Dispatcharr

A motorsports-only fork of [Teamarr](https://github.com/Pharaoh-Labs/teamarr) (formerly Vroomarr), covering F1, F2, F3, NASCAR (Cup/O'Reilly Auto Parts/Trucks), IndyCar, IMSA, and WEC.

## Quick Start

Pull and run the published image:

```bash
git clone https://github.com/tomwinterrose/apex.git
cd apex
docker compose up -d
```

This pulls `ghcr.io/tomwinterrose/apex:latest` and starts it on port `9198` (see `docker-compose.yml`). Images are built for `linux/amd64` and `linux/arm64` and published automatically on every push to `main`.

To build from source instead:

```bash
docker build -t apex:local .
```

## License

MIT
