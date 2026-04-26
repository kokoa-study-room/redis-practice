# 01. String

> **학습 목표**: String이 단순 문자열이 아니라 **바이트/숫자/비트맵의 통합 자료형**임을 이해하고, INCR가 왜 안전한지 설명할 수 있다.
> **사전 지식**: 00-getting-started 완료
> **예상 소요**: 25분

---

## 1. 개념 (Concept)

Redis의 String은 **최대 512MB의 바이트 시퀀스**다. 다음 모두 String이다.

- `"hello"` (텍스트)
- `42`, `3.14` (숫자 — 명령 호출 시 자동으로 숫자로 해석)
- 이미지 바이너리, JPEG 등 (바이너리 안전)
- 비트 배열 (Bitmap이 String 위에 동작)

> 출처: <https://redis.io/docs/latest/develop/data-types/strings/>
> 참고 부분: "Redis Strings are binary safe, this means that a Redis string can contain any kind of data" — 본 단락의 정의 근거

---

## 2. 기본 사용법 (redis-cli)

```
# SET / GET
127.0.0.1:6379> SET name "Redis"
OK
127.0.0.1:6379> GET name
"Redis"

# 옵션 (자주 쓰는 4가지)
SET k v EX 60                # 60초 후 만료
SET k v PX 1500              # 1500ms 후 만료
SET k v NX                   # 존재하지 않을 때만 (Not eXist)
SET k v XX                   # 존재할 때만 (eXist)

# 숫자로 다루기 — 자동 해석
127.0.0.1:6379> SET visits 100
OK
127.0.0.1:6379> INCR visits
(integer) 101
127.0.0.1:6379> INCRBY visits 10
(integer) 111
127.0.0.1:6379> DECR visits
(integer) 110
127.0.0.1:6379> INCRBYFLOAT visits 0.5
"110.5"

# 여러 키 한 번에
127.0.0.1:6379> MSET a 1 b 2 c 3
OK
127.0.0.1:6379> MGET a b c
1) "1"
2) "2"
3) "3"

# 문자열 길이
127.0.0.1:6379> STRLEN name
(integer) 5

# 부분 추출 / 추가
127.0.0.1:6379> GETRANGE name 0 2
"Red"
127.0.0.1:6379> APPEND name "-OSS"
(integer) 9
127.0.0.1:6379> GET name
"Redis-OSS"
```

### Redis 7+ 신규: GETEX, SETEX 대체

```
# GETEX: GET + 만료 갱신을 원자적으로
GETEX k EX 30           # 가져오면서 만료 30초로
GETEX k PERSIST         # 가져오면서 만료 제거
```

---

## 3. 클라이언트 코드 예제

### Python (redis-py 7.4)

```python
import redis

r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)

r.set("greeting", "안녕")
print(r.get("greeting"))                  # 안녕

# INCR로 카운터
r.set("visits", 0)
r.incr("visits")
r.incrby("visits", 10)
print(r.get("visits"))                    # "11" (str로 옴; decode_responses=True 때문)

# NX + EX = 분산 락 기본 패턴
acquired = r.set("lock:foo", "client-id-123", nx=True, ex=30)
if acquired:
    print("락 획득")
else:
    print("이미 누군가 잡고 있음")
```

### Node.js (node-redis 5.12)

```javascript
import { createClient } from "redis";

const r = createClient({ url: "redis://127.0.0.1:6379" });
await r.connect();

await r.set("greeting", "안녕");
console.log(await r.get("greeting")); // 안녕

await r.set("visits", "0");
await r.incr("visits");
await r.incrBy("visits", 10);
console.log(await r.get("visits")); // "11"

// NX + EX
const acquired = await r.set("lock:foo", "client-id-123", { NX: true, EX: 30 });
console.log(acquired ? "획득" : "이미 잠김");

await r.close();
```

---

## 4. 내부 동작 / 시간 복잡도

### 4.1 인코딩 (Encoding)

`OBJECT ENCODING` 으로 확인:

| 인코딩 | 조건 | 설명 |
|---|---|---|
| `int` | 값이 64-bit 정수로 표현 가능 | 포인터 자체에 정수 저장. 메모리 매우 효율적. |
| `embstr` | ≤44 byte 짧은 문자열 | redisObject + sds 가 한 번에 alloc (캐시 친화적). |
| `raw` | 45 byte 이상 | redisObject와 sds(SDS = Simple Dynamic String)가 별도 alloc. |

