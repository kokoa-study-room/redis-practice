# 05. RESP3 Protocol Deep Dive

> **학습 목표**: RESP3 프로토콜의 신규 타입 (Map / Set / Push / Big Number / Double / Verbatim String / Boolean) 을 이해하고, HELLO 협상, push messaging 의 의미, RESP2 대비 어떤 명령들이 어떻게 더 구조적으로 응답하는지 안다.
> **사전 지식**: 08-clients/01-03
> **예상 소요**: 25분

---

## 1. 왜 RESP3 인가?

RESP2 의 한계:
- **모든 응답이 array / bulk string / integer / simple string / error 5가지** 만으로 표현
- 응답이 map (`{name: "Kim", age: 30}`) 이어도 RESP2 는 `["name", "Kim", "age", 30]` 식의 flat array → 클라이언트가 재조립
- Push 메시지 (Pub/Sub, invalidation) 를 일반 응답과 같은 connection 으로 다중화 못 함

RESP3 (Redis 6+) 가 추가:
- **Map** (`%`) — 키-값 사전
- **Set** (`~`) — 중복 없는 집합
- **Push** (`>`) — 비요청 메시지
- **Big Number** (`(`) — 임의 정밀도 정수
- **Double** (`,`) — 부동소수점
- **Boolean** (`#`) — true / false
- **Null** (`_`) — 명시적 null
- **Verbatim String** (`=`) — format hint 포함 (e.g. `txt:Hello`)
- **Streamed Strings** (`$?`) — chunked

> 출처: <https://github.com/redis/redis-specifications/blob/master/protocol/RESP3.md>

---

## 2. HELLO 명령 — 프로토콜 협상

```
HELLO 3                          # RESP3 사용 요청
HELLO 3 AUTH alice p1pp0         # + 인증
HELLO 3 AUTH alice p1pp0 SETNAME myapp-worker-01
```

응답 (Map):
```
1# "server" => "redis"
2# "version" => "8.6.2"
3# "proto" => 3
4# "id" => 42
5# "mode" => "standalone"
6# "role" => "master"
7# "modules" => (empty array)
```

→ 한 명령으로 protocol 협상 + 인증 + 클라이언트 이름 설정.

---

## 3. RESP2 vs RESP3 응답 비교

### 3.1 HGETALL

RESP2:
```
> HGETALL user:1
1) "name"
2) "Kim"
3) "age"
4) "30"
```
→ flat array. 클라이언트가 짝수 인덱스 = key, 홀수 = value 로 재조립.

RESP3:
```
> HGETALL user:1
1# "name" => "Kim"
2# "age" => "30"
```
→ Map 타입. 클라이언트가 그대로 dict / object 로.

### 3.2 CONFIG GET

RESP2:
```
> CONFIG GET maxmemory*
1) "maxmemory"
2) "0"
3) "maxmemory-policy"
4) "noeviction"
```

RESP3:
```
> CONFIG GET maxmemory*
1# "maxmemory" => "0"
2# "maxmemory-policy" => "noeviction"
```

### 3.3 ZRANGE WITHSCORES

RESP2:
```
1) "alice"
2) "1500"
3) "bob"
4) "2300"
```

RESP3:
```
1) 1) "alice"
   2) (double) 1500
2) 1) "bob"
   2) (double) 2300
```
→ score 가 진짜 Double 타입.

### 3.4 CLIENT INFO

RESP2 / RESP3 모두 string 한 줄. RESP3 도 큰 변화 없음 (단순 응답 명령).

### 3.5 XPENDING

RESP3 에서 Map / 중첩 구조로 더 자연스러움.

---

## 4. Push messages

### 4.1 Pub/Sub
RESP2 의 Pub/Sub 메시지:
```
1) "message"
2) "channel"
3) "data"
```
→ 일반 응답과 같은 모양 (array). 클라이언트가 첫 element 보고 push 인지 응답인지 구분.

RESP3:
```
> message
> channel
> data
```
→ `>` prefix 로 push 임을 명확히 마크. 같은 connection 에서 일반 명령 응답과 자유롭게 다중화.

