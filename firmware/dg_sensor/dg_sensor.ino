// 결로 센서 펌웨어 (§8, 계약 §9.2). 보드: ESP32 Dev Module
// 라이브러리 관리자에서 설치: PubSubClient, DHT sensor library(Adafruit), OneWire, DallasTemperature
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <time.h>
#include "isrg_root_x1.h"

// ---- 여기만 채우면 됨 (비밀번호를 넣은 채로 커밋하지 말 것) ----
const char* WIFI_SSID = "";          // 2.4GHz 와이파이만 됨
const char* WIFI_PASS = "";
const char* MQTT_HOST = "";          // HiveMQ Cloud Cluster URL (예: abcd1234.s1.eu.hivemq.cloud)
const uint16_t MQTT_PORT = 8883;     // HiveMQ = 8883(TLS). 서버 PC 로컬 브로커로 테스트할 때만 1883 + MQTT_HOST에 PC IP
const char* MQTT_USER = "";          // HiveMQ 기기용 계정 (예: dg-device). 로컬 브로커면 비워둠
const char* MQTT_PASS = "";
const char* HOME_ID = "home-a";
const char* FW = "0.2";
// -----------------------------------------------------------

const uint8_t PIN_DHT = 4, PIN_ONEWIRE = 5;  // §8 핀맵. DS18B20 버스에 4.7kΩ 풀업 필수
const uint32_t SAMPLE_MS = 30000;
const int MAX_PROBES = 4;

DHT dht(PIN_DHT, DHT22);
OneWire ow(PIN_ONEWIRE);
DallasTemperature ds(&ow);
WiFiClient plainNet;
WiFiClientSecure tlsNet;
PubSubClient mqtt;

DeviceAddress addr[MAX_PROBES];
char probeId[MAX_PROBES][17];
int nProbes = 0;
char devId[16], base[48];

// 모든 샘플은 버퍼를 거쳐 나간다 — 끊겨 있던 동안의 데이터도 재접속 후 순서대로 올라감 (§8.2)
struct Sample { uint32_t ts, seq; float t_air, rh, t_surf[MAX_PROBES]; };
const int BUF_N = 720;  // 30초 × 720 = 6시간. 넘치면 가장 오래된 것부터 덮어씀
Sample buf[BUF_N];
int head = 0, count = 0;  // head = 가장 오래된 샘플
uint32_t seq = 0;

void push(const Sample& s) {
  buf[(head + count) % BUF_N] = s;
  if (count < BUF_N) count++; else head = (head + 1) % BUF_N;
}

int fmt(char* q, float v, int digits) {  // 센서 읽기 실패(NaN) → null
  return isnan(v) ? sprintf(q, "null") : sprintf(q, "%.*f", digits, v);
}

bool send(const Sample& s) {
  char p[400], *q = p, t[64];
  q += sprintf(q, "{\"v\":1,\"ts\":%lu,\"seq\":%lu,\"t_air\":", (unsigned long)s.ts, (unsigned long)s.seq);
  q += fmt(q, s.t_air, 2);
  q += sprintf(q, ",\"rh\":");
  q += fmt(q, s.rh, 1);
  q += sprintf(q, ",\"t_surf\":[");
  for (int i = 0; i < nProbes; i++) { if (i) *q++ = ','; q += fmt(q, s.t_surf[i], 2); }
  q += sprintf(q, "],\"probe_ids\":[");
  for (int i = 0; i < nProbes; i++) q += sprintf(q, "%s\"%s\"", i ? "," : "", probeId[i]);
  sprintf(q, "],\"rssi\":%d,\"fw\":\"%s\"}", WiFi.RSSI(), FW);
  snprintf(t, sizeof t, "%s/telemetry", base);
  return mqtt.publish(t, p);
}

