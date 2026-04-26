# 01. Python — redis-py 7.4

> **학습 목표**: redis-py의 sync/async 사용, decode_responses 옵션, ConnectionPool, RESP3, Sentinel/Cluster 클라이언트 사용법을 안다.
> **예상 소요**: 25분

---

## 1. 설치

```bash
pip install "redis[hiredis]==7.4.0"
```

`hiredis` extras: C로 작성된 고속 응답 파서. 대부분 **그냥 더 빠름**, 코드 변경 불필요.

---

## 2. Sync 기본

```python
import redis

r = redis.Redis(host="127.0.0.1", port=6379, db=0,
                decode_responses=True)

r.set("name", "Kim")
print(r.get("name"))   # "Kim"

# decode_responses=False (기본): bytes 반환
r2 = redis.Redis()
print(r2.get("name"))  # b'Kim'
```

> **decode_responses=True** 는 학습/일반 앱에는 편하지만, **바이너리 저장이 섞여 있으면 인코딩 에러** 발생. 바이너리 키는 별도 인스턴스로 분리.

---

## 3. Async

```python
import asyncio
import redis.asyncio as redis

async def main():
    r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)
    await r.set("k", 1)
    print(await r.get("k"))
    await r.aclose()        # 반드시 호출

asyncio.run(main())
```

> redis-py 5.0+ 부터 `redis.asyncio` 가 표준. 옛 `aredis`/`asyncio_redis` 같은 별도 라이브러리는 deprecated.

---

## 4. Connection Pool

```python
pool = redis.ConnectionPool(host="127.0.0.1", port=6379, max_connections=20)
r = redis.Redis(connection_pool=pool)

# 같은 pool을 다른 Redis 인스턴스와 공유 가능
r2 = redis.Redis(connection_pool=pool)
```

기본은 **인스턴스마다 자체 pool** 자동 생성. 명시적으로 만들면 여러 인스턴스가 공유 가능.

Async용:
```python
import redis.asyncio as aioredis

pool = aioredis.ConnectionPool.from_url("redis://127.0.0.1:6379", max_connections=20)
r = aioredis.Redis(connection_pool=pool)
```

---

## 5. Pipeline / Transaction

```python
# Transaction (MULTI/EXEC)
with r.pipeline() as pipe:
    pipe.set("a", 1)
    pipe.incr("b")
    results = pipe.execute()    # [True, 1]

# Pure pipeline (no MULTI/EXEC, 더 빠름)
with r.pipeline(transaction=False) as pipe:
    for i in range(1000):
        pipe.set(f"k{i}", i)
    pipe.execute()

# WATCH 패턴
with r.pipeline() as pipe:
    while True:
        try:
            pipe.watch("balance")
            current = int(pipe.get("balance") or 0)
            if current < 100: pipe.unwatch(); break
            pipe.multi()
            pipe.decrby("balance", 100)
            pipe.execute()
            break
        except redis.WatchError:
            continue
```

---

## 6. Pub/Sub

```python
ps = r.pubsub()
ps.subscribe("news")

for msg in ps.listen():
    if msg["type"] == "message":
        print(msg["data"])
```

또는 콜백:
```python
def handler(msg):
    print("got:", msg["data"])

ps.subscribe(news=handler)
ps.run_in_thread(sleep_time=0.001)   # 백그라운드 스레드
```

> Pub/Sub은 별도 connection 권장 (subscribe 중에는 일반 명령 못 보냄).

---

## 7. RESP3

```python
r = redis.Redis(host="127.0.0.1", port=6379, protocol=3, decode_responses=True)
```

차이:
- **map / set / push** 같은 새 타입을 그대로 받음 (RESP2는 모두 array)
- 일부 명령(`CLIENT INFO`, `XINFO STREAM` 등)이 더 자연스러운 dict 반환
- Push 통보 (RedisInsight도 사용)

---

## 8. Sentinel

```python
from redis.sentinel import Sentinel

sentinel = Sentinel([("127.0.0.1", 26379),
                     ("127.0.0.1", 26380),
                     ("127.0.0.1", 26381)])

master = sentinel.master_for("mymaster", decode_responses=True)
master.set("k", 1)

slave = sentinel.slave_for("mymaster", decode_responses=True)
print(slave.get("k"))
```

failover 후에도 `master_for` 가 자동으로 새 master 발견.

---

## 9. Cluster

```python
from redis.cluster import RedisCluster

rc = RedisCluster(host="127.0.0.1", port=7001, decode_responses=True)
rc.set("foo", "bar")        # 자동 슬롯 라우팅

# 멀티 키 (같은 슬롯)
rc.mset({"{u:1}:a": 1, "{u:1}:b": 2})

# Pipeline (제한적: 한 노드 단위)
pipe = rc.pipeline()
pipe.set("{u:1}:x", 10)
pipe.set("{u:1}:y", 20)
pipe.execute()
```

---

## 10. 흔한 함정

| 함정 | 설명 |
|---|---|
| `decode_responses=True` + 바이너리 | UnicodeDecodeError. 분리. |
| async에서 `aclose()` 안 함 | connection 누수, 종료 지연. |
| Pub/Sub과 일반 명령 같은 connection | SUBSCRIBE 후 일반 명령 거부. |
| max_connections 안 줌 | 기본은 매우 큼. fork 자식 프로세스에서 connection 공유로 사고. |
| WATCH 재시도 무한 | 무한 충돌 시 백오프 + 횟수 제한. |

---

## 11. 직접 해보기

1. seed-data.sh → `r.scan_iter("demo:*")` 로 키 순회.
2. asyncio로 `r.incr("c")` 100개 동시 실행 → 결과 정합성.
3. Pipeline 1000 SET 시간 측정 vs 일반 1000 SET.
4. RESP3 protocol=3 연결 후 `CLIENT INFO` 결과 비교.
5. 본 프로젝트 examples/python 디렉토리에 직접 코드 배치.

---

## 12. 참고 자료

- **[공식 문서] redis-py readthedocs**
  - URL: <https://redis.readthedocs.io/en/stable/>
  - 참고 부분: 전반 — §2~§9 근거

- **[GitHub] redis/redis-py 7.4.0 release**
  - URL: <https://github.com/redis/redis-py/releases>
  - 참고 부분: 7.4.0 변경 사항 — 본 문서 기준 버전 근거

- **[공식 문서] asyncio examples**
  - URL: <https://redis.readthedocs.io/en/stable/examples/asyncio_examples.html>
  - 참고 부분: aclose / 기본 패턴 — §3 근거
