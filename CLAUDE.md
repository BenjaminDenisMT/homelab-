# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Management tooling for a Raspberry Pi 5 homelab at 81 Logan, Saint-Lambert: Home Assistant, Mosquitto MQTT, ESPHome-flashed mini-splits, an Énergir gas meter read via RTL-SDR, and a HydroQC electricity integration. The repo is split between infra config (`docker-compose.yml`, `config/`) deployed to the Pi, and a local Python CLI package (`homelab/`) for querying/monitoring those services from a dev machine.

This repo is developed from Windows/WSL and deployed to the Pi over SSH — it is not run directly on the dev machine except for the `homelab` CLI itself (which talks to the Pi's services over the network).

## Commands

```bash
# Deploy local changes to the Pi (rsync + pip install -e, from WSL/Windows)
./scripts/deploy.sh                  # defaults to ben@192.168.1.23
./scripts/deploy.sh ben@<other-host>

# homelab CLI (run on the Pi, inside the venv deploy.sh creates)
source .venv/bin/activate
homelab status                       # service reachability table
homelab mqtt monitor [--topic/-t ...]
homelab mqtt gas-watch
homelab energy track [--block/--no-block]
homelab energy report --days 7
homelab ha status
homelab rtl diag [--container/-c] [--tail/-n] [--file/-f]

# Docker services on the Pi
docker compose up -d
docker compose logs -f <service>
docker compose restart <service>

# Lint (ruff is a dev dependency; no CI config exists yet)
ruff check .
```

There is no test suite yet (`pytest`/`pytest-asyncio` are declared as dev dependencies in `pyproject.toml` but no test files exist).

## Architecture

### Config and settings

All runtime config is centralized in `homelab/config.py` as pydantic-settings classes (`MQTTSettings`, `HomeAssistantSettings`, `RTLSDRSettings`, `MiniSplitSettings`, `HydroQCSettings`), composed into a single `settings` singleton. Every value has a hardcoded default (the actual Pi/device addresses) and can be overridden via env vars (see `.env.example` for the prefixes: `MQTT_`, `HA_`, `RTLSDR_`, `MINISPLIT_`, `HYDROQC_`) or a `.env` file. Import `from homelab.config import settings` rather than reading env vars directly.

### CLI structure

`homelab/cli/main.py` is a Typer app with sub-apps (`mqtt`, `energy`, `ha`, `rtl`) that lazily import from `homelab/services/*` inside each command function (keeps `homelab --help` fast). Each service module is independent and can be used as a library outside the CLI:

- `ha_client.py` — thin synchronous HA REST client (`get_state`/`set_state`/`call_service` plus convenience methods for mini-splits, HydroQC, gas).
- `mqtt_monitor.py` — generic MQTT listener (`listen()`) plus `GasMeterWatcher`, a stateful subscriber that accumulates gas readings.
- `energy_tracker.py` — combines `GasMeterWatcher` (MQTT, push) with periodic `HAClient` polls (REST, pull) into daily JSON summaries under `~/.homelab/energy/YYYY-MM-DD.json`.
- `rtlsdr_diag.py` — regex-based log analyzer for known RTL-SDR/rtlamr failure patterns, with a `KNOWN_FIXES` lookup table.

### ⚠️ Two gas-meter pipelines exist — only one is real

This is the most important thing to know before touching anything gas-meter related. There are **two separate, non-interoperable implementations** of "RTL-SDR → MQTT → Home Assistant" for the gas meter, and they use different MQTT topics and HA entity IDs:

| | Docker `rtlamr2mqtt` (NOT production) | Native systemd (production) |
|---|---|---|
| Where | `docker-compose.yml`'s `rtlamr` service (commented out) | `scripts/systemd/{rtl_tcp,rtlamr}.service` + `scripts/rtlamr_mqtt.py` on the Pi |
| Config | `config/rtlamr.yml` → `/home/ben/rtlamr/config.yml` | hardcoded in `scripts/rtlamr_mqtt.py` |
| MQTT topic | `rtlamr/energir_gas` | `homeassistant/sensor/gas_meter/state` |
| HA entity | `sensor.energir_gas_consumption` | `sensor.gas_meter` |
| Meter ID format | `1279204985` (10-digit) | `79204985` (8-digit) |

**The `homelab` Python package (`mqtt_monitor.py`'s `WATCHED_TOPICS`/`GasMeterWatcher`, `rtlsdr_diag.py`'s `docker logs rtlamr` calls, `ha_client.py`'s `get_gas_consumption()`) was written against the Docker pipeline, which was never actually deployed.** `homelab mqtt gas-watch`, `homelab energy track`, and `homelab rtl diag` will silently see nothing from the real gas meter, because they're listening on the wrong topic/container. If you're asked to fix or extend gas-meter tooling, either point it at the real topic/entity (right column above) or finish the Docker migration and decommission the systemd services — don't assume the existing code is wired to the live system.

The two pipelines also physically conflict: both want exclusive USB access to the single RTL-SDR dongle. Never run the Docker `rtlamr` container while `rtlamr.service`/`rtl_tcp.service` are enabled on the Pi (and vice versa) — confirmed by observation to cause USB resets and dropped decodes on whichever side loses the race.

### Deployment model

`scripts/deploy.sh` rsyncs the repo to `/home/ben/homelab` on the Pi and `pip install -e .` into a venv there. It does **not** deploy `docker-compose.yml`, the systemd unit files, or `scripts/rtlamr_mqtt.py` to their live locations (`/etc/systemd/system/`, `/home/ben/rtlamr_mqtt.py`) — those are tracked here for reference/history but must be copied into place and `systemctl daemon-reload`'d manually. The one exception: deploy.sh symlinks `config/rtlamr.yml` to `/home/ben/rtlamr/config.yml`, but only if that file doesn't already exist — it will not overwrite local edits made directly on the Pi, so the repo and the live file can silently drift (this has happened before; verify with `ssh <pi> cat /home/ben/rtlamr/config.yml` before assuming the repo copy is current).

Home Assistant's own config (`/home/ben/homeassistant`, mounted into the `homeassistant` container) is not tracked in this repo at all — it's managed entirely through the HA UI/`.storage` on the Pi.
