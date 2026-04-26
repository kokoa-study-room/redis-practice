# 04. Client-side Caching (서버 보조 클라이언트 캐싱)

> **학습 목표**: Redis 6+ 의 CLIENT TRACKING 으로 클라이언트 메모리에 GET 결과를 캐싱하고, 키 변경 시 서버가 invalidation 을 보내주는 패턴을 이해한다. 이는 동일 워크로드에서 throughput 을 5~10배까지 올릴 수 있다.
> **사전 지식**: 08-clients/01~03, RESP 프로토콜 기초
> **예상 소요**: 30분

---

## 1. 왜 필요한가?

```
일반 Redis:        Application  ──── GET user:1 ────→ Redis (network RTT 매번)
Client-side cache: Application  ─── (로컬 메모리 hit) ─── (Redis 안 부름)
```

LAN RTT ~200μs, Redis 자체 처리 ~수 μs.
→ "캐시의 캐시" 를 클라이언트 프로세스에 두면 RTT 자체를 없앤다.

문제: **stale data**. user:1 이 다른 클라이언트에 의해 바뀌면? → Redis가 알려줘야 함.

> 출처: <https://redis.io/docs/latest/develop/reference/client-side-caching/>

---

## 2. CLIENT TRACKING

### 2.1 기본 (default mode)

```
CLIENT TRACKING ON
GET user:1                  # Redis가 "이 클라이언트가 user:1 을 캐싱할 수 있다" 라고 기억
                            # 클라이언트는 응답을 로컬 메모리에 저장
```

다른 클라이언트가:
```
SET user:1 newval
```

→ Redis가 첫 클라이언트에게 invalidation 메시지 push:
```
INVALIDATE user:1
```

→ 클라이언트는 로컬 캐시에서 user:1 제거.

**서버 측 비용**: 어떤 클라이언트가 어떤 키를 봤는지 invalidation table 에 보관.

### 2.2 Broadcasting mode (BCAST)

서버가 키별 추적을 안 함 → 메모리 0. 대신 **클라이언트가 key prefix 를 등록** 하고 그 prefix 매칭 키 변경 시 invalidation 받음.

```
CLIENT TRACKING ON BCAST PREFIX user: PREFIX cached:
```

장점: 서버 메모리 0.
단점: **불필요한 invalidation** 도 받음 (해당 prefix 의 모든 변경).

---

## 3. 두 가지 구현 — RESP2 vs RESP3

### 3.1 RESP3 — Push messaging (권장)

같은 연결에서 정상 응답 + invalidation push 를 다중화.

```
HELLO 3 AUTH user pwd
CLIENT TRACKING ON
GET user:1
... 일반 응답 ...

(다른 곳에서 SET user:1 ... 발생)
>< push: INVALIDATE [user:1]
```

### 3.2 RESP2 — 두 개의 connection

RESP2 는 push 못 함 → invalidation 전용 connection 별도.

```
# Connection 1 (invalidation 수신용)
CLIENT ID                            # 4
SUBSCRIBE __redis__:invalidate

# Connection 2 (data)
CLIENT TRACKING ON REDIRECT 4        # invalidation을 connection 4번으로
GET user:1
```

→ data connection 에서 GET 받고, invalidation 은 connection 1 의 Pub/Sub 으로 옴.

---

## 4. opt-in / opt-out / NOLOOP

### opt-in
서버가 모든 read 키를 추적하면 부담 → 클라이언트가 **"이 명령 결과는 캐싱하겠다"** 라고 명시:

```
CLIENT TRACKING ON OPTIN
CLIENT CACHING YES                   # 다음 명령만 추적
GET user:1                           # 추적됨

GET other:foo                        # 추적 안 됨 (CACHING YES 안 했으니)
```

### opt-out
반대 — 기본은 모두 추적, 일부 키만 제외:
```
CLIENT TRACKING ON OPTOUT
CLIENT UNTRACKING some_key           # 이 키는 추적 안 함
```

### NOLOOP
내가 변경한 키에 대해서는 invalidation 안 받기 (자기 자신이 보낸 SET 의 invalidation 무시):
```
CLIENT TRACKING ON NOLOOP
```

---

## 5. node-redis 5+ 자동 client-side caching

```javascript
import { createClient } from "redis";

const r = createClient({
  RESP: 3,
  clientSideCache: { 
    ttl: 0,                          // 무한
    maxEntries: 10000,
  },
});
await r.connect();

const a = await r.get("user:1");     // miss → Redis
const b = await r.get("user:1");     // hit → 로컬 (0 RTT)
```

> 클라이언트 라이브러리마다 옵션 이름 다름. 공식 docs 확인.

---

## 6. redis-py 7+ client-side caching

```python
import redis

cache_config = redis.cache.CacheConfig(max_size=10000)
r = redis.Redis(
    host="127.0.0.1", port=6379,
    protocol=3,
    cache_config=cache_config,
)

r.get("user:1")    # miss
r.get("user:1")    # hit (로컬)
```

---

## 7. 측정 — throughput 비교

