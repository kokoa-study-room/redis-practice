# 03. Cluster — 16384 슬롯 sharding

> **학습 목표**: Redis Cluster의 16384 슬롯 / CRC16 / hashtag, 6노드(3 master + 3 replica) 클러스터 띄우기, 재샤딩 / failover 동작을 직접 본다.
> **예상 소요**: 40분

---

## 1. 개념

> **데이터를 16384개 슬롯에 분산. 슬롯을 여러 노드에 나눠 들고, 노드별로 자기 슬롯의 데이터만 책임.**

```
slot = CRC16(key) % 16384

slot 0~5460       → Master A (+ Replica A')
slot 5461~10922   → Master B (+ Replica B')
slot 10923~16383  → Master C (+ Replica C')
```

특징:
- **자동 failover** (Sentinel 없이 — 클러스터 자체에 failover 로직)
- **수평 확장** (노드 추가 → 슬롯 일부 이동)
- 메시지 broadcast 부담 줄이는 **gossip 프로토콜** (cluster bus, 별도 포트 +10000)

---

## 2. 슬롯과 hashtag

```
KEY = "user:1234"  → slot = CRC16("user:1234") % 16384
```

여러 키를 같은 슬롯에 두려면 **hashtag** 사용:

```
{user:1234}:profile     → slot = CRC16("user:1234") % 16384
{user:1234}:cart        → slot = CRC16("user:1234") % 16384
{user:1234}:orders      → 같은 슬롯
```

`{...}` 안의 첫 번째 부분만 hash 대상. 같은 hashtag 끼리는 같은 슬롯 → MULTI/EXEC, Lua, MGET, SUNIONSTORE 등 멀티키 명령 가능.

> 출처: <https://redis.io/docs/latest/operate/oss_and_stack/scaling/>
> 참고 부분: "hash tags" 섹션 — §2 근거

---

## 3. docker-compose.cluster.yml 구성

(본 프로젝트 [`docker/docker-compose.cluster.yml`](../../docker/docker-compose.cluster.yml) 참고)

```yaml
services:
  redis-node-1:
    image: redis:8.6-alpine
    command: >
      redis-server --port 7001 --cluster-enabled yes
                   --cluster-config-file nodes.conf
                   --cluster-node-timeout 5000
                   --appendonly yes
    ports: ["127.0.0.1:7001:7001", "127.0.0.1:17001:17001"]   # +10000 = bus
  # node-2 ~ node-6 동일 패턴 (포트 7002~7006, 17002~17006)
```

기동 후 클러스터 생성:

```bash
docker exec redis-node-1 redis-cli --cluster create \
  redis-node-1:7001 redis-node-2:7002 redis-node-3:7003 \
  redis-node-4:7004 redis-node-5:7005 redis-node-6:7006 \
  --cluster-replicas 1 --cluster-yes
```

→ master 3 (1,2,3) + replica 3 (4,5,6) 자동 배치 + 슬롯 분배.

---

## 4. 클러스터 명령

```
# 클라이언트 연결 (-c = cluster mode, MOVED redirect 자동 처리)
redis-cli -c -p 7001

127.0.0.1:7001> SET foo bar
-> Redirected to slot [12182] located at 127.0.0.1:7003
OK

127.0.0.1:7003> CLUSTER NODES                # 모든 노드 + 슬롯 정보
127.0.0.1:7003> CLUSTER INFO                 # 클러스터 상태 요약
127.0.0.1:7003> CLUSTER SLOTS                # 슬롯 → 노드 매핑
127.0.0.1:7003> CLUSTER SHARDS               # (Redis 7+) shard 단위 정보
127.0.0.1:7003> CLUSTER KEYSLOT foo          # 12182
127.0.0.1:7003> CLUSTER COUNTKEYSINSLOT 12182
```

### 재샤딩 (resharding)

```bash
docker exec redis-node-1 redis-cli --cluster reshard 127.0.0.1:7001
# 대화형: 몇 슬롯, 어디서 어디로?
```

### 노드 추가 / 제거

```bash
# 새 master 추가
docker exec redis-node-1 redis-cli --cluster add-node redis-node-7:7007 redis-node-1:7001

# 새 replica 추가
docker exec redis-node-1 redis-cli --cluster add-node redis-node-8:7008 redis-node-1:7001 \
  --cluster-slave --cluster-master-id <master-id>

# 노드 제거
docker exec redis-node-1 redis-cli --cluster del-node redis-node-1:7001 <node-id>
```