void connectMqtt() {
  char st[64];
  snprintf(st, sizeof st, "%s/status", base);
  const char* user = *MQTT_USER ? MQTT_USER : nullptr;  // 빈 아이디는 '계정 없음'으로 보냄
  if (mqtt.connect(devId, user, MQTT_PASS, st, 1, true, "offline")) {  // LWT: 끊기면 브로커가 offline 발행
    mqtt.publish(st, "online", true);
    Serial.println("MQTT 연결됨");
  } else {
    // -2: 주소·포트·인증서 문제 / 4·5: 아이디·비번 틀림
    Serial.printf("MQTT 실패 state=%d — 가이드의 '문제 해결' 표 참고\n", mqtt.state());
  }
}

void sample() {
  Sample s{(uint32_t)time(nullptr), seq++, dht.readTemperature(), dht.readHumidity()};
  ds.requestTemperatures();  // 12bit 변환 750ms 대기
  for (int i = 0; i < nProbes; i++) s.t_surf[i] = ds.getTempC(addr[i]);  // 끊기면 -127 → 서버가 해당 프로브만 버림
  push(s);
  Serial.printf("ts=%lu Ta=%.2f RH=%.1f Ts0=%.2f 대기=%d\n", (unsigned long)s.ts, s.t_air, s.rh, s.t_surf[0], count);
}

void setup() {
  Serial.begin(115200);
  // 같은 코드를 두 보드에 올려도 ID가 겹치지 않게 MAC에서 만든다
  snprintf(devId, sizeof devId, "dev-%06llx", (ESP.getEfuseMac() >> 24) & 0xFFFFFF);
  snprintf(base, sizeof base, "dg/v1/%s/%s", HOME_ID, devId);
  Serial.printf("\n기기 ID: %s\n", devId);
  if (!*WIFI_SSID || !*MQTT_HOST) {  // 설정 안 채운 채 업로드한 경우
    Serial.println("WIFI_SSID / MQTT_HOST가 비어 있음 — 파일 맨 위 설정을 채우고 다시 업로드");
    while (true) delay(1000);
  }

  dht.begin();
  ds.begin();
  int n = ds.getDeviceCount();
  nProbes = n < MAX_PROBES ? n : MAX_PROBES;
  for (int i = 0; i < nProbes; i++) {
    ds.getAddress(addr[i], i);
    for (int b = 0; b < 8; b++) sprintf(probeId[i] + b * 2, "%02x", addr[i][b]);
    Serial.printf("프로브 %d: %s\n", i, probeId[i]);
  }
  if (!nProbes) Serial.println("DS18B20 0개 — 배선·4.7kΩ 풀업 확인 (이대로면 서버가 전부 거부)");

  WiFi.begin(WIFI_SSID, WIFI_PASS);  // 이후 끊기면 ESP32가 알아서 재접속
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print('.'); }
  Serial.printf("\nWiFi 연결, IP %s\n", WiFi.localIP().toString().c_str());

  configTime(0, 0, "pool.ntp.org", "time.google.com");
  while (time(nullptr) < 1700000000) delay(500);  // 동기화 전 시각(1970년)은 서버가 버린다
  Serial.println("시간 동기화 완료");

  if (MQTT_PORT == 8883) {  // TLS는 시간이 맞아야 인증서 검사가 통과하므로 NTP 뒤에 둔다
    tlsNet.setCACert(ISRG_ROOT_X1);  // 접속이 안 될 때 원인 가리기용으로만: tlsNet.setInsecure();
    mqtt.setClient(tlsNet);
  } else {
    mqtt.setClient(plainNet);
  }
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setBufferSize(512);  // 기본 256B면 프로브 3개부터 잘림
}

void loop() {
  static uint32_t lastSample = -SAMPLE_MS, lastTry = 0;  // 부팅 직후 바로 한 번 측정
  if (millis() - lastSample >= SAMPLE_MS) { lastSample = millis(); sample(); }

  if (!mqtt.connected()) {
    if (WiFi.status() == WL_CONNECTED && millis() - lastTry > 5000) { lastTry = millis(); connectMqtt(); }
    return;  // 끊겨 있어도 측정은 계속, 버퍼에 쌓임
  }
  mqtt.loop();
  if (count && send(buf[head])) { head = (head + 1) % BUF_N; count--; }
}
