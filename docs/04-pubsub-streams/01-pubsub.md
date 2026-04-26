# 01. Pub/Sub

> **학습 목표**: PUBLISH / SUBSCRIBE / PSUBSCRIBE 사용, Pub/Sub의 휘발성 한계, Sharded Pub/Sub (Cluster)을 이해한다.
> **예상 소요**: 20분

---

## 1. 개념

> **"채널에 메시지를 던지면, 그 채널을 듣고 있는 모든 클라이언트에게 즉시 broadcast."**

```
Publisher ──PUBLISH ch1 "hi"──▶ [Redis] ──▶ Subscriber A
                                       └─▶ Subscriber B
                                       └─▶ Subscriber C
```

**핵심**: 메시지가 보존되지 않는다. SUBSCRIBE 안 하고 있던 클라이언트는 못 받는다 (fire-and-forget).

용도:
- **실시간 알림** (채팅 입력, 알림 푸시)
- **WebSocket 게이트웨이의 백엔드**
- **컨피그 변경 broadcast**

---

## 2. 기본 사용법

### 터미널 A (구독자)
```
redis-cli SUBSCRIBE news
1) "subscribe"
2) "news"
3) (integer) 1                        # 현재 구독 개수
# 메시지 대기...
```

### 터미널 B (퍼블리셔)
```
redis-cli PUBLISH news "Hello"
(integer) 2                            # 받은 구독자 수
```

### 터미널 A에 즉시:
```
1) "message"
2) "news"
3) "Hello"
```

### 패턴 구독

```
PSUBSCRIBE news.*                      # news.sports, news.tech 등 다 받음
```

```
1) "pmessage"
2) "news.*"
3) "news.sports"
4) "Game tonight"
```

### 구독 해제

```
UNSUBSCRIBE news
PUNSUBSCRIBE news.*
```

### 정보

```
PUBSUB CHANNELS                        # 활성 채널 목록
PUBSUB CHANNELS "news.*"               # 패턴 매칭
PUBSUB NUMSUB news                     # 채널별 구독자 수
PUBSUB NUMPAT                          # 패턴 구독 개수
```

---

## 3. 클라이언트 코드

### Python — 별도 connection

```python
import redis, threading

r = redis.Redis(decode_responses=True)

def listener():
    pubsub = r.pubsub()
    pubsub.subscribe("news")
    for msg in pubsub.listen():
        if msg["type"] == "message":
            print("받음:", msg["data"])

threading.Thread(target=listener, daemon=True).start()

import time; time.sleep(0.5)
r.publish("news", "Hello")
time.sleep(0.5)
```

### Node.js (node-redis)

```javascript
import { createClient } from "redis";

const sub = createClient();
const pub = createClient();
await sub.connect(); await pub.connect();

await sub.subscribe("news", (msg) => {
  console.log("받음:", msg);
});

await pub.publish("news", "Hello");
```

> **subscribe / publish 는 별도 connection** 으로. 같은 connection에서 SUBSCRIBE 후엔 일반 명령 못 보냄.

---

## 4. Sharded Pub/Sub (Cluster, Redis 7+)

전통 Pub/Sub의 클러스터 한계: 메시지가 모든 노드에 broadcast → 트래픽 폭발.

해결: **Sharded Pub/Sub** — 채널을 슬롯에 매핑. 같은 슬롯 채널 메시지만 같은 노드에서 처리.

```
SSUBSCRIBE shard.ch1
SPUBLISH shard.ch1 "data"
SUNSUBSCRIBE shard.ch1
PUBSUB SHARDCHANNELS
```

> 출처: <https://redis.io/docs/latest/develop/interact/pubsub/#sharded-pubsub>

---

## 5. RESP3 push messaging

RESP3 프로토콜 (Redis 7+, `HELLO 3` / `protocol=3`)에서는 같은 connection으로 일반 명령 + push 메시지 동시 가능 (별도 connection 안 써도 됨).

---

## 6. 흔한 함정

| 함정 | 설명 |
|---|---|
| 메시지가 영속될 줄 안다 | Pub/Sub은 휘발. 영속이 필요하면 Stream. |
| 같은 connection으로 publish | SUBSCRIBE 중인 connection은 일반 명령 거부. |
| `PSUBSCRIBE` 의 부하 | 많은 패턴 등록 + 매 메시지 매칭 연산. 많이 쓰지 말 것. |
| Cluster에서 일반 PUBLISH 사용 | 모든 노드에 broadcast → 트래픽 폭발. SPUBLISH 사용. |
| 컨슈머 잠시 끊겼다 다시 붙으면 | 끊긴 동안 메시지 손실. 보장 필요하면 Stream. |

---

## 7. 직접 해보기

1. 터미널 두 개로 SUBSCRIBE / PUBLISH 양방향.
2. PSUBSCRIBE 'user.*' 후 PUBLISH user.login / user.logout.
3. `PUBSUB NUMSUB ch1 ch2` 로 구독자 수 확인.
4. (Cluster 챕터 후) Sharded Pub/Sub로 SSUBSCRIBE / SPUBLISH.

---

## 8. 참고 자료

- **[공식 문서] Pub/Sub**
  - URL: <https://redis.io/docs/latest/develop/interact/pubsub/>
  - 참고 부분: SUBSCRIBE/PUBLISH 의미 + Sharded Pub/Sub 섹션 — §1, §4 근거

- **[공식 문서] PUBLISH / SUBSCRIBE / PSUBSCRIBE / SPUBLISH**
  - URL: <https://redis.io/docs/latest/commands/publish/>, etc.
  - 참고 부분: 동작 정의 — §2, §4 근거
