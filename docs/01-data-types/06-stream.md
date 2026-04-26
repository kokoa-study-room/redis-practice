# 06. Stream

> **학습 목표**: Stream을 "Redis 안의 Kafka-lite"로 이해하고, Consumer Group으로 작업 큐를 안전하게 만들 수 있다. **Redis 8.6의 IDMP/IDMPAUTO** (멱등성)도 이해한다.
> **예상 소요**: 40분 (가장 정교한 자료형)

---

## 1. 개념

> **append-only 시계열 로그 + Consumer Group 으로 분산 처리.**

```
Stream "events"
┌──────────────┬──────────────┬──────────────┬──────────────┐
│ 1714000001-0 │ 1714000002-0 │ 1714000002-1 │ 1714000003-0 │ ...
│ {user:1,ev:A}│ {user:2,ev:B}│ {user:3,ev:A}│ {user:1,ev:C}│
└──────────────┴──────────────┴──────────────┴──────────────┘
       ▲              ▲ ID = ms-time + seq (자동 생성, 단조 증가)
       └ 가장 오래된 entry      

Consumer Groups:
  group "billing"   → consumer C1, C2  (같은 group 안에서 entry 분배)
  group "analytics" → consumer A1       (group끼리는 같은 entry 다 받음)
```

용도:
- 이벤트 소싱
- 작업 큐 (List보다 안전 — at-least-once)
- 로그 수집
- IoT 텔레메트리

> 출처: <https://redis.io/docs/latest/develop/data-types/streams/>

---

## 2. 기본 사용법

### 2.1 추가 / 조회

```
# XADD: ID 자동 생성(*)
XADD events '*' user 1 type signup
# → "1714000001-0"

# 명시적 ID
XADD events 1714000005-0 user 2 type login

# 길이 제한 (트림)
XADD events MAXLEN 1000 '*' user 3 type purchase
XADD events MAXLEN '~' 1000 '*' ...      # ~ = 근사치 트림 (성능 ↑, 정확도 ↓)
XADD events MINID 1700000000-0 '*' ...    # ID 기준 트림

# 조회
XLEN events                          # 길이
XRANGE events - +                    # 전체 (- = 가장 작은 ID, + = 가장 큰)
XRANGE events - + COUNT 10           # 처음 10개
XREVRANGE events + - COUNT 10        # 최근 10개

# 단순 read (consumer group 없이)
XREAD COUNT 5 STREAMS events 0       # 0 이후 모든 entry
XREAD BLOCK 5000 STREAMS events $    # $ = 지금 이후 새로 들어오는 것 5초 대기

# 정보
XINFO STREAM events
XINFO STREAM events FULL
```

### 2.2 Consumer Group

```
# 그룹 생성 (이미 존재하면 BUSYGROUP 에러)
XGROUP CREATE events billing 0       # 0 부터 read
XGROUP CREATE events billing $       # 지금부터 read (이전 entry 무시)
XGROUP CREATE events billing 0 MKSTREAM   # stream이 없어도 만들기

# 컨슈머가 받기 (> = 아직 다른 컨슈머에 안 준 새 entry)
XREADGROUP GROUP billing consumer-1 COUNT 10 BLOCK 5000 STREAMS events '>'

# 처리 후 ACK (PEL Pending Entries List 에서 제거)
XACK events billing 1714000001-0 1714000002-0

# 미처리(PEL) 조회
XPENDING events billing                       # 요약
XPENDING events billing - + 10 consumer-1     # 자세히

# 죽은 컨슈머의 메시지 회수 (claim)
XCLAIM events billing consumer-2 60000 1714000005-0
# → consumer-1이 60초간 ACK 안 한 메시지를 consumer-2가 가져감

# autoclaim (Redis 6.2+)
XAUTOCLAIM events billing consumer-2 60000 0 COUNT 10
```

### 2.3 Redis 8.6 신규: 멱등성 (Idempotency)

