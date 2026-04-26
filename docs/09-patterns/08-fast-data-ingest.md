# 08. Fast Data Ingest — 초당 수십만 이벤트 받기

> **학습 목표**: 대량 이벤트를 Redis에 효율적으로 적재하는 패턴 — pipelining, MULTI batch, Stream 사용, 비동기 worker 분리, back-pressure 다루기.
> **예상 소요**: 25분

---

## 1. 시나리오

- IoT 센서 100만 대가 5초마다 데이터 전송 → 초당 20만 이벤트
- 클릭스트림 / 광고 노출 로그
- 게임 이벤트 (점수 / 위치 / 채팅)
- 금융 tick 데이터

→ Redis 가 받기에 충분히 빠르지만, **client / 네트워크 측이 병목**이 되기 쉬움.

---

## 2. 단순한 방법 (느림)

```python
for event in stream:
    r.xadd("events", event)        # 매 이벤트마다 RTT 1회
```

LAN RTT 200μs → 초당 5,000 events 한계.

---

## 3. 패턴 1 — Pipelining (가장 효과적)

```python
BATCH_SIZE = 1000

def ingest_batch(events):
    with r.pipeline(transaction=False) as pipe:
        for event in events:
            pipe.xadd("events", event)
        pipe.execute()
```

성능: RTT 1회로 1000 명령 → 초당 ~수십만 이벤트 가능.

---

## 4. 패턴 2 — Aggregator pattern (앱 단에서 모으고 보내기)

```python
import asyncio
from collections import deque

queue = deque()

async def producer(event):
    queue.append(event)

async def flusher():
    while True:
        await asyncio.sleep(0.01)   # 10ms마다 flush
        if not queue: continue
        
        batch = []
        while queue and len(batch) < 1000:
            batch.append(queue.popleft())
        
        async with r.pipeline(transaction=False) as pipe:
            for event in batch:
                pipe.xadd("events", event)
            await pipe.execute()
```

→ 10ms 윈도 / 1000개 batch 의 trade-off. 지연 vs throughput.

---

## 5. 패턴 3 — Stream + Consumer Group (안전 분산 처리)

```python
# Producer
def ingest(event):
    r.xadd("events", event, maxlen=("~", 10_000_000))   # 1천만 cap

# Consumer (워커 N개)
GROUP = "workers"
try:
    r.xgroup_create("events", GROUP, id="0", mkstream=True)
except Exception: pass

def worker(name):
    while True:
        resp = r.xreadgroup(GROUP, name, {"events": ">"}, count=100, block=1000)
        if not resp: continue
        for _, entries in resp:
            ids_to_ack = []
            for id_, fields in entries:
                process(fields)             # downstream (DB / Kafka 등)
                ids_to_ack.append(id_)
            r.xack("events", GROUP, *ids_to_ack)
```

→ Producer 는 빠르게 적재만, Consumer N개가 분산 처리.
→ 한 consumer 죽어도 PEL 에 남아 다른 consumer 가 XCLAIM.

---

## 6. 패턴 4 — Sharding (한 키 한 노드 한계 돌파)

단일 Stream 키는 한 Cluster 노드에 묶임. 매우 큰 부하 시:

```python
NUM_SHARDS = 16

def ingest_sharded(event):
    shard = hash(event["user_id"]) % NUM_SHARDS
    r.xadd(f"events:{shard}", event)

# Consumer 도 shard 별
def worker(shard, name):
    while True:
        r.xreadgroup(GROUP, name, {f"events:{shard}": ">"}, count=100, block=1000)
        ...
```

→ Cluster 노드 N개에 분산 → 노드 수만큼 throughput 증가.

---

## 7. 패턴 5 — RESP3 push + auto-pipelining (node-redis 5+)

```javascript
import { createClient } from "redis";
const r = createClient({ url: "redis://...", RESP: 3 });
await r.connect();

// Promise.all 만으로 자동 pipelining
const events = generateEvents(10000);
await Promise.all(events.map(e => r.xAdd("events", "*", e)));
```

→ 같은 connection 으로 동시 명령이 자동으로 batch 됨.

---

## 8. Back-pressure — Consumer 가 못 따라잡을 때

증상:
- Stream length 무한 증가
- 메모리 폭증
- Producer 도 결국 느려짐

대응:

### 8.1 MAXLEN cap 강제
```
XADD events MAXLEN '~' 10000000 '*' ...
```
가장 오래된 entry 부터 폐기. **데이터 손실 가능 — 비즈니스 OK 인지 확인**.

