# 02. Keyspace Notifications

> **학습 목표**: 키의 만료/변경 이벤트를 Pub/Sub 채널로 받는 기능을 활성화하고, 분산 작업 트리거에 활용할 수 있다. **단점(미보장)** 도 안다.
> **예상 소요**: 20분

---

## 1. 개념

> **키에 어떤 일이 생기면 → Redis가 미리 정해진 Pub/Sub 채널에 이벤트 발행.**

채널 형식:
```
__keyspace@<db>__:<key>      # "이 키에 X 동작이 일어났다"  (키 관점)
__keyevent@<db>__:<event>    # "이 동작이 어떤 키에 일어났다" (이벤트 관점)
```

용도:
- **TTL 만료 트리거** — 토큰 만료 시 후속 작업
- **세션 만료 처리**
- **외부 시스템에 변경 동기화**

---

## 2. 활성화

기본은 비활성. `notify-keyspace-events` 옵션으로 켜야 함.

```
CONFIG SET notify-keyspace-events "KEA"
```

또는 `redis.conf`:
```
notify-keyspace-events "KEA"
```

각 글자 의미:
| 글자 | 의미 |
|---|---|
| `K` | Keyspace 이벤트 (`__keyspace@<db>__:<key>` 채널) |
| `E` | Keyevent 이벤트 (`__keyevent@<db>__:<event>` 채널) |
| `g` | 일반 명령 (DEL, EXPIRE, RENAME, ...) |
| `$` | String 명령 |
| `l` | List 명령 |
| `s` | Set 명령 |
| `h` | Hash 명령 |
| `z` | ZSET 명령 |
| `x` | Expired 이벤트 (TTL로 만료된 키) |
| `e` | Evicted 이벤트 (maxmemory로 쫓겨난 키) |
| `m` | key-miss 이벤트 |
| `n` | New key 이벤트 |
| `t` | Stream 명령 |
| `d` | Module key 이벤트 |
| `A` | g$lshzxetd 모두 (위 모두) |

학습용으로는 `KEA` 가 모든 이벤트.

> 출처: <https://redis.io/docs/latest/develop/use/keyspace-notifications/>
> 참고 부분: 글자 표 — 본 표 근거

---

## 3. 사용 예 — 만료 알림

### 터미널 A
```
redis-cli PSUBSCRIBE '__keyevent@0__:expired'
```

### 터미널 B
```
SET token:abc "data" EX 5
```

5초 후 터미널 A:
```
1) "pmessage"
2) "__keyevent@0__:expired"
3) "__keyevent@0__:expired"
4) "token:abc"
```

### Python 예제

```python
import redis
r = redis.Redis(decode_responses=True)

# 활성화 (영속 설정은 redis.conf, 이건 일회성)
r.config_set("notify-keyspace-events", "KEA")

ps = r.pubsub()
ps.psubscribe("__keyevent@0__:expired")

# 토큰 발급
r.set("token:user:1", "abc", ex=10)

# 리스닝
for msg in ps.listen():
    if msg["type"] == "pmessage":
        expired_key = msg["data"]
        print(f"만료됨: {expired_key} → 후속 처리")
```

---

## 4. 만료 이벤트의 함정 (가장 중요)

> **만료 이벤트는 키가 "삭제되는 시점"에 발행된다.**

Redis는 두 가지 방식으로 만료 키를 정리:
1. **Lazy**: 클라이언트가 키를 액세스할 때 → 그 시점에 삭제 + 이벤트 발행
2. **Active**: 백그라운드 cron이 일부 샘플링 → 만료된 키 삭제

→ **TTL이 끝난 정확한 시점에 이벤트가 오지 않을 수 있다.** 늦어질 수 있음.

또한:
- **at-most-once**: 구독자가 잠시 끊겨 있으면 그 사이 이벤트 손실.
- **클러스터에서 노드 단위** → 다른 노드의 키 이벤트는 안 옴.

> 출처: <https://redis.io/docs/latest/develop/use/keyspace-notifications/>
> 참고 부분: "Timing of expired events" 섹션 + "At-most-once delivery" — 본 절 근거

---

## 5. 운영에서 사용 시 권고

| 상황 | 권고 |
|---|---|
| **반드시 시간 정확** 필요 | Keyspace Notifications 부적합. 별도 스케줄러 / Stream 사용. |
| **at-least-once** 필요 | Notifications 부적합. Stream + Consumer Group. |
| **단순 알림 / 모니터링** | 적합. |
| **Cluster** | sharded 통신 + 노드별 구독 모두 고려. 복잡 → Stream 권장. |

---

## 6. 직접 해보기

1. `CONFIG SET notify-keyspace-events "KEA"` 후 `PSUBSCRIBE '__keyspace@0__:user:*'` → SET user:1 시 이벤트 확인.
2. `SET k v EX 3` → 3초 후 expired 이벤트 시점 측정. 정확히 3초인가 5초인가?
3. SUBSCRIBE 안 하고 있다가 SET / EX → 다시 SUBSCRIBE → 이전 이벤트 못 받는 것 확인 (휘발).
4. evicted 이벤트 트리거: `maxmemory` 작게 설정 + 큰 데이터 채워서.

---

## 7. 참고 자료

- **[공식 문서] Keyspace Notifications**
  - URL: <https://redis.io/docs/latest/develop/use/keyspace-notifications/>
  - 참고 부분: 글자 표, "Timing of expired events", "At-most-once delivery" — §2, §4 근거

- **[공식 문서] CONFIG SET / GET**
  - URL: <https://redis.io/docs/latest/commands/config-set/>
  - 참고 부분: notify-keyspace-events 옵션 변경 방법 — §2 근거