같은 producer가 같은 메시지를 여러 번 XADD 해도 한 번만 저장되게.

```
# IDMPAUTO (자동 ID 생성 + 멱등성)
XADD events IDMPAUTO p1 msg-001 '*' user 1 ev signup
# → 첫 호출: "1714000010-0" 저장 + 추적
# → 같은 producer p1, iid msg-001로 다시 호출: 이미 본 IID라 새로 저장 안 함, 첫 ID 반환

# IDMP (명시적)
XADD events IDMP p1 msg-002 1714000020-0 user 2 ev purchase
```

설정:
```
XCFGSET events IDMP_DURATION 86400 IDMP_MAXSIZE 100000
# 멱등성 추적 데이터를 24시간 또는 10만 개까지 유지
```

> 출처: <https://github.com/redis/redis/releases/tag/8.6.0> "Streams: XADD idempotency (at-most-once guarantee) with new IDMPAUTO and IDMP arguments" — 본 단락 명령 형식 근거

> 출처 (Node-redis 지원): <https://github.com/redis/node-redis/releases/tag/redis%405.11.0> "XADD idempotency options" 섹션

### 2.4 Redis 8.8-M02 (pre-release): XNACK

> Pre-release 단계. 정식 버전 안내 시점에 다시 확인 필요.
> 출처: <https://github.com/redis/redis/releases/tag/8.8-m02>
> "XNACK: a new streams command that allows consumers to explicitly release pending messages"

---

## 3. 클라이언트 코드 예제

### Python — Consumer Group 워커

```python
import redis
r = redis.Redis(decode_responses=True)

STREAM = "tasks"
GROUP = "workers"
CONSUMER = "worker-1"

# 그룹이 없으면 만들기
try:
    r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
except redis.exceptions.ResponseError:
    pass  # BUSYGROUP - 이미 있음

while True:
    # 새 메시지 + 미ack 메시지를 함께 처리하는 일반 패턴:
    # 1) 먼저 기존 PEL을 다시 보낸 적 있는지 확인 (id="0")
    # 2) 그 다음 신규(">")
    resp = r.xreadgroup(
        groupname=GROUP, consumername=CONSUMER,
        streams={STREAM: ">"}, count=10, block=5000,
    )
    if not resp:
        continue
    for stream_name, entries in resp:
        for entry_id, fields in entries:
            try:
                # 처리
                print(f"[{entry_id}] {fields}")
                r.xack(STREAM, GROUP, entry_id)
            except Exception as e:
                # 처리 실패 → ACK 안 함 → PEL에 남음 → 추후 재시도/Claim
                print(f"FAIL {entry_id}: {e}")
```

### Node.js (node-redis 5.12 — IDMPAUTO 사용)

```javascript
import { createClient } from "redis";
const r = createClient(); await r.connect();

const id = await r.xAdd("events", "*", { user: "1", ev: "signup" }, {
  IDMPAUTO: { producer: "p1", iid: "signup-msg-001" }
});
console.log("Stream ID:", id);
```

> 출처: node-redis 5.11.0 릴리즈노트의 IDMPAUTO 인터페이스 (위 §2.3 참고)

---

## 4. 내부 동작

### 4.1 인코딩

Stream의 외부 인코딩은 `stream` 하나뿐. 내부적으로:
- **rax (Radix Tree)**: ID 인덱싱 (정렬된 순회 + 빠른 lookup)
- **listpack 노드 묶음**: rax 잎에 작은 listpack로 묶어 저장 (메모리 효율)

> 02-internals/07-rax-radix-tree.md 에서 자세히.
> 출처: <https://github.com/redis/redis/blob/8.6/src/t_stream.c> stream에서 rax + listpack 사용

### 4.2 Big-O

| 명령 | 복잡도 |
|---|---|
| `XADD` | O(log N) (rax 삽입) |
| `XLEN` | O(1) (메타에 저장) |
| `XRANGE / XREAD` | O(log N + M) |
| `XACK / XDEL` | O(log N) |
| `XCLAIM` | O(log N + M) per id |
| `XINFO STREAM` | O(1) ~ O(log N) |

