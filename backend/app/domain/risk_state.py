"""판정 상태머신 (§3.3) — 히스테리시스 + dwell. 입력은 RHs 5분 중앙값."""
from dataclasses import dataclass, field
from enum import IntEnum


class State(IntEnum):
    SAFE = 0
    WATCH = 1
    ALERT = 2
    CONDENSING = 3


# 상태: (진입 RHs, 복귀 RHs, 지속 조건 초)
RULES = {
    State.WATCH: (72.0, 69.0, 600),
    State.ALERT: (80.0, 77.0, 600),
    State.CONDENSING: (100.0, 97.0, 300),
}
STALE_AFTER_S = 300  # 마지막 수신 후 5분


@dataclass
class RiskMachine:
    state: State = State.SAFE
    above_since: dict[State, float] = field(default_factory=dict)  # 진입 임계 이상이 연속된 시작 시각

    def update(self, rh_s: float, t: float) -> State:
        for lvl, (entry, _, _) in RULES.items():
            if rh_s >= entry:
                self.above_since.setdefault(lvl, t)
            else:
                self.above_since.pop(lvl, None)

        # 상승: 더 높은 상태의 진입 조건이 dwell 동안 유지됐는가 (높은 것부터)
        for lvl in sorted(RULES, reverse=True):
            if lvl <= self.state:
                break
            since = self.above_since.get(lvl)
            if since is not None and t - since >= RULES[lvl][2]:
                self.state = lvl
                return self.state

        # 하강: 현재 상태의 복귀 임계 밑으로 내려가면 즉시, 복귀 임계를 아직 넘는 가장 높은 상태로
        if self.state > State.SAFE and rh_s < RULES[self.state][1]:
            self.state = max(
                (lvl for lvl in RULES if lvl < self.state and rh_s >= RULES[lvl][1]),
                default=State.SAFE,
            )
        return self.state
