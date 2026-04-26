# 04. Pipelining & Batching

> **학습 목표**: Pipelining이 RTT를 어떻게 줄이는지, MULTI/EXEC 와 다른 점, MGET/MSET/HMGET 같은 명령이 사실상 batching인 이유를 이해한다.
> **예상 소요**: 20분

---

## 1. RTT 가 throughput을 좌우한다

Redis 자체는 빠르지만 (μs 단위), **네트워크 RTT** 가 LAN 1ms / WAN 10-50ms.

```
Sequential SET 100번 (RTT 1ms):
  - 100 * (1ms RTT + 0.05ms execute) = ~105ms

Pipelined SET 100번:
  - 1 * (1ms RTT + 100 * 0.05ms) = ~6ms
```

→ **수십 배 차이**.

---

## 2. Pipeline 사용

### Python (redis-py)

```python
import redis
r = redis.Redis()

# 일반 (느림)
for i in range(1000):
    r.set(f"k{i}", i)

# Pipeline (빠름)
with r.pipeline(transaction=False) as pipe:
    for i in range(1000):
        pipe.set(f"k{i}", i)
    pipe.execute()                  # 한 번에 전송 + 결과 받음
```

### Node.js (node-redis 5.x)

```javascript
import { createClient } from "redis";
const r = createClient(); await r.connect();

const pipe = r.multi();              // multi() 가 transaction
// 또는 pipeline 패턴
const promises = [];
for (let i = 0; i < 1000; i++) {
  promises.push(r.set(`k${i}`, String(i)));
}
await Promise.all(promises);         // node-redis 5+는 자동 pipelining
```

> node-redis 5+ 는 같은 connection의 동시 명령을 자동 파이프라이닝.
> 출처: <https://github.com/redis/node-redis> README "Auto-pipelining"

### Node.js (ioredis)

```javascript
import Redis from "ioredis";
const r = new Redis();

const pipe = r.pipeline();
for (let i = 0; i < 1000; i++) {
  pipe.set(`k${i}`, String(i));
}
const results = await pipe.exec();   // 결과 배열
```

ioredis는 `enableAutoPipelining: true` 옵션도 지원.

---

## 3. Pipeline vs MULTI/EXEC

| 항목 | Pipeline | MULTI/EXEC |
|---|---|---|
| 목적 | RTT 절약 | 원자적 + 격리 |
| 명령 사이 끼어들기 | 가능 | 불가 |
| 결과 받기 | execute() 시 한 번에 | EXEC 시 한 번에 |
| WATCH 가능 | ❌ (transaction=False) | ✅ |
| 성능 | 가장 빠름 (대량 batch) | Pipeline + atomic 비용 |

같은 라이브러리 메서드(`pipeline()`)가 옵션 `transaction=True/False` 로 둘 다 지원하는 경우 많음.

---

## 4. MGET/MSET/HMGET — 명령 자체가 batching

```python
# 100번 GET
for i in range(100):
    r.get(f"k{i}")          # 100 RTT

# 한 MGET 명령으로
r.mget([f"k{i}" for i in range(100)])   # 1 RTT
```

가능하면 해당 자료형의 multi-key 명령 사용:
- `MSET / MGET` (String)
- `HMGET / HMSET` (Hash)
- `SADD / SREM` (Set, 한 번에 여러 member)
- `ZADD` (한 번에 여러 score-member)

---

## 5. Connection Pool

매 명령마다 새 connection 만들면 **TCP handshake 비용** 발생.
**Pool로 connection 재사용**.

### Python (redis-py)

```python
pool = redis.ConnectionPool(host="127.0.0.1", port=6379, max_connections=20)
r = redis.Redis(connection_pool=pool)
# r 인스턴스 여럿에 같은 pool 공유 가능
```

### Node.js (node-redis 5+)

```javascript
import { createClientPool } from "redis";
const pool = createClientPool({ url: "redis://127.0.0.1:6379" }, { maximum: 20 });
const r = await pool.connect();
```

### 클러스터에서

cluster-aware 클라이언트는 노드별 pool을 자동 관리. `pool_size` 등 옵션 확인.

---

## 6. Pipeline 적정 크기

너무 작으면: 효과 적음
너무 크면:
- **메모리 폭증** (응답 버퍼)
- **첫 응답 지연** (다 끝나야 받음)
- **단일 스레드 점유**

권장: **100~1000 명령 단위** 부터 시작, 워크로드별로 측정.

---

## 7. 흔한 함정

| 함정 | 설명 |
|---|---|
| Pipeline 결과를 보고 다음 명령 분기 | execute() 가 끝나야 결과 받음. 분기 필요하면 chunk로. |
| MULTI/EXEC 안에 BLOCKING 명령 (BLPOP 등) | 거부됨. |
| Cluster에서 Pipeline + 다중 슬롯 | 클라이언트가 노드별로 분리 후 병렬 전송. 일부 라이브러리는 안 됨. |
| Pool 크기 너무 작음 | 동시 요청 많으면 대기. CPU 코어 + 워커 수 고려. |
| Pool 크기 너무 큼 | 서버에 connection 너무 많음 → maxclients 도달 위험. |

---

## 8. 직접 해보기

1. 1000개 SET — Pipeline vs 일반 → 시간 비교.
2. MGET 100개 vs GET 100번 → 시간 비교.
3. `INFO clients` → connected_clients 변화 (pool 효과).
4. Pipeline 크기 10/100/1000/10000 → 최적점 찾기.
5. ioredis `enableAutoPipelining: true` 효과 측정.

---

## 9. 참고 자료

- **[공식 문서] Pipelining**
  - URL: <https://redis.io/docs/latest/develop/use/pipelining/>
  - 참고 부분: RTT 모델 + 사용 예 — §1, §2 근거

- **[redis-py docs] Pipeline / ConnectionPool**
  - URL: <https://redis.readthedocs.io/en/stable/connections.html#connection-pools>
  - 참고 부분: pipeline / pool 사용 — §2, §5 근거

- **[node-redis README] Auto-pipelining**
  - URL: <https://github.com/redis/node-redis>
  - 참고 부분: 자동 pipelining 동작 — §2 근거

- **[ioredis] Pipelining**
  - URL: <https://github.com/redis/ioredis#pipelining>
  - 참고 부분: pipeline().exec() — §2 근거
