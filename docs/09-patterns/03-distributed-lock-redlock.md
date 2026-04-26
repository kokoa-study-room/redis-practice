# 03. 분산 락 (Distributed Lock)

> **학습 목표**: `SET NX EX` + Lua 안전 해제로 분산 락 구현, Redlock 알고리즘과 그 논쟁(Kleppmann vs antirez), 라이브러리 사용 권고.
> **예상 소요**: 30분

---

## 1. 단순 락 (Single instance)

```
SET lock:foo <random_token> NX EX 30
```

- `NX`: 없을 때만 SET (락 획득)
- `EX 30`: 30초 후 자동 만료 (잡고 죽어도 영원히 잠기지 않음)
- `random_token`: 자기 락임을 확인할 ID (UUID)

해제:
```lua
-- KEYS[1] = lock key
-- ARGV[1] = my token
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
else
    return 0
end
```

**왜 Lua?** GET 후 다른 클라이언트가 잠시 잡았는데 내가 DEL 하는 사고 방지.

---

## 2. Python 구현

```python
import uuid, redis
r = redis.Redis(decode_responses=True)

RELEASE = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
else
    return 0
end
"""

def acquire(name, ttl=30):
    token = str(uuid.uuid4())
    if r.set(f"lock:{name}", token, nx=True, ex=ttl):
        return token
    return None

def release(name, token):
    return r.eval(RELEASE, 1, f"lock:{name}", token)

# 사용
token = acquire("job:foo")
if token:
    try:
        do_work()
    finally:
        release("job:foo", token)
```

또는 **redis-py 내장 Lock**:
```python
with r.lock("lock:foo", timeout=30, blocking_timeout=10) as lock:
    do_work()
```

---

## 3. 락 연장 (extend)

긴 작업: TTL이 짧으면 끝나기 전에 만료. 주기적으로 연장:

```lua
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('PEXPIRE', KEYS[1], ARGV[2])
else
    return 0
end
```

```python
EXTEND = open("extend.lua").read()
def extend(name, token, ttl_ms):
    return r.eval(EXTEND, 1, f"lock:{name}", token, ttl_ms)
```

---

## 4. Redlock — 멀티 인스턴스 락

단일 Redis 노드는 죽으면 락 정보 손실 → Redlock은 N개 독립 Redis에 동시 락.

알고리즘:
1. 현재 시각 t1
2. N개 인스턴스에 동시 SET NX EX 시도
3. (N/2 + 1) 이상 성공 + (t2 - t1) < TTL 이면 락 획득.
4. 실패하면 모든 인스턴스에 release.

```python
from redis.cluster import RedisCluster   # 또는
from redlock import Redlock              # python-redlock 라이브러리

# 5개 독립 Redis 인스턴스
dlm = Redlock([{"host": "r1", "port": 6379},
               {"host": "r2", "port": 6379},
               {"host": "r3", "port": 6379},
               {"host": "r4", "port": 6379},
               {"host": "r5", "port": 6379}])

lock = dlm.lock("resource", 30000)  # 30초
if lock:
    try:
        do_work()
    finally:
        dlm.unlock(lock)
```

> 출처: <https://redis.io/docs/latest/develop/use/patterns/distributed-locks/>

---

## 5. Kleppmann의 Redlock 비판

Martin Kleppmann (저자, "Designing Data-Intensive Applications") 가 Redlock의 안전성에 의문 제기 (2016):

핵심 비판:
1. **GC pause / 네트워크 지연** 으로 락 보유 클라이언트의 행위가 락 만료 후로 늦어질 수 있음
2. **시스템 시계 점프** (NTP 등)에 안전하지 않음
3. fencing token (단조 증가 ID) 가 없어서, 만료된 락 보유자가 외부 자원에 write 하면 막을 방법 없음

antirez (Redis 저자)의 반박:
1. 모든 분산 락은 GC pause / 시계 문제에 어느 정도 노출됨
2. fencing은 락 자체의 책임이 아니라 외부 자원의 책임
3. 정확성이 절대 보장 필요한 경우(은행 거래)는 분산 락 자체가 부적합 (별도 트랜잭션 시스템 필요)

> 출처:
> - Kleppmann: <https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html>
> - antirez 반박: <http://antirez.com/news/101>

**실용 결론**:
- **상호배제만 필요 (효율 목적)**: 단일 Redis SET NX EX 충분.
- **정확성 절대 보장 필요**: Redlock보다 ZooKeeper / etcd / DB 트랜잭션.
- 그 사이라면 검증된 라이브러리 사용 (`redlock-py`, `Redisson`).

---

## 6. 흔한 함정

| 함정 | 설명 |
|---|---|
| TTL 없이 SET NX | 잡고 죽으면 영원히 잠김 |
| 락 키 그대로 DEL | 다른 클라이언트의 락을 풀 수 있음. Lua 안전 해제. |
| 너무 짧은 TTL | 작업 끝나기 전에 만료. extend 필요. |
| Cluster에서 락 키 분산 | 한 키만 쓰면 한 노드. hashtag로 같은 슬롯 강제. |
| 동기 코드에서 blocking 락 무한 대기 | timeout 설정 |
| Redis 죽으면 모든 락 사라짐 | Redlock은 이를 완화하지만 완전 해결 아님 |

---

## 7. 직접 해보기

1. 두 터미널에서 같은 락 동시 acquire → 한 쪽만 성공.
2. 하나가 잡고 30초 sleep → 다른 한 쪽은 30초 후 acquire 가능.
3. 안전 해제 Lua 적용 안 한 버전과 적용 버전 비교 (시뮬레이션).
4. (도전) python-redlock 으로 5노드 Redis (학습용 docker-compose 5개 띄워서) Redlock.

---

## 8. 참고 자료

- **[공식 문서] Distributed Locks**
  - URL: <https://redis.io/docs/latest/develop/use/patterns/distributed-locks/>
  - 참고 부분: SET NX EX, Lua 안전 해제, Redlock — §1, §4 근거

- **[블로그] Kleppmann — How to do distributed locking**
  - URL: <https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html>
  - 참고 부분: Redlock 비판 — §5 근거

- **[블로그] antirez — Is Redlock safe?**
  - URL: <http://antirez.com/news/101>
  - 참고 부분: 반박 — §5 근거

- **[공식 문서] redis-py Lock**
  - URL: <https://redis.readthedocs.io/en/stable/connections.html#redis.Redis.lock>
  - 참고 부분: 내장 Lock 사용 — §2 근거
