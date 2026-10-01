-- DB 스키마 (§9.4). docker-compose가 최초 기동 시 1회 실행한다.
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE homes (
    id            text PRIMARY KEY,
    name          text,
    region_code   text NOT NULL DEFAULT 'seoul',
    owner_user_id text
);

CREATE TABLE devices (
    id           text PRIMARY KEY,
    home_id      text NOT NULL REFERENCES homes(id),
    label        text,
    location_tag text,
    fw           text,
    calib_t_air  real NOT NULL DEFAULT 0,  -- §8.4 오프셋은 서버에 두고 수신 시 적용
    calib_rh     real NOT NULL DEFAULT 0,
    calib_t_surf real NOT NULL DEFAULT 0,
    last_seen    timestamptz,
    online       boolean
);

-- 프로브마다 한 행. (device_id, probe_id, time) 유니크가 QoS1 중복 수신의 멱등성 처리(§9.1)
CREATE TABLE readings (
    time      timestamptz NOT NULL,
    device_id text NOT NULL,
    probe_id  text NOT NULL,
    t_air     real,
    rh        real,
    t_surf    real,
    t_dew     real,
    rh_surf   real,
    delta_t   real,
    rssi      smallint,
    saturated boolean NOT NULL DEFAULT false,
    UNIQUE (device_id, probe_id, time)
);
SELECT create_hypertable('readings', 'time', chunk_time_interval => INTERVAL '1 day');

CREATE MATERIALIZED VIEW readings_1m WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT time_bucket('1 minute', time) AS bucket, device_id, probe_id,
       avg(t_air) AS t_air, avg(rh) AS rh, avg(t_surf) AS t_surf, avg(t_dew) AS t_dew, avg(rh_surf) AS rh_surf
FROM readings GROUP BY 1, 2, 3 WITH NO DATA;
-- start_offset은 기기 오프라인 버퍼(최대 6시간, §8.2)보다 넉넉해야 늦게 온 백로그도 집계된다
SELECT add_continuous_aggregate_policy('readings_1m',
    start_offset => INTERVAL '1 day', end_offset => INTERVAL '1 minute', schedule_interval => INTERVAL '1 minute');

CREATE MATERIALIZED VIEW readings_1h WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT time_bucket('1 hour', time) AS bucket, device_id, probe_id,
       avg(t_air) AS t_air, avg(rh) AS rh, avg(t_surf) AS t_surf, avg(t_dew) AS t_dew, avg(rh_surf) AS rh_surf
FROM readings GROUP BY 1, 2, 3 WITH NO DATA;
SELECT add_continuous_aggregate_policy('readings_1h',
    start_offset => INTERVAL '7 days', end_offset => INTERVAL '1 hour', schedule_interval => INTERVAL '30 minutes');

ALTER TABLE readings SET (timescaledb.compress, timescaledb.compress_segmentby = 'device_id, probe_id');
SELECT add_compression_policy('readings', INTERVAL '7 days');
SELECT add_retention_policy('readings', INTERVAL '90 days');  -- 원본만 삭제, 집계 뷰는 유지

CREATE TABLE events (
    id           bigserial PRIMARY KEY,
    device_id    text NOT NULL REFERENCES devices(id),
    state        text NOT NULL,  -- WATCH / ALERT / CONDENSING / STALE (SAFE는 기록 안 함)
    started_at   timestamptz NOT NULL,
    ended_at     timestamptz,
    peak_rh_surf real,
    min_delta_t  real
);
CREATE INDEX ON events (device_id, started_at DESC);

CREATE TABLE weather_hourly (
    time        timestamptz NOT NULL,
    region_code text NOT NULL,
    t_ext       real NOT NULL,
    rh_ext      real,
    source      text NOT NULL,  -- 'kma' | 'open-meteo' (§4.5)
    PRIMARY KEY (region_code, time)
);
SELECT create_hypertable('weather_hourly', 'time', chunk_time_interval => INTERVAL '30 days');

CREATE TABLE daily_diagnostics (
    day           date NOT NULL,
    device_id     text NOT NULL REFERENCES devices(id),
    f_rsi         real,  -- NULL = 산출 조건 미달 (§4.3)
    tdr           real,
    t_ext_avg     real,
    minutes_alert real NOT NULL,
    mould_dose    real NOT NULL,  -- %·h (§3.4)
    PRIMARY KEY (day, device_id)
);

-- 스키마 검증 실패 메시지 (§9.5). 파이프라인은 멈추지 않는다.
CREATE TABLE dead_letters (
    id          bigserial PRIMARY KEY,
    received_at timestamptz NOT NULL DEFAULT now(),
    topic       text,
    payload     text,
    error       text
);

CREATE TABLE push_subscriptions (
    endpoint    text PRIMARY KEY,
    keys        jsonb NOT NULL,
    quiet_start smallint NOT NULL DEFAULT 23,  -- §9.7 야간 무음 (CONDENSING 예외)
    quiet_end   smallint NOT NULL DEFAULT 7
);
