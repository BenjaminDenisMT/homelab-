"""
Central configuration for the 81 Logan homelab.
All values can be overridden via environment variables or a .env file.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class MQTTSettings(BaseSettings):
    host: str = Field("192.168.1.23", description="Mosquitto broker IP (Pi static)")
    port: int = 1883
    username: str = ""
    password: str = ""

    model_config = SettingsConfigDict(env_prefix="MQTT_")


class HomeAssistantSettings(BaseSettings):
    base_url: str = Field("http://192.168.1.23:8123", description="HA instance URL")
    token: str = Field("", description="Long-lived access token")

    model_config = SettingsConfigDict(env_prefix="HA_")


class RTLSDRSettings(BaseSettings):
    meter_id: int = Field(1279204985, description="Énergir ERT module serial (Itron 100G DLS)")
    protocol: str = "scm+"                   # SCM+ = 10-digit Itron
    sample_rate: int = 2_048_000
    center_freq_hz: int = 912_600_155        # Observed from rtlamr logs
    filter_id: int = 1279204985             # Set to 0 to scan all meters nearby

    model_config = SettingsConfigDict(env_prefix="RTLSDR_")


class MiniSplitSettings(BaseSettings):
    """Carrier 38MGRQ24C-3 system – 2× CloudFree SLWF-01Pro ESPHome dongles."""
    chambre_entity: str = "climate.air_conditioner_fd4038_air_conditioner"
    chambre_humidity: str = "sensor.air_conditioner_fd4038_air_conditioner_indoor_humidity"
    chambre_ip: str = "192.168.1.49"

    cuisine_entity: str = "climate.kitchen_carrier_cuisine_air_conditioner"
    cuisine_humidity: str = "sensor.kitchen_carrier_cuisine_air_conditioner_indoor_humidity"
    cuisine_ip: str = "192.168.1.50"

    # Humidity thresholds for auto Dry/Cool switching
    humidity_dry_threshold: float = 50.0    # Switch to Dry above this
    humidity_cool_threshold: float = 50.0   # Switch back to Cool below this

    model_config = SettingsConfigDict(env_prefix="MINISPLIT_")


class HydroQCSettings(BaseSettings):
    """HydroQC HACS integration sensors."""
    total_consumption_sensor: str = "sensor.hydro_quebec_maison_total_consumption"
    bill_total_sensor: str = "sensor.hydro_quebec_maison_bill_total_to_date"
    hourly_sensor: str = "sensor.hydro_quebec_maison_hourly_consumption"

    model_config = SettingsConfigDict(env_prefix="HYDROQC_")


class Settings(BaseSettings):
    mqtt: MQTTSettings = Field(default_factory=MQTTSettings)
    ha: HomeAssistantSettings = Field(default_factory=HomeAssistantSettings)
    rtlsdr: RTLSDRSettings = Field(default_factory=RTLSDRSettings)
    mini_splits: MiniSplitSettings = Field(default_factory=MiniSplitSettings)
    hydro: HydroQCSettings = Field(default_factory=HydroQCSettings)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )


# Singleton – import this throughout the project
settings = Settings()