### 자동 균형
```bash
docker exec redis-node-1 redis-cli --cluster rebalance redis-node-1:7001
```

---

## 5. failover

master 죽으면 클러스터가 자동으로 replica를 master로 승격.

```bash
# master 1 죽이기
docker compose -f docker/docker-compose.cluster.yml stop redis-node-1

# ~5초 후 (cluster-node-timeout)
docker exec redis-node-2 redis-cli -p 7002 CLUSTER NODES
# replica였던 redis-node-4 가 master로 승격
```

수동 failover:
```
CLUSTER FAILOVER          # replica에서 실행 → 자기가 master 됨
```

---

## 6. 클라이언트 — Cluster 인식

### Python (redis-py)

```python
from redis.cluster import RedisCluster

rc = RedisCluster(host="127.0.0.1", port=7001, decode_responses=True)
rc.set("foo", "bar")           # 자동 슬롯 라우팅
print(rc.get("foo"))

# 멀티 키
rc.mset({"{u:1}:a": 1, "{u:1}:b": 2})   # 같은 hashtag → 한 노드에 라우팅
```

### Node.js (ioredis Cluster)

```javascript
import Redis from "ioredis";
const cluster = new Redis.Cluster([
  { host: "127.0.0.1", port: 7001 },
  { host: "127.0.0.1", port: 7002 },
  { host: "127.0.0.1", port: 7003 },
]);

await cluster.set("foo", "bar");
```

---

## 7. 멀티 키 명령의 한계

```
MGET k1 k2 k3       # 모두 같은 슬롯이어야 함, 아니면 CROSSSLOT 에러
MSET k1 1 k2 2 k3 3 # 동일
SUNIONSTORE / ZADD ... 모두 마찬가지
MULTI/EXEC          # 모든 키 같은 슬롯
EVAL/FCALL          # KEYS 모두 같은 슬롯
```

해결: **hashtag** `{user:1}` 로 묶음.

---

## 8. Cluster mode 의 함정

| 함정 | 설명 |
|---|---|
| 비-Cluster 클라이언트 사용 | MOVED/ASK 리다이렉트 처리 못 함. `-c` 또는 cluster-aware client. |
| 멀티 키 명령에 여러 슬롯 키 | CROSSSLOT 에러. hashtag로 묶기. |
| Pub/Sub 부하 폭발 | 일반 PUBLISH는 모든 노드에 broadcast. **SPUBLISH** (Sharded Pub/Sub) 사용. |
| `KEYS *` | 한 노드만 보여줌. 모든 노드 순회 필요하면 클라이언트가 노드별 SCAN. |
| replica를 read 부하 분산에 | 클러스터 기본은 master에서만 read. `READONLY` 명령 + cluster-aware 클라이언트로 가능 (eventual consistency 주의). |
| 노드 timeout 너무 짧음 | 일시 네트워크에 false failover. 5000ms 이상 권장. |

---

## 9. RedisInsight Cluster 연결

Add Database → Connect to: `127.0.0.1:7001` (or any).
RedisInsight는 자동으로 다른 노드 발견 + 슬롯 분포 시각화.

---

## 10. 직접 해보기

1. compose로 6노드 클러스터 띄우고 `--cluster create` 로 초기화.
2. `CLUSTER SLOTS` / `CLUSTER NODES` 출력 분석.
3. `redis-cli -c -p 7001 SET foo bar` → 어떤 노드로 redirect 되는지.
4. master 1 stop → 자동 failover 확인.
5. `--cluster reshard` 로 1000 슬롯 이동 → keyspace 분포 변화.
6. hashtag로 `{u:1}:profile`, `{u:1}:cart` SET → 같은 노드인지 (`CLUSTER KEYSLOT`).

---

## 11. 참고 자료

- **[공식 문서] Cluster Tutorial**
  - URL: <https://redis.io/docs/latest/operate/oss_and_stack/scaling/>
  - 참고 부분: 슬롯 16384, hashtag, cluster bus — §1, §2 근거

- **[공식 문서] Cluster Spec**
  - URL: <https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/>
  - 참고 부분: gossip / failover / MOVED 리다이렉트 — §3, §5 근거

- **[공식 문서] CLUSTER 명령군**
  - URL: <https://redis.io/docs/latest/commands/cluster-nodes/>, etc.
  - 참고 부분: NODES / SLOTS / SHARDS — §4 근거
