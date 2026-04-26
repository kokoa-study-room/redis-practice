# 02. Sentinel — 자동 failover

> **학습 목표**: Sentinel 3대로 master 고장 감지 + replica를 master로 승격하는 quorum 기반 HA를 직접 띄우고 failover를 시연한다.
> **예상 소요**: 30분

---

## 1. 개념

> **Sentinel 프로세스들이 master 의 헬스를 감시. master가 죽으면 quorum으로 합의해서 replica를 새 master로 승격.**

```
[Master] ←─── monitor ──── [Sentinel 1]
   │                       [Sentinel 2]
   │                       [Sentinel 3]
   │ (replicate)
   ▼
[Replica 1]
[Replica 2]
```

특징:
- Sentinel은 **Redis와 같은 바이너리** (`redis-server --sentinel`).
- 클라이언트는 **Sentinel에 master 주소를 물어본다** (master가 바뀌어도 발견 가능).
- 자동 failover, configuration provider, 알림.

---

## 2. 권장 토폴로지

| 노드 수 | quorum | 안정성 |
|---|---|---|
| 3 Sentinel | 2 | 1대 죽어도 OK |
| 5 Sentinel | 3 | 2대 죽어도 OK |

Sentinel 끼리도 통신해서 합의. 짝수면 split-brain 가능 → 홀수 권장.

---

## 3. 설정 예 — sentinel.conf

```
port 26379
dir /tmp
sentinel monitor mymaster 192.168.1.10 6379 2
sentinel down-after-milliseconds mymaster 5000
sentinel failover-timeout mymaster 60000
sentinel parallel-syncs mymaster 1
# sentinel auth-pass mymaster <password>
```

옵션:
- `mymaster`: 클러스터 식별 별칭
- `192.168.1.10 6379`: 초기 master 주소 (이후 자동 갱신)
- `2`: quorum (이 수의 Sentinel이 동의해야 failover)
- `down-after-milliseconds`: 응답 없으면 SDOWN(주관적 다운) 판단 시간
- `failover-timeout`: failover 중간 단계 타임아웃
- `parallel-syncs`: 새 master로 동시에 replicate할 replica 수

---

## 4. docker-compose.sentinel.yml 예시

(본 프로젝트 [`docker/docker-compose.sentinel.yml`](../../docker/docker-compose.sentinel.yml) 참고)

```yaml
services:
  redis-master:
    image: redis:8.6-alpine
    command: redis-server --port 6379
    ports: ["127.0.0.1:6379:6379"]

  redis-replica-1:
    image: redis:8.6-alpine
    command: redis-server --port 6380 --replicaof redis-master 6379
    depends_on: { redis-master: { condition: service_started } }

  redis-replica-2:
    image: redis:8.6-alpine
    command: redis-server --port 6381 --replicaof redis-master 6379
    depends_on: { redis-master: { condition: service_started } }

  sentinel-1:
    image: redis:8.6-alpine
    command: redis-server /etc/redis/sentinel.conf --sentinel
    volumes: [ "./redis/sentinel/sentinel-1.conf:/etc/redis/sentinel.conf" ]
    ports: ["127.0.0.1:26379:26379"]
    depends_on: { redis-master: { condition: service_started } }

  sentinel-2:
    image: redis:8.6-alpine
    command: redis-server /etc/redis/sentinel.conf --sentinel
    volumes: [ "./redis/sentinel/sentinel-2.conf:/etc/redis/sentinel.conf" ]
    ports: ["127.0.0.1:26380:26379"]

  sentinel-3:
    image: redis:8.6-alpine
    command: redis-server /etc/redis/sentinel.conf --sentinel
    volumes: [ "./redis/sentinel/sentinel-3.conf:/etc/redis/sentinel.conf" ]
    ports: ["127.0.0.1:26381:26379"]
```

---

## 5. failover 실습 흐름

