# 09. 실전 패턴 (Patterns)

> **이 챕터의 목표**: 가장 자주 만나는 6가지 패턴을 실제 코드로 구현해본다. 각 패턴의 함정과 대안도 안다.

---

## 학습 순서

| # | 파일 | 핵심 |
|---|---|---|
| 01 | [01-cache-aside.md](01-cache-aside.md) | 가장 흔한 캐시 패턴 + cache stampede 방지 |
| 02 | [02-rate-limiter.md](02-rate-limiter.md) | Token Bucket / Sliding Window / Fixed Window |
| 03 | [03-distributed-lock-redlock.md](03-distributed-lock-redlock.md) | SET NX EX + Lua 안전 해제, Redlock 논쟁 |
| 04 | [04-leaderboard.md](04-leaderboard.md) | ZSET 기반 리더보드 + TOP-N 유지 |
| 05 | [05-session-store.md](05-session-store.md) | Hash + TTL, 슬라이딩 만료 |
| 06 | [06-feed-timeline.md](06-feed-timeline.md) | Fan-out write vs read 비교 |

---

## 패턴 선택 가이드

| 문제 | 패턴 |
|---|---|
| DB 부하가 높다 | Cache-aside |
| 사용자별 API 호출 제한 | Rate Limiter |
| 동시에 같은 작업이 두 번 안 일어나야 | 분산 락 |
| 게임 점수 / 인기 순위 | Leaderboard |
| 로그인 세션 | Session Store |
| SNS 피드 / 타임라인 | Fan-out 패턴 |
