# homelab – 81 Logan, Saint-Lambert

Raspberry Pi 5 homelab management package.

## Services tracked

| Service | Address | Notes |
|---|---|---|
| Mosquitto MQTT | 192.168.1.23:1883 (also 127.0.0.1) | Broker for all IoT messages |
| Home Assistant | http://192.168.1.23:8123 | Docker, /home/ben/homeassistant |
| Gas meter reader | 2x native systemd (NOT Docker) | RTL-SDR Blog V4 → SCM+ → MQTT |
| ESPHome chambre | 192.168.1.49 | CloudFree SLWF-01Pro, Carrier mini-split |
| ESPHome cuisine | 192.168.1.50 | CloudFree SLWF-01Pro, Carrier mini-split |
| HydroQC HACS | HA sensor | 800+ days electricity history |

## Gas meter

- **Device**: Itron 100G DLS ERT module (exterior-mounted)
- **Serial**: 1279204985 (meter transmits as 8-digit `79204985`)
- **Protocol**: SCM+ (10-digit Itron)
- **Frequency**: ~912.6 MHz (observed center 912,600,155 Hz)
- **Hardware**: RTL-SDR Blog V4 (R828D tuner)

**Production pipeline (native systemd, not Docker):**

```
rtl_tcp.service  (scripts/systemd/rtl_tcp.service)
    → owns the RTL-SDR dongle exclusively, always-on TCP SDR server
rtlamr.service   (scripts/systemd/rtlamr.service)
    → runs scripts/rtlamr_mqtt.py, connects to rtl_tcp over 127.0.0.1:1234,
      decodes SCM+, publishes to homeassistant/sensor/gas_meter/{config,state}
      via MQTT at 127.0.0.1:1883 (retained, as of 2026-10-28)
```

Successful captures happen roughly once a day (SCM+ bursts), not continuously —
that's expected, not a fault.

> ⚠️ **docker-compose.yml's `rtlamr` service is NOT used in production** — it's
> a half-finished migration attempt that conflicts with the setup above (both
> try to claim the same USB dongle). It's commented out in docker-compose.yml.
> Do not re-enable it without first stopping `rtlamr.service`/`rtl_tcp.service`
> on the Pi, or without finishing the migration and decommissioning the
> systemd services.

> ⚠️ **Known issue**: unfiltered/multi-protocol decoding (`-msgtype=all`)
> causes `"not keeping up with rtl_tcp"` at ~2.2M sample rate — the Pi ARM64
> can't decode 4 protocols simultaneously. The production script already
> filters to a single protocol (`-msgtype=scm+ -filterid=79204985`).

> ⚠️ **2026-10-17 outage root cause**: Wi-Fi roaming hiccups on the mesh
> network changed the Pi's IP. Home Assistant's MQTT integration was
> hardcoded to the Pi's old address (`192.168.1.32`) instead of `127.0.0.1`,
> so it silently stopped receiving gas meter updates even though the Pi kept
> publishing successfully the whole time. Fix in progress: repoint HA's MQTT
> broker config to `127.0.0.1` (`.storage/core.config_entries` on the Pi).

## Quick start

```bash
# From WSL / Windows
./scripts/deploy.sh                  # rsync + pip install on Pi

# On the Pi
source .venv/bin/activate
homelab status                       # check all services
homelab mqtt monitor                 # live MQTT stream
homelab mqtt gas-watch               # watch for gas readings
homelab rtl diag                     # scan rtlamr logs for issues
homelab energy track                 # start gas + hydro tracker
homelab energy report --days 7       # last 7 days summary
homelab ha status                    # mini-splits + HydroQC
```

## Environment variables

Copy `.env.example` → `.env` and fill in your HA long-lived token:

```bash
cp .env.example .env
# Edit .env: set HA_TOKEN=<token from HA profile page>
```

## Docker

```bash
docker compose up -d          # start mosquitto, homeassistant, rtlamr, esphome
docker compose logs -f rtlamr # follow gas meter logs
```
