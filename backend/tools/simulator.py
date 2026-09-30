"""가상 센서 퍼블리셔 (§11.2). 하드웨어 없이 파이프라인 전체를 돌린다.

  python tools/simulator.py --scenario mould --speed 60    # 5시간 곡선을 5분에 재생
  python tools/simulator.py --scenario steady              # 실시간 30초 간격

MQTT 접속은 서버와 같은 환경변수(MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASS, MQTT_TLS)를 쓴다.
운영 브로커(HiveMQ)에 직접 붙여 개발할 것 — v1.1 원칙.
"""
import argparse
import json
import math
import os
import random
import time

import paho.mqtt.client as mqtt

STEP = 30  # 초


def mould(i: int) -> tuple[float, float, float]:
    """습도 서서히 상승 → ALERT → 결로 → 환기 후 회복. (t_air, rh, t_surf) 반환."""
    h = i * STEP / 3600
    if h < 1:
        rh = 50
    elif h < 3:
        rh = 50 + (h - 1) * 12.5    # 2시간에 50→75
    elif h < 4:
        rh = 75                      # RHs 100 부근 (결로)
    else:
        rh = 45 + 30 * math.exp(-(h - 4) * 3)  # 환기
    return 20.0, rh, 15.0


def steady(i: int) -> tuple[float, float, float]:
    return 21.0, 45.0, 17.0


SCENARIOS = {"mould": (mould, 5 * 3600 // STEP), "steady": (steady, 10**9)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", choices=SCENARIOS, default="mould")
    ap.add_argument("--speed", type=float, default=1.0, help="재생 배속")
    ap.add_argument("--home", default="home-a")
    ap.add_argument("--device", default="dev-sim-1")
    a = ap.parse_args()

    base = f"dg/v1/{a.home}/{a.device}"
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=a.device)
    if os.getenv("MQTT_USER"):
        c.username_pw_set(os.getenv("MQTT_USER"), os.getenv("MQTT_PASS"))
    if os.getenv("MQTT_TLS", "false").lower() == "true":
        c.tls_set()
    c.will_set(f"{base}/status", "offline", qos=1, retain=True)  # LWT (§8.2)
    c.connect(os.getenv("MQTT_HOST", "localhost"), int(os.getenv("MQTT_PORT", "1883")))
    c.loop_start()
    c.publish(f"{base}/status", "online", qos=1, retain=True)

    fn, steps = SCENARIOS[a.scenario]
    # 배속 재생이어도 타임스탬프가 벽시계를 앞지르지 않도록 과거에서 시작해 '지금'에 끝나게 한다
    t0 = time.time() - (steps * STEP * (1 - 1 / a.speed) if steps < 10**9 else 0)
    for i in range(steps):
        ta, rh, ts = fn(i)
        payload = {
            "v": 1, "ts": int(t0 + i * STEP), "seq": i,
            "t_air": round(ta + random.gauss(0, 0.1), 2),
            "rh": round(rh + random.gauss(0, 0.8), 1),
            "t_surf": [round(ts + random.gauss(0, 0.05), 2), round(ts + 1.2 + random.gauss(0, 0.05), 2)],
            "probe_ids": ["28ff000001", "28ff000002"], "rssi": -60, "fw": "sim",
        }
        c.publish(f"{base}/telemetry", json.dumps(payload), qos=1)
        print(payload["ts"], payload["rh"], payload["t_surf"])
        time.sleep(STEP / a.speed)
    c.loop_stop()


if __name__ == "__main__":
    main()