```python
import time, redis

r_no_cache = redis.Redis(decode_responses=True)
r_cache = redis.Redis(decode_responses=True, protocol=3,
                      cache_config=redis.cache.CacheConfig(max_size=10000))

# warmup
r_cache.set("hot:key", "v")

N = 100_000
t0 = time.perf_counter()
for _ in range(N):
    r_no_cache.get("hot:key")
print(f"no cache: {N / (time.perf_counter() - t0):.0f} ops/s")

t0 = time.perf_counter()
for _ in range(N):
    r_cache.get("hot:key")
print(f"with cache: {N / (time.perf_counter() - t0):.0f} ops/s")
```

기대 결과: with cache 가 5~50배 빠름 (RTT가 사라지므로).

---

## 8. Race condition 주의

```
[D] client → server: GET foo
[I] server → client: INVALIDATE foo (다른 클라이언트가 동시에 변경)
[D] server → client: "bar" (오래된 값)
```

→ 클라이언트가 "bar" 를 로컬 캐시에 저장 → 다음 GET 에서 stale.

해결: GET 전송 전에 placeholder 저장 → INVALIDATE 오면 placeholder 삭제 → 응답 도착 시 placeholder 없으면 캐싱 안 함.

```
1. 로컬: foo → "caching-in-progress"
2. server: GET foo
3. server: INVALIDATE foo (먼저 도착)
4. 로컬: foo 삭제 (placeholder 였음)
5. server: "bar" 응답
6. 로컬: foo 가 없음 → 캐싱 안 함
```

또는 RESP3 단일 connection 사용 → 메시지 순서 보장됨.

---

## 9. 연결 끊김 처리

invalidation 수신 connection 이 끊기면 그 사이 변경 알림 손실 → stale.

대응:
- 연결 끊김 감지 → **로컬 캐시 전체 flush**
- 정기 PING (Pub/Sub mode 에서도 PING 가능) → 죽은 연결 조기 감지

---

## 10. 무엇을 캐싱할까

| 적합 | 부적합 |
|---|---|
| 자주 GET, 가끔 변경 | 자주 변경 (counter 등) |
| 작은 값 | 거대 값 (메모리) |
| 모든 클라이언트가 같은 값 | 클라이언트별 다른 값 |
| TTL 있는 캐시 키 | session 처럼 보안 민감 |

---

## 11. 메모리 한계 / eviction

서버 측:
```
tracking-table-max-keys 1000000      # 추적 가능 최대 키 수
```

→ 초과 시 가장 오래된 키 invalidate (= 클라이언트는 강제 evict).

클라이언트 측:
- LRU 또는 fixed size 캐시
- 최대 키마다 TTL 부여 권장 (max age)

---

## 12. 흔한 함정

| 함정 | 설명 |
|---|---|
| 캐시 stale 가능성 무시 | placeholder + invalidation race 처리 필요. RESP3 추천. |
| 모든 키 캐싱 | 메모리 폭증. opt-in / max size 사용. |
| invalidation connection 끊김 후 재연결만 | flush 안 하면 stale. 연결 끊김 시 cache flush 필수. |
| Cluster에서 단일 broadcast | 슬롯별로 다른 노드. 노드별 tracking 필요. |
| BCAST + 너무 많은 prefix | 서버 CPU 부담. 적은 수의 의미 있는 prefix. |
| TTL 없는 영구 캐시 | 영원히 stale 가능 (invalidation 못 받았다면). max age 보호. |

---

## 13. 직접 해보기

1. `CLIENT TRACKING ON` 후 GET → 다른 클라이언트에서 SET → MONITOR 로 INVALIDATE 메시지 확인.
2. RESP3 single connection 으로 같은 시나리오 → push 메시지로 옴.
3. node-redis / redis-py 의 client-side cache 옵션 켜고 throughput 측정.
4. opt-in / opt-out / NOLOOP 각각 시험.
5. `tracking-table-max-keys 100` 으로 줄이고 200개 키 추적 시도 → 강제 evict 동작.

---

## 14. 참고 자료

- **[공식 문서] Client-side caching reference** — <https://redis.io/docs/latest/develop/reference/client-side-caching/>
  - 참고 부분: tracking 모델 / RESP2 vs RESP3 / opt-in/out / NOLOOP / race conditions — §1~§9 근거

- **[공식 문서] CLIENT TRACKING** — <https://redis.io/docs/latest/commands/client-tracking/>
  - 참고 부분: 옵션 (ON/OFF, REDIRECT, BCAST, OPTIN, OPTOUT, NOLOOP) — §2 근거

- **[공식 문서] CLIENT CACHING / CLIENT TRACKINGINFO / CLIENT UNTRACKING**
  - URL: 위 명령들 페이지
  - 참고 부분: opt-in 흐름 — §4 근거

- **[node-redis docs] Client-side caching**
  - URL: <https://github.com/redis/node-redis>
  - 참고 부분: clientSideCache 옵션 — §5 근거

- **[redis-py docs] Client-side cache**
  - URL: <https://redis.readthedocs.io/en/stable/>
  - 참고 부분: cache_config — §6 근거
