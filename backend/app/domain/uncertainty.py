"""판정 불확도 (B-04, 설계서 §5.4·§5.6). 순수함수만 — I/O 금지.

표면습도 RHs = RH · es(Ta) / es(Ts)의 표준불확도를 센서 불확도로부터 전파한다(1차 테일러, 입력 간 무상관).
기준 조건(실내 20 °C·60 %, 벽 15 °C)에서 민감도는 ∂RHs/∂RH ≈ +1.37, ∂RHs/∂Ts ≈ −5.3, ∂RHs/∂Ta ≈ +5.1 [%p/단위]이고,
RHs가 80 %인 경계 조건에서는 ∂RHs/∂RH = 80/RH ≈ +1.33이다. 결과는 약 ±4.6 %p로 설계서 §5.4의 ±4.5 %p와 같다.

★ 불확도 수치는 이 파일 한 곳에서만 정한다. 설계서 §3.3(±4 %p)과 §5.4(±4.5 %p)가 서로 달랐던 것을
  여기서 계산한 값(nominal_u_rhs)으로 통일한다. 리포트 문구 등 다른 곳은 이 값을 가져다 쓴다.
"""
import math
from dataclasses import dataclass

from app.domain.psychrometrics import B, C, rh_surface

# 센서 표준불확도 (데이터시트 정확도를 그대로 표준불확도로 본다 — 설계서 §5.4와 같은 가정)
U_T_AIR = 0.5    # DHT22 온도 ±0.5 K
U_RH = 2.0       # DHT22 습도 ±2 %p (고습·저온에서는 ±5 %p까지 나빠질 수 있음 — 보수적으로 쓰려면 호출 시 u_rh 지정)
U_T_SURF = 0.5   # DS18B20 ±0.5 K

RHS_LIMIT = 80.0  # ISO 13788 곰팡이 기준 표면습도


def _g(t: float) -> float:
    """d ln es / dT (Magnus)."""
    return B * C / (C + t) ** 2


def sensitivities(t_air: float, rh: float, t_surf: float) -> tuple[float, float, float]:
    """(∂RHs/∂Ta, ∂RHs/∂RH, ∂RHs/∂Ts). 100 % 클립 전의 RHs 식으로 계산한다."""
    rhs = 100 * math.exp(math.log(rh / 100) + B * t_air / (C + t_air) - B * t_surf / (C + t_surf))
    return rhs * _g(t_air), rhs / rh, -rhs * _g(t_surf)


def u_rhs(t_air: float, rh: float, t_surf: float,
          u_t_air: float = U_T_AIR, u_rh: float = U_RH, u_t_surf: float = U_T_SURF) -> float:
    """측정 한 건의 표면습도 표준불확도 [%p]."""
    a, h, s = sensitivities(t_air, rh, t_surf)
    return math.sqrt((a * u_t_air) ** 2 + (h * u_rh) ** 2 + (s * u_t_surf) ** 2)


def nominal_u_rhs() -> float:
    """대표 불확도 — 기준 조건(20 °C, 60 %, 벽 15 °C). 리포트·안내 문구용 단일 값."""
    return u_rhs(20.0, 60.0, 15.0)


@dataclass(frozen=True)
class RhsBand:
    rh_surf: float      # 표면습도 추정값 (100 클립)
    lo: float           # 추정값 − 불확도 (0 이상)
    hi: float           # 추정값 + 불확도 (100 이하)
    u: float            # 표준불확도 [%p]
    borderline: bool    # 기준(80 %)이 범위 안 → '경계(판정 보류)' 표시용


def rhs_band(t_air: float, rh: float, t_surf: float, limit: float = RHS_LIMIT, **u_kw) -> RhsBand:
    """표면습도를 범위로. 경계 플래그는 표시용 — 상태머신(risk_state)은 바꾸지 않는다(팀 합의 전)."""
    v = rh_surface(t_air, rh, t_surf)
    u = u_rhs(t_air, rh, t_surf, **u_kw)
    return RhsBand(v, max(0.0, v - u), min(100.0, v + u), u, is_borderline(v, u, limit))


def is_borderline(rh_surf: float, u: float, limit: float = RHS_LIMIT) -> bool:
    """|RHs − 기준| ≤ 불확도이면 측정 오차 안에서 위험/안전을 가를 수 없다."""
    return abs(rh_surf - limit) <= u
