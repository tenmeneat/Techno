"""백엔드↔프런트 계약 (§11.1). 여기서 OpenAPI가 생성되고 프런트 타입이 뽑힌다.
바꾸려면 §11.4 변경 절차."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.forecast import Forecast

StateName = Literal["SAFE", "WATCH", "ALERT", "CONDENSING", "STALE"]


class Device(BaseModel):
    id: str
    home_id: str
    label: str | None
    location_tag: str | None
    fw: str | None
    last_seen: datetime | None
    online: bool | None
    calib_t_air: float
    calib_rh: float
    calib_t_surf: float
    state: StateName


class DevicePatch(BaseModel):
    label: str | None = None
    location_tag: str | None = None


class Calibration(BaseModel):
    t_air: float = 0
    rh: float = 0
    t_surf: float = 0


class ProbeReading(BaseModel):
    time: datetime
    probe_id: str
    t_air: float
    rh: float
    t_surf: float
    t_dew: float
    t80: float
    rh_surf: float


class Current(BaseModel):
    """GET current 응답이자 WS 'reading' 메시지 본문."""
    device_id: str
    state: StateName
    forecast: Forecast | None
    probes: list[ProbeReading]


class Event(BaseModel):
    id: int
    state: StateName
    started_at: datetime
    ended_at: datetime | None
    peak_rh_surf: float | None
    min_delta_t: float | None


class Diagnostic(BaseModel):
    day: date
    f_rsi: float | None
    tdr: float | None
    t_ext_avg: float | None
    minutes_alert: float
    mould_dose: float


class ReportRequest(BaseModel):
    device_id: str
    from_: datetime = Field(alias="from")
    to: datetime


class Report(BaseModel):
    device: Device
    from_: datetime = Field(serialization_alias="from")
    to: datetime
    minutes_alert: float
    minutes_condensing: float
    event_days: list[date]
    mean_rh_surf: float | None  # ISO 13788 비교용 기간 평균 RHs
    diagnostics: list[Diagnostic]
    weather_sources: dict[str, int]  # 출처 표기용 (kma / open-meteo 시간 수)


class PushSubscription(BaseModel):
    endpoint: str
    keys: dict[str, str]
    quiet_start: int = Field(23, ge=0, le=23)
    quiet_end: int = Field(7, ge=0, le=23)
