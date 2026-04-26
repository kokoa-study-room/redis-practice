# 04. Set

> **학습 목표**: Set의 중복 제거 / 집합 연산 (합/교/차) 활용, intset / listpack / hashtable 인코딩 전환을 설명할 수 있다.
> **예상 소요**: 20분

---

## 1. 개념

**중복 없는 멤버 모음**. 순서 없음. 멤버는 String.

용도:
- 태그 (`SADD post:1:tags python redis docker`)
- 친구/팔로워 목록 (집합 연산이 자연스러움)
- 일회성 작업 dedup (`SADD seen:user:1 ev-001` → 이미 있으면 0)
- 권한 / 그룹 멤버십

---

## 2. 기본 사용법

```
SADD tags python redis docker      # (integer) 3
SADD tags python                   # (integer) 0  (중복은 무시)
SCARD tags                         # 3 (개수)
SMEMBERS tags                      # 전체 (작을 때만)
SISMEMBER tags python              # 1
SMISMEMBER tags python java        # 1) 1  2) 0   (Redis 6.2+)
SRANDMEMBER tags 2                 # 무작위 2개
SPOP tags 1                        # 무작위 1개 + 삭제
SREM tags docker                   # 삭제

# 집합 연산
SADD a 1 2 3 4
SADD b 3 4 5 6

SUNION a b                         # 합집합 → {1,2,3,4,5,6}
SINTER a b                         # 교집합 → {3,4}
SDIFF a b                          # 차집합 (a-b) → {1,2}

SUNIONSTORE result a b             # 결과를 다른 Set에 저장
SINTERSTORE result a b
SDIFFSTORE result a b

# 카운트만 (결과 미저장; Redis 7+)
SINTERCARD 2 a b                   # 교집합 크기만
SINTERCARD 2 a b LIMIT 100         # 100 이상이면 100 반환 (조기 중단)

# 안전한 순회
SSCAN tags 0 MATCH "py*" COUNT 100
```

---

## 3. 클라이언트 코드 예제

### Python — 친구 추천 (공통 친구 기반)

```python
import redis
r = redis.Redis(decode_responses=True)

r.sadd("friends:alice", "bob", "carol", "dave")
r.sadd("friends:eve",   "bob", "dave", "frank")

# 공통 친구 개수
common_count = r.sintercard(2, "friends:alice", "friends:eve")
common = r.sinter("friends:alice", "friends:eve")
print(f"공통 친구 {common_count}명: {common}")
# 공통 친구 2명: {'bob', 'dave'}

# alice가 모르는, eve의 친구 (추천 후보)
candidates = r.sdiff("friends:eve", "friends:alice")
print("추천 후보:", candidates)  # {'frank'}
```

### Node.js

```javascript
import { createClient } from "redis";
const r = createClient(); await r.connect();

await r.sAdd("friends:alice", ["bob", "carol", "dave"]);
await r.sAdd("friends:eve",   ["bob", "dave", "frank"]);

console.log(await r.sInter(["friends:alice", "friends:eve"]));  // ['bob', 'dave']
console.log(await r.sDiff(["friends:eve", "friends:alice"]));    // ['frank']
```

---

## 4. 내부 동작

### 4.1 인코딩 (Redis 7.2+ 부터 listpack 도입)

| 인코딩 | 조건 |
|---|---|
| `intset` | 모든 멤버가 64-bit 정수 AND 개수 ≤ `set-max-intset-entries` (기본 512) |
| `listpack` | 모든 멤버가 짧은 문자열 AND 개수 ≤ `set-max-listpack-entries` (기본 128) AND 각 값 ≤ `set-max-listpack-value` (기본 64) |
| `hashtable` | 위 두 조건 다 깨질 때 |

```
SADD nums 1 2 3 4 5
OBJECT ENCODING nums       # "intset"

SADD tags python redis
OBJECT ENCODING tags       # "listpack"

SADD nums "abc"            # 정수 아닌 값 추가
OBJECT ENCODING nums       # "listpack" 또는 "hashtable" (개수 따라)
```

> 출처: <https://redis.io/docs/latest/commands/object-encoding/>
> 참고 부분: Set 가능 인코딩 목록 — §4.1 근거

### 4.2 Big-O

| 명령 | 복잡도 |
|---|---|
| `SADD`, `SREM`, `SISMEMBER`, `SCARD` | O(1) per element |
| `SMEMBERS` | O(N) |
| `SINTER`, `SUNION`, `SDIFF` | O(N*M)~O(전체합) — 작은 셋 우선 |
| `SINTERCARD ... LIMIT n` | 평균 O(min(N,n)) — 조기 중단으로 큰 절약 |

---

## 5. 흔한 함정

| 함정 | 설명 |
|---|---|
| **큰 Set의 SMEMBERS** | O(N), 응답 크기도 큼. `SSCAN` 사용. |
| **`SINTER` 큰 두 Set** | 교집합이 작아도 두 Set 다 봐야 함. 작은 Set 먼저 두는 클라이언트 정렬 후 호출. |
| **dedup만 필요한데 모든 멤버 보존** | 메모리. HyperLogLog (08-hyperloglog) 으로 카운트만 추정 가능. |
| **순서가 필요한데 Set** | Set은 순서 없음. Sorted Set으로 가야 함. |
| **intset → listpack 전환 후 메모리 증가** | 정수 외 값 1개 추가로 전환되면 메모리 살짝 증가. 의도적이면 무관. |

---

## 6. RedisInsight

Browser → Set 키 → 멤버 목록 표시 + 추가/삭제 UI.
Workbench → `SINTER` 결과를 표로 보여줌.

---

## 7. 직접 해보기

1. 정수만 SADD → intset 확인. 한 멤버를 문자열로 → 인코딩 변화.
2. 1000개 멤버 SADD → hashtable 전환 시점 확인.
3. 두 Set으로 교집합 SINTER vs SINTERCARD vs SINTERCARD LIMIT 의 응답 크기 비교.
4. `SDIFFSTORE result a b` 후 result에 TTL 부여 (`EXPIRE result 60`).

---

## 8. 참고 자료

- **[공식 문서] Redis Sets**
  - URL: <https://redis.io/docs/latest/develop/data-types/sets/>
  - 참고 부분: "Sets are useful in a number of cases" 단락 — §1 사용처 근거

- **[공식 문서] SINTERCARD**
  - URL: <https://redis.io/docs/latest/commands/sintercard/>
  - 참고 부분: "Available since: 7.0.0" + LIMIT 옵션 — §2 근거

- **[공식 문서] OBJECT ENCODING (Set 부분)**
  - URL: <https://redis.io/docs/latest/commands/object-encoding/>
  - 참고 부분: "Sets can be encoded as: hashtable, intset, listpack (Redis >= 7.2)" — §4.1 근거