---

## 5. 흔한 함정

| 함정 | 설명 |
|---|---|
| **MAXLEN 안 쓰면 무한 증가** | 항상 MAXLEN 또는 MINID로 트림. `~` 트림이 성능에 유리. |
| **`XREAD` BLOCK 0** (무제한) **을 잡고 다른 명령** | 그 connection은 묶여 있음. consumer connection은 별도 pool. |
| **PEL을 안 보고 `>` 만 read** | 다른 컨슈머가 죽으면서 남긴 PEL 메시지가 영영 처리 안 됨. 워커는 시작 시 `XPENDING` 점검 + `XCLAIM`. |
| **여러 Stream을 하나 키에 모음** | Stream은 키 1개에 단일 시퀀스. 토픽 분리는 키 분리로. |
| **8.6 미만에서 IDMP 사용** | 명령 자체가 없음. `INFO server` 의 redis_version 확인. |

---

## 6. List 큐 vs Stream 큐 비교

| 항목 | List + BLPOP | Stream + Consumer Group |
|---|---|---|
| 컨슈머 죽었을 때 메시지 손실 | 가능 | PEL에 남아 재처리 가능 |
| 동일 메시지 여러 그룹 fan-out | 어려움 | 그룹 단위 가능 |
| 메시지 ID / 순서 추적 | 별도 구현 필요 | 내장 (XINFO) |
| 운영 복잡도 | 낮음 | 중간 |
| 처리량 | 매우 높음 | 높음 (조금 낮을 수 있음) |
| 어울리는 케이스 | 단순 작업 큐 | 안전한 작업 큐 / 이벤트 로그 |

---

## 7. RedisInsight

Browser → Stream 키 → Entries / Consumer Groups / Consumers 탭.
Consumer Group의 PEL을 표로 시각화. 컨슈머별 idle time도 확인.

---

## 8. 직접 해보기

1. `XADD events MAXLEN '~' 100 '*' user 1 ev test` 를 200번 → `XLEN` 이 100 부근인지.
2. 그룹 만들고 두 컨슈머로 동시 `XREADGROUP` → 메시지가 분배되는지.
3. 컨슈머 1에서 처리만 하고 ACK 안 한 채 종료 → `XPENDING` 으로 확인 → 컨슈머 2에서 `XCLAIM` 또는 `XAUTOCLAIM`.
4. (Redis 8.6) `XADD events IDMPAUTO p1 same-id '*' x 1` 을 두 번 → 같은 ID 반환되는지.

---

## 9. 참고 자료

- **[공식 문서] Redis Streams**
  - URL: <https://redis.io/docs/latest/develop/data-types/streams/>
  - 참고 부분: ID 형식, MAXLEN ~ 트림, Consumer Group 개념 — §1, §2 근거

- **[공식 문서] XADD / XREADGROUP / XPENDING / XCLAIM**
  - URL: <https://redis.io/docs/latest/commands/xadd/>, etc.
  - 참고 부분: Time complexity, 옵션 형식 — §2, §4.2 근거

- **[GitHub] redis/redis 8.6.0 release notes**
  - URL: <https://github.com/redis/redis/releases/tag/8.6.0>
  - 참고 부분: "Streams: XADD idempotency ... IDMPAUTO and IDMP" — §2.3 IDMP 명령 근거

- **[GitHub] redis/node-redis 5.11.0 release notes**
  - URL: <https://github.com/redis/node-redis/releases/tag/redis%405.11.0>
  - 참고 부분: "XADD idempotency options" 섹션 — Node 클라이언트 IDMPAUTO API 근거

- **[GitHub] redis/redis 8.8-M02 release notes**
  - URL: <https://github.com/redis/redis/releases/tag/8.8-m02>
  - 참고 부분: "XNACK" 추가 — §2.4 pre-release 신규 사항 근거
