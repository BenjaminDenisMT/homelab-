#!/usr/bin/env python3
import subprocess
import json
import paho.mqtt.client as mqtt

MQTT_HOST = "127.0.0.1"
MQTT_PORT = 1883
MQTT_USER = ""
MQTT_PASS = ""
METER_ID = "79204985"

client = mqtt.Client()
if MQTT_USER:
    client.username_pw_set(MQTT_USER, MQTT_PASS)
client.connect(MQTT_HOST, MQTT_PORT)
client.loop_start()

# MQTT auto-discovery pour Home Assistant
discovery = {
    "name": "Gas Meter",
    "state_topic": "homeassistant/sensor/gas_meter/state",
    "unit_of_measurement": "m³",
    "icon": "mdi:fire",
    "unique_id": "gas_meter_79204985",
    "device_class": "gas",
    "state_class": "total_increasing"
}
client.publish(
    "homeassistant/sensor/gas_meter/config",
    json.dumps(discovery),
    retain=True
)

# Lance rtlamr et pipe le output
cmd = [
    "/home/ben/go/bin/rtlamr",
    "-centerfreq=915000000",
    "-symbollength=32",
    "-tunergainmode=true",
    "-tunergain=40",
    "-msgtype=scm+",
    "-filterid=" + METER_ID,
    "-format=json"
]

proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)

print("Listening for meter", METER_ID)
for line in proc.stdout:
    line = line.strip()
    if not line:
        continue
    try:
        data = json.loads(line)
        consumption = data["Message"]["Consumption"] / 100
        print(f"Consumption: {consumption} m³")
        client.publish(
            "homeassistant/sensor/gas_meter/state",
            str(consumption),
            retain=True,
        )
    except Exception as e:
        print("Skip:", line[:80])