```bash
# 1) 환경 기동
docker compose -f docker/docker-compose.sentinel.yml up -d

# 2) Sentinel에 마스터 정보 물어보기
docker exec sentinel-1 redis-cli -p 26379 SENTINEL MASTER mymaster
# → ip / port / num-other-sentinels / quorum / num-slaves 등

# 3) 현재 master 확인
docker exec sentinel-1 redis-cli -p 26379 SENTINEL GET-MASTER-ADDR-BY-NAME mymaster
# → 1) "redis-master"  2) "6379"

# 4) master 죽이기
docker compose -f docker/docker-compose.sentinel.yml stop redis-master

# 5) ~5초 후 — Sentinel이 SDOWN→ODOWN→failover 진행
docker exec sentinel-1 redis-cli -p 26379 SENTINEL GET-MASTER-ADDR-BY-NAME mymaster
# → 새로운 master 주소 (replica-1 또는 replica-2)

# 6) 새 master에서 SET 가능, 옛 master 다시 띄우면 replica로 합류
docker compose -f docker/docker-compose.sentinel.yml start redis-master
```

---

## 6. 클라이언트 — Sentinel 인식

### Python (redis-py)

```python
from redis.sentinel import Sentinel

sentinel = Sentinel([("127.0.0.1", 26379),
                     ("127.0.0.1", 26380),
                     ("127.0.0.1", 26381)],
                    socket_timeout=0.5)

# master 가져오기 (failover 후에도 자동 갱신)
master = sentinel.master_for("mymaster", socket_timeout=0.5, decode_responses=True)
master.set("k", 1)

# replica에서 read
slave = sentinel.slave_for("mymaster", socket_timeout=0.5, decode_responses=True)
print(slave.get("k"))
```

### Node.js (ioredis)

```javascript
import Redis from "ioredis";

const redis = new Redis({
  sentinels: [
    { host: "127.0.0.1", port: 26379 },
    { host: "127.0.0.1", port: 26380 },
    { host: "127.0.0.1", port: 26381 },
  ],
  name: "mymaster",
});
```

> ioredis는 Sentinel 지원이 잘 되어 있어 HA 구성에서 자주 선택됨.

---

## 7. 흔한 함정

| 함정 | 설명 |
|---|---|
| Sentinel 짝수 | split-brain 위험. 홀수 (3, 5). |
| `down-after-milliseconds` 너무 짧음 | 일시적 네트워크 흔들림에도 failover. 5초 이상 권장. |
| 클라이언트가 master 주소를 캐시 | failover 후 옛 master에 write → 거부됨. Sentinel-aware 클라이언트 사용. |
| Sentinel 스스로의 HA | Sentinel도 죽을 수 있음. 3+ 권장. |
| Sentinel과 Redis가 같은 호스트 | 호스트 전체가 죽으면 둘 다 사라짐. 다른 호스트에 분산. |

---

## 8. 직접 해보기

1. compose 띄우고 SENTINEL MASTER mymaster 출력 분석.
2. master 강제 종료 → 5초 후 GET-MASTER-ADDR-BY-NAME 으로 새 master 확인.
3. Python sentinel 클라이언트로 SET/GET — failover 후에도 자동 동작.
4. Sentinel 1대만 죽여보기 — 나머지 2대로 quorum 만족하므로 정상 동작.
5. Sentinel 2대 죽이면? quorum 못 채워서 failover 못 함.

---

## 9. 참고 자료

- **[공식 문서] Redis Sentinel**
  - URL: <https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/>
  - 참고 부분: SDOWN/ODOWN, quorum, parallel-syncs — §1, §3 근거

- **[공식 문서] sentinel.conf example**
  - URL: <https://github.com/redis/redis/blob/8.6/sentinel.conf>
  - 참고 부분: 옵션별 주석 — §3 근거

- **[redis-py docs] Sentinel**
  - URL: <https://redis.readthedocs.io/en/stable/connections.html#sentinel-client>
  - 참고 부분: master_for / slave_for — §6 Python 예제 근거

- **[ioredis] Sentinel**
  - URL: <https://github.com/redis/ioredis#sentinel>
  - 참고 부분: sentinels 옵션 — §6 Node 예제 근거
