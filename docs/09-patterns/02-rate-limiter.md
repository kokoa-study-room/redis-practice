# 02. Rate Limiter

> **학습 목표**: Fixed Window / Sliding Window / Token Bucket 세 가지 알고리즘을 Redis로 구현하고, 각 trade-off를 안다.
> **예상 소요**: 30분

---

## 1. 알고리즘 비교

| 알고리즘 | 정확도 | 복잡도 | 메모리 |
|---|---|---|---|
| Fixed Window (`INCR`) | 낮음 (윈도 경계 burst 가능) | 매우 단순 | 키 1개/사용자 |
| Sliding Window Counter | 중간 | 단순 | 키 1~2개/사용자 |
| Sliding Window Log (`ZSET`) | 높음 | 중간 | 윈도 내 요청 수만큼 |
| Token Bucket (`Lua`) | 높음 (burst 허용) | 중간 | Hash 1개/사용자 |
| Leaky Bucket | 높음 | 중간 | Hash 1개/사용자 |

---

## 2. Fixed Window (가장 단순)

```python
def fixed_window(user_id, limit=100, window_sec=60):
    now = int(time.time())
    bucket = now // window_sec
    key = f"rl:{user_id}:{bucket}"
    
    pipe = r.pipeline()
    pipe.incr(key)
    pipe.expire(key, window_sec)
    count, _ = pipe.execute()
    
    return count <= limit
```

**문제**: 윈도 경계에서 burst.
00:00:59에 100개 + 00:01:00에 100개 = 1초에 200개 가능.

---

## 3. Sliding Window Log (정확)

ZSET에 요청 timestamp를 멤버로 저장 → 윈도 밖 제거 → 카운트.

```python
def sliding_window_log(user_id, limit=100, window_sec=60):
    now = time.time()
    key = f"rl:{user_id}"
    
    pipe = r.pipeline()
    pipe.zremrangebyscore(key, 0, now - window_sec)        # 만료 제거
    pipe.zcard(key)                                          # 현재 수
    pipe.zadd(key, {f"{now}:{uuid.uuid4()}": now})           # 새 요청 추가
    pipe.expire(key, window_sec)
    _, count, _, _ = pipe.execute()
    
    return count < limit
```

**문제**: 메모리 = 윈도 내 모든 요청 수. 100 RPS × 60s = 6000개 멤버/사용자.

---

## 4. Token Bucket (Lua, 가장 우아)

```lua
-- KEYS[1] = bucket key
-- ARGV[1] = capacity
-- ARGV[2] = refill_rate (per sec)
-- ARGV[3] = now_ms

local capacity = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local data = redis.call('HMGET', KEYS[1], 'tokens', 'last')
local tokens = tonumber(data[1]) or capacity
local last = tonumber(data[2]) or now

local elapsed_sec = (now - last) / 1000
tokens = math.min(capacity, tokens + elapsed_sec * rate)

if tokens < 1 then
    redis.call('HSET', KEYS[1], 'tokens', tokens, 'last', now)
    return 0
else
    tokens = tokens - 1
    redis.call('HSET', KEYS[1], 'tokens', tokens, 'last', now)
    redis.call('PEXPIRE', KEYS[1], math.ceil(capacity / rate * 1000))
    return 1
end
```

```python
TOKEN_BUCKET = open("token_bucket.lua").read()

def token_bucket(user_id, capacity=10, rate=1):
    now_ms = int(time.time() * 1000)
    return r.eval(TOKEN_BUCKET, 1, f"rl:{user_id}", capacity, rate, now_ms) == 1
```

**장점**: burst 허용 (capacity까지 누적), 평균 rate 유지.

---

## 5. Sliding Window Counter (Hybrid)

Fixed Window 두 개 (이전/현재) 의 가중 합:

```python
def sliding_window_counter(user_id, limit=100, window_sec=60):
    now = time.time()
    current_bucket = int(now) // window_sec
    elapsed_in_window = (now % window_sec) / window_sec
    
    cur_key = f"rl:{user_id}:{current_bucket}"
    prev_key = f"rl:{user_id}:{current_bucket - 1}"
    
    pipe = r.pipeline()
    pipe.incr(cur_key); pipe.expire(cur_key, 2 * window_sec)
    pipe.get(prev_key)
    cur_count, _, prev_count = pipe.execute()
    
    weighted = int(prev_count or 0) * (1 - elapsed_in_window) + cur_count
    return weighted <= limit
```

**장점**: 메모리 적고 정확도 중간 이상.

---

## 6. Redis 8.8-M02 신규 — GCRA Rate Limiter

8.8-M02 부터 Redis 자체에 GCRA(Generic Cell Rate Algorithm) 기반 rate limiter가 추가된다 (PR #14826, #14905, redis-cell 모듈 기반).

> 출처: <https://github.com/redis/redis/releases/tag/8.8-m02>
> 참고 부분: "GCRA (generic cell rate algorithm) rate limiter (based on the redis-cell module by @brandur)"

8.6.x 기준에서는 위의 Lua 패턴을 쓰고, 8.8 GA 출시 후 GCRA 명령으로 마이그레이션 가능.

---

## 7. 흔한 함정

| 함정 | 설명 |
|---|---|
| Fixed Window의 경계 burst | Sliding Window 또는 Token Bucket으로 |
| Lua 안에서 시간 직접 가져오기 | 결정적이지 않음 → ARGV로 now 전달 |
| ZSET에 같은 timestamp 두 요청 | 중복으로 무시됨. UUID 등으로 unique 멤버 |
| TTL 안 줌 | 키 누적. EXPIRE 필수 |
| 분산 환경에서 Redis 없을 때 fallback | Redis 죽었을 때 정책 정의 (open vs closed) |

---

## 8. 직접 해보기

1. 위 4가지 패턴 중 2개 이상 구현 → 200 req/sec 시뮬레이션 → 통과/거부 비율.
2. Fixed Window 경계에서 burst 재현 (timestamp 0:59, 1:00 두 시점).
3. Token Bucket의 burst 동작 (10초 비활성 후 한 번에 10 요청 통과).
4. RedisInsight에서 ZSET (sliding log) 키 시각화.

---

## 9. 참고 자료

- **[블로그] Stripe — Scaling your API with rate limiters**
  - URL: <https://stripe.com/blog/rate-limiters>
  - 참고 부분: GCRA / Token Bucket 비교 — §1, §6 근거

- **[GitHub] brandur/redis-cell**
  - URL: <https://github.com/brandur/redis-cell>
  - 참고 부분: GCRA 알고리즘 — §6 근거 보충

- **[GitHub] redis/redis 8.8-M02 release notes**
  - URL: <https://github.com/redis/redis/releases/tag/8.8-m02>
  - 참고 부분: GCRA 8.8 통합 — §6 근거

- **[공식 문서] Redis as a rate limiter (튜토리얼)**
  - URL: <https://redis.io/learn/howtos/solutions/microservices/api-rate-limiting>
  - 참고 부분: 패턴 예시 — §2~§5 보충
