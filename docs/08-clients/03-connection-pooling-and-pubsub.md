# 03. Connection Pooling & Pub/Sub 운영 패턴

> **학습 목표**: Pool 크기를 어떻게 정할지, Pub/Sub 컨슈머 connection을 분리해야 하는 이유, 죽은 connection 회복 패턴을 안다.
> **예상 소요**: 20분

---

## 1. 왜 Pool인가

매 요청마다 connection 생성:
- TCP handshake (RTT × 1)
- TLS 사용 시 추가 RTT
- Redis는 connection 별 buffer 메모리 할당

→ **재사용**: pool로 connection을 미리 만들어두고 빌려준다.

---

## 2. Pool 크기 정하기

### 너무 작음
- 동시 요청이 많을 때 대기 (queue)
- 효과적인 동시성 ↓

### 너무 큼
- Redis 측 `maxclients` (기본 10000) 도달 위험
- connection 별 메모리 (수 KB) 누적
- 컨텍스트 스위칭 비용

### 가이드

| 환경 | 권장 |
|---|---|
| 단일 워커 (CPU 1코어) | 5~10 |
| 일반 웹 앱 (워커 4-8) | 워커당 10~20 |
| 비동기 (asyncio/Node) | 동시성에 비례, 보통 50~200 |
| 서버리스 함수 | 함수 인스턴스당 1개 (cold start 비용 주의) |

**측정**: Redis `INFO clients` → `connected_clients` / `maxclients` 비교.

---

## 3. Pub/Sub은 왜 별도 connection인가

```
SUBSCRIBE ch1
# 이 connection은 이제 subscribed 상태.
# SET, GET 같은 명령 → (error) Can't execute ...
```

→ **subscribed connection은 일반 명령 거부**.

따라서:
- subscribe 전용 connection (혹은 RESP3 push로 같은 connection 사용 — 일부 라이브러리)
- publish는 **일반 connection / pool**

### Python 패턴

```python
import redis

r = redis.Redis()              # 일반 명령용
ps = r.pubsub()                # 내부적으로 별도 connection
ps.subscribe("news")

# r 은 publish 등에 계속 사용 가능
r.publish("news", "hello")
```

### Node.js (node-redis)

```javascript
const sub = r.duplicate();
await sub.connect();
await sub.subscribe("news", (m) => console.log(m));

// r 은 일반 명령 그대로
await r.publish("news", "hello");
```

---

## 4. 죽은 connection 회복

원인: 네트워크 흔들림 / Redis 재시작 / Sentinel failover.

### 라이브러리 자동 재연결

| 라이브러리 | 기본 |
|---|---|
| redis-py | `socket_timeout` + `retry` 옵션으로 재시도 |
| node-redis | 내장 reconnect (지수 백오프) |
| ioredis | `retryStrategy` 옵션 |

### Pub/Sub 컨슈머 재구독

라이브러리 대부분 자동으로 재구독. 단, 경계 케이스(이미 새 master로 failover된 시점):
- Sentinel 클라이언트는 자동으로 새 master 발견
- 일반 클라이언트는 raw IP에 매달려 있음 → Sentinel-aware 권장

---

## 5. Connection 누수

증상: `INFO clients` 의 connected_clients가 시간 따라 증가.

원인:
- pool에서 빌리고 안 돌려줌 (라이브러리 with 블록 안 씀)
- async에서 `await aclose()` 안 함
- Pub/Sub `duplicate()` 만 하고 `quit()` 안 함

진단:
```
CLIENT LIST                # 현재 연결 모두 + age / idle
CLIENT KILL ADDR 1.2.3.4:5678   # 강제 종료
```

---

## 6. 운영 권고

| 항목 | 권고 |
|---|---|
| Pool 크기 | 워커/동시성 기준으로 설정, 운영하면서 조정 |
| Pub/Sub | 별도 connection (or RESP3 push) |
| Sentinel/Cluster | 라이브러리의 전용 클라이언트 사용 |
| Health check | `r.ping()` 주기 호출 (load balancer health 등) |
| Timeout | socket_timeout 설정 (블록되면 다른 요청 영향) |
| Retry | exponential backoff + jitter, max attempts 제한 |

---

## 7. Cluster Connection Pool 특수성

cluster-aware 클라이언트는:
- **노드별 pool** 자동 관리
- 슬롯 → 노드 매핑 캐시
- MOVED 응답에 따라 캐시 갱신

따라서 클라이언트 수준의 pool 크기 옵션은 **노드당 max** 의 의미.

```python
RedisCluster(host="127.0.0.1", port=7001, max_connections=20)
# → 노드 6개면 최대 120 connection (이론치)
```

---

## 8. 흔한 함정

| 함정 | 설명 |
|---|---|
| Pool 1 + 동시 요청 100 | 직렬화. Pool 크기 늘리기. |
| 같은 connection으로 SUBSCRIBE + 일반 명령 | 거부. duplicate. |
| Lambda에서 매 호출마다 connect | cold start 비용. global scope에 connection 둠 (단, fork 주의). |
| 환경변수로 connection 수 무제한 | OOM 위험. 명시적 maximum. |
| Sentinel 안 쓰고 IP 직접 | failover 후 옛 IP에 붙음. |

---

## 9. 직접 해보기

1. Pool 크기 1로 두고 100 동시 SET → 시간 측정.
2. 같은 코드 Pool 20 → 시간 비교.
3. SUBSCRIBE 한 connection으로 SET 시도 → 에러 확인.
4. `CLIENT LIST` 로 현재 connection 수 / age 분석.
5. Sentinel failover 후에도 Sentinel-aware client는 정상 동작.

---

## 10. 참고 자료

- **[공식 문서] Connection management**
  - URL: <https://redis.io/docs/latest/develop/clients/>
  - 참고 부분: pool / pub-sub 분리 권고 — §3, §6 근거

- **[redis-py] Connection pools**
  - URL: <https://redis.readthedocs.io/en/stable/connections.html#connection-pools>
  - 참고 부분: max_connections — §2 근거

- **[node-redis] Pool / duplicate**
  - URL: <https://github.com/redis/node-redis>
  - 참고 부분: createClientPool, duplicate — §3 근거