### 8.2 외부 buffer (Kafka 등)
Redis Stream → Kafka 로 ETL. Kafka 가 영구 저장 / replay.

### 8.3 Producer rate limit
```python
async def ingest_with_limit(event):
    while r.xlen("events") > 5_000_000:
        await asyncio.sleep(0.1)
    r.xadd("events", event)
```

### 8.4 Consumer scale-out
워커 수 증가 또는 sharding.

---

## 9. List vs Stream 선택

| 항목 | List + LPUSH/BLPOP | Stream + Consumer Group |
|---|---|---|
| Throughput | 매우 높음 | 높음 (살짝 낮음) |
| 컨슈머 죽음 회복 | ❌ | ✅ (PEL) |
| fan-out | ❌ | ✅ (그룹별) |
| MAXLEN cap | LTRIM (수동) | 명령 안에 (자동) |
| ID 추적 | 직접 구현 | 내장 |
| 적합 | 단순 작업 큐 | 안전 / 영속 / 분산 |

대량 이벤트 ingest 는 보통 **Stream + Consumer Group** 권장.

---

## 10. Pipelining 한계

```python
# 너무 큰 pipeline
with r.pipeline(transaction=False) as pipe:
    for i in range(1_000_000):    # 100만
        pipe.xadd("events", {"i": i})
    pipe.execute()                 # 응답 대기 / 메모리 폭증
```

→ Redis 가 100만 응답 모두 만들어 client 에 보냄. 응답 메모리 + client 처리 부담.

권장: **batch 1000~10000 단위로 분할**.

---

## 11. 메트릭 모니터링

| 메트릭 | 의미 |
|---|---|
| `XLEN events` | 현재 길이 — 증가 추세면 consumer 못 따라잡음 |
| `XPENDING events <group>` | PEL 크기 |
| `INFO stats` `total_commands_processed` rate | 초당 명령 수 |
| `INFO clients` `connected_clients` | 연결 수 (너무 많으면 connection pool 조정) |
| Stream 메모리 (`MEMORY USAGE events`) | 메모리 사용 |

---

## 12. 흔한 함정

| 함정 | 설명 |
|---|---|
| 매 이벤트마다 connect | TCP handshake 비용. Connection pool 필수. |
| MAXLEN 안 함 | Stream 무한 증가. `~ N` 이 가장 효율적. |
| 동기 1-by-1 | 단일 producer throughput 매우 낮음. pipeline 필수. |
| Pipeline 너무 큼 | 응답 메모리 폭증. 1000~10000 단위. |
| Consumer 1개 | 한 워커 한계 = 한 노드 한계. N개 + sharding. |
| `XADD events *` 의 단일 키 | Cluster 에서 한 노드 한계. sharding. |
| ack 잊음 | PEL 무한 증가. XAUTOCLAIM 보조. |

---

## 13. 측정 — 실제 throughput

```bash
# producer 시뮬
docker run --rm --network host redislabs/memtier_benchmark \
  -s 127.0.0.1 -p 6379 \
  --command "XADD events * field value" \
  -t 4 -c 25 --test-time=30
```

스트림 길이:
```
redis-cli XLEN events
```

기대치: 단일 노드 ~수십만~수백만 events/sec (네트워크 / payload 크기에 따라).

---

## 14. 직접 해보기

1. 100만 이벤트 적재 — naive vs pipeline (1000) vs pipeline (10000) 비교.
2. Stream + Consumer Group 으로 producer 1, consumer 4 설정 → 분배 확인.
3. MAXLEN 5만으로 cap 한 후 100만 적재 → 결국 5만 부근 유지 확인.
4. 일부러 Consumer 1개만 두고 producer 빠르게 → XLEN 폭증 모니터.
5. (Cluster) sharding 으로 4 슬롯에 분산 → 단일 vs 4-shard throughput 비교.

---

## 15. 참고 자료

- **[Redis Solutions] Fast data ingest** — <https://redis.io/solutions/fast-data-ingest/>
  - 참고 부분: 패턴 / 사용 사례 — §1 근거

- **[Redis Tutorial] Fast data ingest pipeline with Redis** — <https://redis.io/tutorials/fast-data-ingest-pipeline-with-redis/>
  - 참고 부분: pipeline / batching — §3 근거

- **[공식 문서] Pipelining** — <https://redis.io/docs/latest/develop/use/pipelining/>
  - 참고 부분: RTT 절감 / batch 크기 — §3, §10 근거

- **[공식 문서] Streams Tutorial — XADD MAXLEN** — <https://redis.io/docs/latest/commands/xadd/>
  - 참고 부분: MAXLEN ~ 옵션 — §8.1 근거
