# 03. Hash (필드 단위 TTL 포함)

> **학습 목표**: Hash가 객체 1개를 메모리 효율적으로 저장하는 데 적합한 이유, listpack ↔ hashtable 전환, **Redis 7.4+ field-level TTL** (HEXPIRE 계열)을 사용할 수 있다.
> **예상 소요**: 30분

---

## 1. 개념

Hash는 **key 안의 또 하나의 작은 맵 (field → value)**.
JSON 객체 한 개를 저장한다고 보면 된다.

```
key = "user:1001"
  ├ field "name"   → "Kim"
  ├ field "email"  → "k@example.com"
  └ field "level"  → "10"
```

용도:
- 사용자 프로필 / 상품 정보 / 세션 상태
- "필드만 부분 수정" 이 잦을 때 (전체 JSON을 SET 하는 것보다 효율)
- **필드별 만료** 가 필요할 때 (Redis 7.4+ HEXPIRE)

> 출처: <https://redis.io/docs/latest/develop/data-types/hashes/>

---

## 2. 기본 사용법

```
# field 설정
HSET user:1001 name "Kim" email "k@example.com" level 10
# (integer) 3   ← 새로 추가된 필드 수

# 조회
HGET user:1001 name              # "Kim"
HMGET user:1001 name email       # 1) "Kim" 2) "k@example.com"
HGETALL user:1001                # 전체 (필드 많으면 부담; 04-내부동작 참고)
HKEYS user:1001                  # 필드 이름들
HVALS user:1001                  # 값들
HLEN user:1001                   # 필드 개수
HEXISTS user:1001 email          # 1 / 0

# 부분 수정
HINCRBY user:1001 level 5        # 숫자 필드 증가 (15)
HINCRBYFLOAT user:1001 score 0.5
HSETNX user:1001 nickname "k"    # 없을 때만

# 삭제
HDEL user:1001 nickname email
```

### Redis 7.4+ : 필드 단위 TTL (8.x 에서도 동일)

```
# 단일 field 만료 (초)
HEXPIRE user:1001 30 FIELDS 1 email
# → 1: 적용됨, 0: field 없음, 2: 만료 시간이 과거라 즉시 삭제됨

HPEXPIRE user:1001 5000 FIELDS 1 token   # 밀리초

# 여러 field 한 번에
HEXPIRE user:1001 60 FIELDS 2 name email

# TTL 조회
HTTL user:1001 FIELDS 1 email            # [29] 등 초 단위
HPTTL user:1001 FIELDS 1 email           # 밀리초

# 만료 제거
HPERSIST user:1001 FIELDS 1 email

# 절대 시각
HEXPIREAT user:1001 1735689600 FIELDS 1 token

# Redis 8.0+ : 한 번에 만료까지 SET
HSETEX user:1001 60 FIELDS 1 token "abc123"
HGETEX user:1001 EX 30 FIELDS 1 email    # GET + 만료 갱신
```

> 출처: <https://redis.io/docs/latest/commands/hexpire/>
> 참고 부분: "Available since: 7.4.0" + 반환 코드 표 — 본 단락의 7.4 버전과 0/1/2 반환 의미 근거

---

## 3. 클라이언트 코드 예제

### Python — 사용자 프로필 + 토큰 만료

```python
import redis
r = redis.Redis(decode_responses=True)

# 객체 저장
r.hset("user:1001", mapping={
    "name": "Kim",
    "email": "k@example.com",
    "level": 10,
})

# 부분 갱신
r.hincrby("user:1001", "level", 5)

# 토큰 필드는 30초 후 자동 삭제
r.hset("user:1001", "session_token", "xyz789")
r.hexpire("user:1001", 30, "session_token")

print(r.hgetall("user:1001"))
# {'name': 'Kim', 'email': '...', 'level': '15', 'session_token': 'xyz789'}

# 30초 뒤 → session_token만 사라지고 다른 필드는 유지
```

### Node.js (node-redis 5.12)

```javascript
import { createClient } from "redis";
const r = createClient(); await r.connect();

await r.hSet("user:1001", { name: "Kim", email: "k@example.com", level: "10" });
await r.hIncrBy("user:1001", "level", 5);

await r.hSet("user:1001", "session_token", "xyz789");
// node-redis 5.11+ 부터 hExpire 명령 지원
await r.hExpire("user:1001", 30, "session_token");

console.log(await r.hGetAll("user:1001"));
```

> 출처 (node-redis HEXPIRE): <https://github.com/redis/node-redis/releases/tag/redis%405.10.0> 의 hash field expiration 기능 — node-redis 5.10+에서 명시적 지원

---

## 4. 내부 동작 / 시간 복잡도

### 4.1 인코딩

