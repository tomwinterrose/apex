# Vroomarr

Motorsports EPG Generator for Dispatcharr

A motorsports-only fork of [Teamarr](https://github.com/Pharaoh-Labs/teamarr), covering F1, NASCAR (Cup/O'Reilly Auto Parts/Trucks), IndyCar, IMSA, and WEC.

## Quick Start

No prebuilt image is published yet — build and run from source:

```bash
git clone https://github.com/tomwinterrose/vroomarr.git
cd vroomarr
docker compose up -d --build
```

This builds the image locally from the included `Dockerfile` and starts it on port `9198` (see `docker-compose.yml`).

## License

MIT