### 4.2 Client-side caching invalidation
```
> invalidate
> 1) "user:1"
   2) "user:2"
```
→ Tracking invalidation 도 push 로 옴.

---

## 5. 클라이언트 라이브러리 사용

### 5.1 Python (redis-py)
```python
import redis

r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True, protocol=3)

# HGETALL 결과가 dict 로 직접 옴 (RESP2 도 그렇긴 함, 라이브러리가 변환)
hash_value = r.hgetall("user:1")     # {'name': 'Kim', 'age': '30'}

# CLIENT INFO 등의 응답이 더 풍부
info = r.client_info()
```

### 5.2 Node.js (node-redis 5+)
```javascript
import { createClient } from "redis";
const r = createClient({ url: "redis://...", RESP: 3 });
await r.connect();

const hash = await r.hGetAll("user:1");   // { name: 'Kim', age: '30' }
```

### 5.3 ioredis
ioredis 5.x 도 RESP3 지원 (`enableAutoPipelining` + protocol option). 정확한 옵션은 ioredis docs.

---

## 6. RESP3 가 가능하게 하는 기능

| 기능 | RESP3 필요? | 이유 |
|---|---|---|
| Client-side caching (single connection) | ✅ | invalidation push 다중화 |
| Multi-line server response | 권장 | Map/Set 자연 표현 |
| Big number (snowflake 등) | ✅ | RESP2 는 string으로 위장 |
| true/false 명확 | ✅ | RESP2 는 0/1 integer |
| 새 명령 (HOTKEYS, FCALL 등) 의 풍부 응답 | 권장 | Map/nested |

---

## 7. 호환성

- 클라이언트가 RESP3 보내면 서버가 RESP3로 응답.
- HELLO 안 보내면 RESP2 (default, 호환).
- 같은 connection 으로 RESP2 ↔ RESP3 전환 가능 (HELLO 2 / HELLO 3).
- Cluster / Sentinel 도 모두 호환.

---

## 8. 흔한 함정

| 함정 | 설명 |
|---|---|
| protocol=3 만 주면 모든 게 자동? | 라이브러리가 변환을 해주지만 일부 명령은 응답 형식 차이 그대로 노출. 라이브러리 docs 확인. |
| Pub/Sub 인데 RESP2 모드 + Pub/Sub 전용 connection | RESP3 면 한 connection 으로 가능. 코드 단순화 기회. |
| Big number 가 string 으로 옴 | RESP3 에서도 client 가 변환 안 하면 string. parse 필요. |
| HELLO 안 쓰고 protocol 옵션만 줬는데 안 됨 | 라이브러리에 따라 HELLO 자동 호출 / 수동 호출. |
| Push 메시지 핸들러 안 등록 | invalidation 무시됨. 라이브러리의 push handler 등록 필수. |

---

## 9. 직접 해보기

1. RESP2 / RESP3 모드로 같은 명령 (HGETALL, CONFIG GET, ZRANGE WITHSCORES) 호출 — 응답 구조 차이.
2. RESP3 단일 connection 으로 SUBSCRIBE + 일반 명령 동시 사용.
3. RESP3 + CLIENT TRACKING ON → invalidation push 수신.
4. `HELLO 2` 후 다시 `HELLO 3` 전환 — 같은 connection 에서 protocol 변경.

---

## 10. 참고 자료

- **[공식 명세] RESP3 Specification** — <https://github.com/redis/redis-specifications/blob/master/protocol/RESP3.md>
  - 참고 부분: 신규 타입 표 / 와이어 형식 — §1 근거

- **[공식 문서] HELLO command** — <https://redis.io/docs/latest/commands/hello/>
  - 참고 부분: 협상 / 응답 — §2 근거

- **[공식 문서] Redis serialization protocol** — <https://redis.io/docs/latest/develop/reference/protocol-spec/>
  - 참고 부분: RESP2 vs RESP3 대조 — §3 근거

- **[redis-py] Protocol option** — <https://redis.readthedocs.io/en/stable/connections.html>
  - 참고 부분: protocol=3 — §5.1 근거

- **[node-redis] RESP3 support** — <https://github.com/redis/node-redis>
  - 참고 부분: RESP: 3 옵션 — §5.2 근거
