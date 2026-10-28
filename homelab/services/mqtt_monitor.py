"""
MQTT monitor – subscribes to all homelab topics and pretty-prints live traffic.
Run:  homelab mqtt monitor
      homelab mqtt monitor --topic homeassistant/#
"""

import json
import threading
from datetime import datetime
from typing import Callable

import paho.mqtt.client as mqtt
from rich.console import Console
from rich.table import Table

from homelab.config import settings

console = Console()

# Topics we care about
WATCHED_TOPICS = [
    "rtlamr/energir_gas/#",          # Gas meter readings
    "homeassistant/sensor/#",         # HA discovery payloads
    "homeassistant/climate/#",        # Mini-split state
    "esphome/#",                      # ESPHome device events
]


def _on_connect(client: mqtt.Client, userdata, flags, rc, properties=None):
    if rc == 0:
        console.print(f"[green]✓ Connected to MQTT broker {settings.mqtt.host}:{settings.mqtt.port}[/green]")
        for topic in userdata["topics"]:
            client.subscribe(topic)
            console.print(f"  Subscribed → [cyan]{topic}[/cyan]")
    else:
        console.print(f"[red]✗ MQTT connect failed, rc={rc}[/red]")


def _on_message(client: mqtt.Client, userdata, msg: mqtt.MQTTMessage):
    ts = datetime.now().strftime("%H:%M:%S")
    payload = msg.payload.decode("utf-8", errors="replace")

    # Try to pretty-print JSON
    try:
        data = json.loads(payload)
        payload_display = json.dumps(data, indent=None, ensure_ascii=False)
    except (json.JSONDecodeError, ValueError):
        payload_display = payload[:120]

    # Colour by topic prefix
    topic = msg.topic
    if "energir_gas" in topic:
        colour = "yellow"
    elif "climate" in topic:
        colour = "blue"
    elif "esphome" in topic:
        colour = "magenta"
    else:
        colour = "white"

    console.print(f"[dim]{ts}[/dim] [{colour}]{topic}[/{colour}]  {payload_display}")

    # Call any registered handlers
    for handler in userdata.get("handlers", []):
        handler(topic, payload)


def listen(
    topics: list[str] | None = None,
    on_message: Callable[[str, str], None] | None = None,
    block: bool = True,
) -> mqtt.Client:
    """
    Start an MQTT listener.

    Parameters
    ----------
    topics:     List of MQTT topic filters. Defaults to WATCHED_TOPICS.
    on_message: Optional callback(topic, payload_str) for each message.
    block:      If True, blocks the calling thread.
    """
    topics = topics or WATCHED_TOPICS
    handlers = [on_message] if on_message else []

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        userdata={"topics": topics, "handlers": handlers},
    )
    client.on_connect = _on_connect
    client.on_message = _on_message

    if settings.mqtt.username:
        client.username_pw_set(settings.mqtt.username, settings.mqtt.password)

    client.connect(settings.mqtt.host, settings.mqtt.port, keepalive=60)

    if block:
        client.loop_forever()
    else:
        t = threading.Thread(target=client.loop_forever, daemon=True)
        t.start()

    return client


class GasMeterWatcher:
    """
    Watches the rtlamr MQTT topic and accumulates readings.

    Usage::

        watcher = GasMeterWatcher()
        watcher.start()
        # … later …
        print(watcher.latest)
    """

    TOPIC = f"rtlamr/energir_gas"

    def __init__(self):
        self.latest: dict | None = None
        self.readings: list[dict] = []
        self._client: mqtt.Client | None = None

    def _handle(self, topic: str, payload: str):
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return
        data["_received_at"] = datetime.now().isoformat()
        self.latest = data
        self.readings.append(data)
        console.print(
            f"[yellow]⛽ Gas meter[/yellow] "
            f"consumption={data.get('Consumption', '?')} m³  "
            f"id={data.get('ID', '?')}"
        )

    def start(self, block: bool = False) -> "GasMeterWatcher":
        self._client = listen(
            topics=[f"{self.TOPIC}/#", f"{self.TOPIC}"],
            on_message=self._handle,
            block=block,
        )
        return self