| 인코딩 | 조건 | 비고 |
|---|---|---|
| `listpack` | 필드 수 ≤ `hash-max-listpack-entries` (기본 128) AND 모든 값 길이 ≤ `hash-max-listpack-value` (기본 64) | 메모리 효율 최강 |
| `hashtable` | 위 조건 초과 | O(1) 조회 |

```
HSET tiny f1 v1 f2 v2
OBJECT ENCODING tiny             # "listpack"

# 큰 값 1개 추가
HSET tiny big "$(python -c 'print("a"*100)')"
OBJECT ENCODING tiny             # "hashtable"  ← 한 번 전환되면 도로 안 돌아감
```

### 4.2 Big-O

| 명령 | 복잡도 |
|---|---|
| `HSET`, `HGET`, `HDEL`, `HEXISTS`, `HLEN` | O(1) per field |
| `HMGET`, `HMSET` | O(N) (필드 수) |
| `HGETALL`, `HKEYS`, `HVALS` | O(N) |
| `HSCAN` | O(1) per call (cursor 기반) |
| `HEXPIRE`, `HTTL` | O(N) (지정한 필드 수) |

---

## 5. 흔한 함정

| 함정 | 설명 |
|---|---|
| **`HGETALL` 남발** | 필드가 수만 개면 한 번에 다 가져옴 → 큰 응답. `HSCAN` 이나 필요한 필드만 `HMGET`. |
| **Hash를 List처럼** | 필드를 인덱스로 (`HSET k 0 ... 1 ...`) → ListType의 인덱스 복잡도 모방 어려움. List/SortedSet 사용. |
| **value를 항상 string으로** | 숫자 증가는 `HINCRBY` 가 안전. JSON 직렬화 후 SET 하지 말고 필드 분리. |
| **HEXPIRE 미지원 클라이언트** | 7.4 이전 클라이언트 라이브러리는 명령을 모름. redis-py 6.0+ / node-redis 5.10+ 필요. |
| **listpack → hashtable 후 메모리 안 줄어듦** | 한 번 전환되면 안 돌아옴. 필드를 다 지워도 hashtable 메타 메모리 잔존. |

---

## 6. RedisInsight에서

Browser → Hash 키 → field-value 표.
field 클릭 → TTL 표시 (Redis 7.4+ 의 필드 TTL이 컬럼으로 보임).

---

## 7. Hash vs JSON 문자열 비교

| 시나리오 | Hash 권장 | JSON String 권장 |
|---|---|---|
| 부분 필드 자주 수정 | ✅ | ❌ (전체 재작성) |
| 한 필드만 만료 | ✅ (HEXPIRE) | ❌ |
| 클라이언트가 항상 전체 객체를 한 번에 다룸 | ❌ (불필요) | ✅ (직렬화 1회) |
| RediSearch 등 인덱싱 필요 | ✅ (필드 단위 인덱스) | ✅ (RedisJSON + RediSearch) |

---

## 8. 직접 해보기

1. 작은 Hash 만들고 `OBJECT ENCODING` → `listpack` 확인.
2. 값이 100자 이상인 필드 추가 → 인코딩 변화 관찰.
3. 필드 1개에 `HEXPIRE 5` → 6초 후 `HGETALL` 결과에서 그 필드만 사라지는지.
4. `HSCAN user:1001 0 COUNT 10` 으로 cursor 순회 시도.
5. `HRANDFIELD k 3 WITHVALUES` 무작위 필드 3개 가져오기.

---

## 9. 참고 자료

- **[공식 문서] Redis Hashes**
  - URL: <https://redis.io/docs/latest/develop/data-types/hashes/>
  - 참고 부분: "Field expiration" 섹션 — §1, §2 근거

- **[공식 문서] HEXPIRE / HPEXPIRE / HTTL / HPERSIST**
  - URL: <https://redis.io/docs/latest/commands/hexpire/>
  - 참고 부분: "Available since: 7.4.0" + 반환 코드 0/1/2 의미 — §2 근거

- **[공식 문서] HSETEX / HGETEX**
  - URL: <https://redis.io/docs/latest/commands/hsetex/>
  - 참고 부분: "Available since: 8.0.0" — §2의 8.0+ 명령 근거

- **[GitHub] redis/redis — redis.conf (8.6)** `hash-max-listpack-*` 기본값
  - URL: <https://github.com/redis/redis/blob/8.6/redis.conf>
  - 참고 부분: 128 entries / 64 byte 임계값 주석 — §4.1 근거

- **[GitHub] redis/node-redis releases**
  - URL: <https://github.com/redis/node-redis/releases/tag/redis%405.11.0>
  - 참고 부분: "Redis 8.6 Support" 섹션 — Node 클라이언트 명령 가용성 근거