```
127.0.0.1:6379> SET a 12345
OK
127.0.0.1:6379> OBJECT ENCODING a
"int"

127.0.0.1:6379> SET b "hello world"
OK
127.0.0.1:6379> OBJECT ENCODING b
"embstr"

127.0.0.1:6379> SET c "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"  # 46자
OK
127.0.0.1:6379> OBJECT ENCODING c
"raw"
```

> SDS와 인코딩 전환 메커니즘은 [02-internals/02-sds.md](../02-internals/02-sds.md) 에서 자세히.
> 출처 (44byte 임계): <https://github.com/redis/redis/blob/8.6/src/object.c> `OBJ_ENCODING_EMBSTR_SIZE_LIMIT` 매크로 — embstr/raw 경계가 44임을 코드로 명시.

### 4.2 시간 복잡도 (Big-O)

| 명령 | 복잡도 | 비고 |
|---|---|---|
| `SET`, `GET`, `INCR`, `DECR` | **O(1)** | |
| `STRLEN`, `APPEND` | O(1) | APPEND는 amortized O(1) |
| `GETRANGE`, `SETRANGE` | O(N) | N = 반환할 바이트 수 |
| `MSET`, `MGET` | O(N) | N = 키 개수 |

> 출처: 각 명령 페이지의 "Time complexity" 섹션, e.g. <https://redis.io/docs/latest/commands/set/>

### 4.3 INCR가 왜 안전한가

단일 스레드 + 명령이 atomic이라:

```
client A: INCR counter
client B: INCR counter
```

같이 와도 **반드시 둘 중 하나가 먼저 실행**되고 다른 쪽이 그 결과를 보고 +1 한다.
RDBMS의 SELECT-then-UPDATE race condition이 없다.

---

## 5. 흔한 함정 (Pitfalls)

| 함정 | 설명 | 피하는 법 |
|---|---|---|
| INCR 대상이 숫자가 아님 | `SET k "abc"` 후 `INCR k` → `(error) ERR value is not an integer` | 명시적 초기화 또는 `INCR` 대상 키와 일반 String 키 분리 |
| 너무 큰 String (수백 MB) | 단일 키 → `DEL` 시 서버 멈춤 | `UNLINK`, 또는 자료를 chunk 키로 분할 |
| TTL 없는 캐시 | maxmemory 도달 시 eviction policy에 따라 다른 키가 사라질 수 있음 | 캐시 용도면 `SET ... EX <초>` 항상 부여 |
| 바이너리에 `decode_responses=True` | UTF-8 디코딩 에러 | 바이너리 키는 별도 클라이언트 (decode 안 함) |
| `INCRBYFLOAT` 의 누적 오차 | 부동소수점 합산 누적 | 정수 단위로 저장 후 표시할 때만 나누기 |

---

## 6. RedisInsight에서 확인하기

Browser → 검색 `name` → 우측 패널:
- Type: `string`
- Encoding: `embstr` (자동 표시)
- TTL / Memory 도 같이

여러 자료형 String을 만들고 Encoding이 어떻게 다른지 GUI에서 한눈에 확인.

---

## 7. 직접 해보기

1. `SET counter 0` → `INCR counter` 를 100번 (cli/Python/Node 어느 것이든)
2. `OBJECT ENCODING counter` → 인코딩이 무엇인지?
3. 1KB 짜리 임의 문자열(`"a"*1000`)을 SET → 인코딩은? STRLEN은?
4. `SET token "xyz" NX EX 5` → 5초 안에 다시 같은 명령 → 결과는?
5. `MSET k1 1 k2 2 k3 3` 후 `MGET k1 k2 k3 k4` → 없는 키는?

---

## 8. 참고 자료 (References)

- **[공식 문서] Redis Strings — redis.io**
  - URL: <https://redis.io/docs/latest/develop/data-types/strings/>
  - 참고 부분: "Redis Strings are binary safe" 단락 — §1 정의 근거

- **[공식 문서] SET command**
  - URL: <https://redis.io/docs/latest/commands/set/>
  - 참고 부분: 옵션 목록(EX/PX/NX/XX) + Time complexity — §2, §4.2 근거

- **[공식 문서] OBJECT ENCODING**
  - URL: <https://redis.io/docs/latest/commands/object-encoding/>
  - 참고 부분: String 인코딩 (`int`, `embstr`, `raw`) — §4.1 표 근거

- **[GitHub] redis/redis — src/object.c (8.6)**
  - URL: <https://github.com/redis/redis/blob/8.6/src/object.c>
  - 참고 부분: `OBJ_ENCODING_EMBSTR_SIZE_LIMIT` 매크로 — §4.1의 44byte 임계 근거
