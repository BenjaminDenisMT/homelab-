"""
Thin Home Assistant REST API client.
Docs: https://developers.home-assistant.io/docs/api/rest/
"""

import httpx
from homelab.config import settings


class HAClient:
    """Synchronous HA REST client (use async_client() for async code)."""

    def __init__(self, base_url: str | None = None, token: str | None = None):
        self.base_url = (base_url or settings.ha.base_url).rstrip("/")
        self._token = token or settings.ha.token
        self._headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------ #
    # Generic helpers                                                       #
    # ------------------------------------------------------------------ #

    def get_state(self, entity_id: str) -> dict:
        """Return the current state object for an entity."""
        r = httpx.get(
            f"{self.base_url}/api/states/{entity_id}",
            headers=self._headers,
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    def set_state(self, entity_id: str, state: str, attributes: dict | None = None) -> dict:
        r = httpx.post(
            f"{self.base_url}/api/states/{entity_id}",
            headers=self._headers,
            json={"state": state, "attributes": attributes or {}},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    def call_service(self, domain: str, service: str, data: dict | None = None) -> list:
        r = httpx.post(
            f"{self.base_url}/api/services/{domain}/{service}",
            headers=self._headers,
            json=data or {},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------------ #
    # Convenience methods for this homelab                                  #
    # ------------------------------------------------------------------ #

    def get_gas_consumption(self) -> float | None:
        """Latest Énergir gas meter reading in m³ (from rtlamr → MQTT → HA)."""
        try:
            s = self.get_state("sensor.energir_gas_consumption")
            return float(s["state"])
        except Exception:
            return None

    def get_hydro_consumption(self) -> dict:
        """HydroQC electricity consumption sensors."""
        sensors = {
            "total": settings.hydro.total_consumption_sensor,
            "bill_to_date": settings.hydro.bill_total_sensor,
        }
        result = {}
        for key, entity_id in sensors.items():
            try:
                s = self.get_state(entity_id)
                result[key] = {"state": s["state"], "unit": s["attributes"].get("unit_of_measurement")}
            except Exception as e:
                result[key] = {"error": str(e)}
        return result

    def get_mini_split_status(self) -> dict:
        """Current state of both Carrier mini-splits."""
        cfg = settings.mini_splits
        entities = {
            "chambre": cfg.chambre_entity,
            "cuisine": cfg.cuisine_entity,
        }
        humidity_entities = {
            "chambre": cfg.chambre_humidity,
            "cuisine": cfg.cuisine_humidity,
        }
        result = {}
        for room, entity_id in entities.items():
            try:
                s = self.get_state(entity_id)
                h = self.get_state(humidity_entities[room])
                result[room] = {
                    "hvac_mode": s["state"],
                    "temperature": s["attributes"].get("temperature"),
                    "current_temperature": s["attributes"].get("current_temperature"),
                    "fan_mode": s["attributes"].get("fan_mode"),
                    "humidity_pct": float(h["state"]) if h["state"] not in ("unavailable", "unknown") else None,
                }
            except Exception as e:
                result[room] = {"error": str(e)}
        return result

    def set_mini_split_mode(self, room: str, hvac_mode: str) -> dict:
        """
        Set mini-split mode.
        room: 'chambre' | 'cuisine'
        hvac_mode: 'heat' | 'cool' | 'dry' | 'fan_only' | 'off'
        """
        cfg = settings.mini_splits
        entity_id = cfg.chambre_entity if room == "chambre" else cfg.cuisine_entity
        return self.call_service("climate", "set_hvac_mode", {
            "entity_id": entity_id,
            "hvac_mode": hvac_mode,
        })

    def ping(self) -> bool:
        try:
            r = httpx.get(f"{self.base_url}/api/", headers=self._headers, timeout=5)
            return r.status_code == 200
        except Exception:
            return False
