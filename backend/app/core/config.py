"""환경변수. 판정·계산 상수는 app/domain/ 에 있다 (§11.1 공통 계약)."""
import os
from zoneinfo import ZoneInfo

env = os.getenv

DATABASE_URL = env("DATABASE_URL", "postgresql://dg:dg@localhost:5432/dg")

MQTT_HOST = env("MQTT_HOST", "localhost")
MQTT_PORT = int(env("MQTT_PORT", "1883"))
MQTT_USER = env("MQTT_USER") or None
MQTT_PASS = env("MQTT_PASS") or None
MQTT_TLS = env("MQTT_TLS", "false").lower() == "true"  # HiveMQ Cloud = true, 8883

API_TOKEN = env("API_TOKEN", "")  # 비어 있으면 인증 생략 (로컬 개발)
CORS_ORIGINS = env("CORS_ORIGINS", "http://localhost:3000").split(",")

# 외기온 (§4.5)
REGION_CODE = env("REGION_CODE", "seoul")
KMA_AUTH_KEY = env("KMA_AUTH_KEY", "")
KMA_STN = env("KMA_STN", "108")
LAT = float(env("LAT", "37.5714"))
LON = float(env("LON", "126.9658"))

# Web Push (§9.7)
VAPID_PRIVATE_KEY = env("VAPID_PRIVATE_KEY", "")
VAPID_PUBLIC_KEY = env("VAPID_PUBLIC_KEY", "")
VAPID_SUBJECT = env("VAPID_SUBJECT", "mailto:team@example.com")

TZ = ZoneInfo("Asia/Seoul")
