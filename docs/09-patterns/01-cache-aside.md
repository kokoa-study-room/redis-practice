# 01. Cache-Aside (Lazy Loading)

> **학습 목표**: 가장 흔한 캐시 패턴을 안전하게 구현하고 cache stampede / inconsistency 같은 함정을 피한다.
> **예상 소요**: 25분

---

## 1. 기본 흐름

```
read:
  v = redis.get(key)
  if v is None:
    v = db.query(key)
    redis.set(key, v, ex=300)   # TTL 5분
  return v

write:
  db.update(key, new_v)
  redis.delete(key)            # invalidation (다음 read에서 다시 채워짐)
```

장점:
- 단순
- DB가 source of truth
- 캐시 누락에도 동작 (느릴 뿐)

---

## 2. Python 구현

```python
import json, redis
r = redis.Redis(decode_responses=True)

CACHE_TTL = 300

def get_user(user_id: int):
    key = f"user:{user_id}"
    cached = r.get(key)
    if cached:
        return json.loads(cached)
    user = db.fetch_user(user_id)              # DB 조회
    if user:
        r.set(key, json.dumps(user), ex=CACHE_TTL)
    return user

def update_user(user_id: int, data: dict):
    db.update_user(user_id, data)
    r.delete(f"user:{user_id}")                # 캐시 무효화
```

---

## 3. 함정 1 — Cache Stampede (Thundering Herd)

상황: TTL 만료 직후, 1000개 요청이 동시에 캐시 miss → 1000번 동시에 DB 조회.

### 해결 1: 락 (Lock)

```python
import time
from redis.lock import Lock

def get_user_safe(user_id: int):
    key = f"user:{user_id}"
    cached = r.get(key)
    if cached:
        return json.loads(cached)
    
    lock = Lock(r, f"lock:{key}", timeout=10, blocking_timeout=5)
    if lock.acquire(blocking=True):
        try:
            cached = r.get(key)               # 다시 확인 (다른 스레드가 채웠을 수도)
            if cached:
                return json.loads(cached)
            user = db.fetch_user(user_id)
            r.set(key, json.dumps(user), ex=CACHE_TTL)
            return user
        finally:
            lock.release()
    else:
        # 락 못 잡음 → 잠시 대기 후 캐시 다시
        time.sleep(0.1)
        return json.loads(r.get(key) or "null")
```

### 해결 2: Probabilistic Early Refresh

만료 임박할수록 일부 요청이 미리 갱신.

```python
import math, random, time

def get_user_xfetch(user_id: int):
    key = f"user:{user_id}"
    cached = r.get(key)
    ttl = r.ttl(key)
    if cached:
        # delta = "갱신에 걸린 시간 추정"
        delta = 0.05  # 50ms 가정
        beta = 1.0
        if random.random() * delta * beta * math.log(random.random()) < -ttl:
            # 일찍 갱신 (확률적)
            return refresh_and_return(key, user_id)
        return json.loads(cached)
    return refresh_and_return(key, user_id)
```

> 출처: <https://www.vldb.org/pvldb/vol8/p886-vattani.pdf> "XFetch" 알고리즘

### 해결 3: Redis 자체에서 lua로 lock + fetch

(02-lua-scripts 챕터의 패턴 응용)

---

## 4. 함정 2 — Stale Data

read-after-write 일관성 깨질 수 있음:
1. write: DB 업데이트 + DEL key
2. 그 사이 다른 read: SET key (옛 값)
→ 캐시에 옛 값.

### 해결: Double Delete

```python
def update_user(user_id, data):
    r.delete(f"user:{user_id}")        # 1차
    db.update_user(user_id, data)
    time.sleep(0.5)                    # 짧게 대기 (옵션)
    r.delete(f"user:{user_id}")        # 2차
```

### 해결: Write-through (캐시 먼저 갱신)

```python
def update_user(user_id, data):
    db.update_user(user_id, data)
    r.set(f"user:{user_id}", json.dumps(data), ex=CACHE_TTL)
```

캐시-DB 불일치 가능성 있어 적합한 케이스에만.

---

## 5. 함정 3 — Negative Cache (없음을 캐싱)

DB에 없는 키를 매번 조회하면 DB 부하. 없음(`None`)도 짧게 캐싱:

```python
NULL_TTL = 60

def get_user_with_negative(user_id):
    key = f"user:{user_id}"
    cached = r.get(key)
    if cached == "__NULL__":
        return None
    if cached:
        return json.loads(cached)
    user = db.fetch_user(user_id)
    if user is None:
        r.set(key, "__NULL__", ex=NULL_TTL)
    else:
        r.set(key, json.dumps(user), ex=CACHE_TTL)
    return user
```

장점: DB 부하 차단.
단점: 잠시 후 데이터 추가돼도 NULL_TTL 동안 못 봄.

---

## 6. 함정 4 — TTL 미설정

```python
r.set(f"user:{user_id}", json.dumps(user))   # ❌ TTL 없음
```

→ 영원히 메모리에 누적. 반드시 `ex=`.

---

## 7. 메모리 정책 (Eviction)

```
maxmemory 2gb
maxmemory-policy allkeys-lru
```

캐시 용도는 **`allkeys-lru`** (또는 LFU) 권장. **noeviction** 이면 가득 차면 에러.

---

## 8. 직접 해보기

1. Cache-aside 함수 작성 → seed-data.sh의 product 데이터로 테스트.
2. 1000개 요청 동시에 → DB 조회 횟수 측정 (락 적용 vs 미적용).
3. NULL caching 적용 후 존재 안 하는 키를 100번 조회 → DB 호출 1번만 가는지.
4. RedisInsight Profiler로 SET/GET 흐름 관찰.

---

## 9. 참고 자료

- **[블로그/논문] Cache stampede / XFetch**
  - URL: <https://www.vldb.org/pvldb/vol8/p886-vattani.pdf>
  - 참고 부분: probabilistic early refresh — §3 해결 2 근거

- **[공식 문서] Eviction policies**
  - URL: <https://redis.io/docs/latest/operate/oss_and_stack/management/eviction/>
  - 참고 부분: allkeys-lru / volatile-lru — §7 근거

- **[공식 문서] redis-py Lock**
  - URL: <https://redis.readthedocs.io/en/stable/connections.html#redis.Redis.lock>
  - 참고 부분: Lock 사용법 — §3 해결 1 근거
