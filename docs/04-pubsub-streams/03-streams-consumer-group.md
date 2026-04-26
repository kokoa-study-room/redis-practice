# 03. Streams + Consumer Group (운영 관점)

> **학습 목표**: 01-data-types/06-stream.md 의 명령을 운영 관점으로 다시 봐서, **at-least-once 처리**, 컨슈머 죽음 회복, **Redis 8.6 IDMP 멱등성** 까지 단단히 익힌다.
> **예상 소요**: 30분

---

## 1. 작업 큐 안전 처리 패턴

### 1.1 시작 시 — PEL 먼저, 그 다음 신규

```python
def consume(stream, group, consumer):
    # 1) 이전에 받았지만 ack 못 한 것 (PEL) 먼저 처리
    while True:
        pending = r.xreadgroup(group, consumer, {stream: "0"}, count=10)
        if not pending or not pending[0][1]:
            break
        process_and_ack(pending)
    
    # 2) 그 다음 신규 메시지 (>)
    while True:
        new = r.xreadgroup(group, consumer, {stream: ">"}, count=10, block=5000)
        process_and_ack(new)
```

`"0"` (또는 `"0-0"`) → PEL 재읽기. `">"` → 신규.

### 1.2 컨슈머 죽었을 때 — XAUTOCLAIM

```python
# 다른 컨슈머가 60초 이상 ack 못 한 메시지를 가로챔
r.xautoclaim(stream, group, my_consumer, min_idle_time=60_000, start_id="0", count=10)
```

이걸 워커마다 주기적으로 (예: 30초마다) 실행하면 죽은 컨슈머의 일감이 자연스럽게 회복된다.

### 1.3 ack 절대 잊지 말기

```python
try:
    process(payload)
    r.xack(stream, group, msg_id)         # 성공 시에만 ack
except Exception:
    pass  # PEL에 남음 → 추후 재시도
```

영구 실패하는 메시지(독약, poison message)는 일정 횟수 재시도 후 별도 dead-letter 키로 옮기는 패턴.

---

## 2. 멱등성 (Idempotency, Redis 8.6+)

같은 producer가 같은 메시지를 두 번 XADD 해도 한 번만 저장.

```
XADD events IDMPAUTO p1 msg-001 '*' user 1 ev signup
# 같은 (p1, msg-001) 다시 → 이미 본 것 → 새 ID 안 만듦, 첫 ID 반환
```

설정:
```
XCFGSET events IDMP_DURATION 86400 IDMP_MAXSIZE 100000
# 멱등 추적 데이터는 24시간 또는 10만 개까지
```

확인:
```
XINFO STREAM events
# idmp-duration: 86400
# idmp-maxsize: 100000
# pids-tracked: 5      ← producer 수
# iids-tracked: 12345  ← 추적 중인 instance ID
```

> 출처: <https://github.com/redis/redis/releases/tag/8.6.0> "XADD idempotency"

---

## 3. 트림 정책

### MAXLEN
```
XADD events MAXLEN 1000 '*' ...           # 정확히 1000개로 잘라냄 (느림)
XADD events MAXLEN '~' 1000 '*' ...       # 근사치 (1000 이상; 빠름)
```

### MINID (Redis 6.2+)
```
XADD events MINID '~' 1700000000-0 '*' ...   # 이 ID 이전은 다 삭제
```

### XTRIM (별도 명령)
```
XTRIM events MAXLEN '~' 10000
XTRIM events MINID 1700000000
```

---

## 4. 모니터링 명령

```
XINFO STREAM events                       # 길이, last id, group 수
XINFO STREAM events FULL                  # 노드 단위 상세
XINFO GROUPS events                       # 모든 그룹 요약
XINFO CONSUMERS events <group>            # 그룹의 컨슈머 + idle time + pending count
XPENDING events <group>                   # 요약
XPENDING events <group> - + 100 <consumer> # 자세히
```

---

## 5. RedisInsight에서

Stream 키 → 좌측 탭:
- **Entries**: ID 별 데이터
- **Consumer Groups**: 그룹 + 컨슈머 + PEL 시각화
- **Statistics**: 길이 / first / last id

PEL의 idle time을 한눈에 → 죽은 컨슈머 식별.

---

## 6. 흔한 함정

| 함정 | 설명 |
|---|---|
| `>` 만 read, PEL 무시 | 죽은 컨슈머의 메시지 영영 처리 안 됨. 시작 시 `"0"` 점검 + XAUTOCLAIM 주기. |
| MAXLEN 안 함 | 무한 증가. `~` 트림으로 적당히. |
| 같은 그룹에 컨슈머 이름 중복 | 같은 이름으로 두 워커 실행하면 read를 같이 받게 됨. UUID/host-pid 권장. |
| 트랜잭션 안에 XADD | MULTI/EXEC 안에서 XADD는 가능하지만 BLOCKING 명령은 안 됨. |
| `IDMPAUTO` 8.6 미만에서 사용 | 명령 자체가 없음. `INFO server`로 redis_version 확인. |

---

## 7. List/Pub-Sub 와 다시 비교

| 특성 | List + BLPOP | Pub/Sub | Stream |
|---|---|---|---|
| 영속 | ✅ | ❌ | ✅ (트림 정책 따라) |
| 부하 분산 | ✅ (한 메시지 한 컨슈머) | ❌ (모두 받음) | ✅ (그룹 단위) |
| fan-out | ❌ | ✅ | ✅ (그룹마다) |
| 컨슈머 죽음 회복 | ❌ | ❌ | ✅ (PEL + XCLAIM) |
| 운영 복잡도 | 낮음 | 낮음 | 중간 |

---

## 8. 직접 해보기

1. 두 컨슈머를 같은 그룹으로 띄우고 메시지가 분배되는지.
2. 한 컨슈머를 강제 종료 → 다른 컨슈머가 XAUTOCLAIM으로 회수.
3. (Redis 8.6) `IDMPAUTO p1 same-id` 로 같은 메시지 두 번 → ID 같은지.
4. `XCFGSET` 으로 IDMP_DURATION 60초 설정 → 60초 후 같은 IID 다시 들어오면 신규로 받는지.
5. RedisInsight에서 PEL 시각화 확인.

---

## 9. 참고 자료

- **[공식 문서] Streams Tutorial**
  - URL: <https://redis.io/docs/latest/develop/data-types/streams/>
  - 참고 부분: Consumer Group 운영, XPENDING/XCLAIM 패턴 — §1 근거

- **[공식 문서] XAUTOCLAIM**
  - URL: <https://redis.io/docs/latest/commands/xautoclaim/>
  - 참고 부분: min_idle_time, count — §1.2 근거

- **[GitHub] redis/redis 8.6.0 release notes**
  - URL: <https://github.com/redis/redis/releases/tag/8.6.0>
  - 참고 부분: "XADD idempotency" — §2 근거

- **[GitHub] redis/node-redis 5.11.0 release notes**
  - URL: <https://github.com/redis/node-redis/releases/tag/redis%405.11.0>
  - 참고 부분: XCFGSET 명령 가용성 — §2 설정 근거
