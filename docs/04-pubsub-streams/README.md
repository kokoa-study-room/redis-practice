# 04. Pub/Sub & Streams (메시징 / 이벤트)

> **이 챕터의 목표**: Pub/Sub과 Stream의 차이를 알고 상황에 맞게 선택할 수 있다. Keyspace Notifications도 활용한다.

---

## 학습 순서

| # | 파일 | 핵심 |
|---|---|---|
| 01 | [01-pubsub.md](01-pubsub.md) | PUBLISH/SUBSCRIBE, PSUBSCRIBE 패턴, Sharded Pub/Sub |
| 02 | [02-keyspace-notifications.md](02-keyspace-notifications.md) | 키 만료/변경 이벤트를 Pub/Sub으로 받기 |
| 03 | [03-streams-consumer-group.md](03-streams-consumer-group.md) | Consumer Group 운영, IDMP (8.6+) 멱등성 |

---

## Pub/Sub vs Stream 비교

| 항목 | Pub/Sub | Stream + Consumer Group |
|---|---|---|
| 메시지 보존 | ❌ (휘발) | ✅ (XLEN까지 유지) |
| 컨슈머 죽음 → 메시지 손실 | 가능 | PEL에 남아 재처리 가능 |
| fan-out (1 → N) | ✅ 자연스러움 | 그룹 단위로 가능 |
| 부하 분산 (N 컨슈머가 나눠 처리) | ❌ | ✅ |
| 복잡도 | 낮음 | 중간 |
| 어울리는 케이스 | 알림 / 실시간 채팅 / WebSocket bridge | 작업 큐 / 이벤트 소싱 / 로그 |

---

## Keyspace Notifications 한 줄 요약

> **"키 X가 만료됐다 / 변경됐다" 이벤트를 Pub/Sub 채널로 받는 기능.**

```
notify-keyspace-events "KEA"     # K = keyspace, E = keyevent, A = all commands
```

활성화 후 `__keyspace@0__:user:1` 같은 채널을 SUBSCRIBE.
