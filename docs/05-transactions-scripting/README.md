# 05. 트랜잭션 & 스크립팅 (Transactions & Scripting)

> **이 챕터의 목표**: Redis의 "트랜잭션"이 RDBMS의 ACID와 다른 점, MULTI/EXEC/WATCH로 낙관적 락 구현, Lua / Functions로 서버 측 로직 작성.

---

## 학습 순서

| # | 파일 | 핵심 |
|---|---|---|
| 01 | [01-multi-exec-watch.md](01-multi-exec-watch.md) | 명령 묶기 + WATCH 낙관적 락 |
| 02 | [02-lua-scripts.md](02-lua-scripts.md) | EVAL / EVALSHA — 서버에서 원자적 실행 |
| 03 | [03-functions.md](03-functions.md) | Redis 7+ Functions — 영속적 등록형 스크립트 |

---

## 핵심 통찰

- Redis는 단일 스레드라 **모든 단일 명령은 atomic**.
- "트랜잭션"이 필요한 진짜 이유는 **여러 명령을 순서 보장 + 다른 클라이언트 끼어들기 방지** 하고 싶을 때.
- MULTI/EXEC: 명령들을 큐잉 후 한 번에 실행. **롤백 없음**.
- WATCH: optimistic locking — 감시 중인 키가 다른 클라이언트에 의해 변경되면 EXEC가 실패.
- Lua/Function: 더 복잡한 서버 측 원자 로직.
