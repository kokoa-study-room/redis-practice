# 05. Sorted Set (ZSET)

> **학습 목표**: ZSET이 score 기반 정렬 + 멤버 유일성을 동시에 제공한다는 점, listpack ↔ skiplist+hashtable 전환, 리더보드/시계열 인덱스 구현법을 익힌다.
> **예상 소요**: 35분 (Redis의 가장 강력한 자료형 중 하나)

---

## 1. 개념

> **"중복 없는 멤버 + 각 멤버의 score(double) → score로 자동 정렬된 Set"**

```
key = "leaderboard"
  alice  → 1500
  bob    → 2300
  carol  →  980
  dave   → 1875
  eve    → 2750
```

내부적으로:
- **Hash table**: 멤버 → score 빠른 조회 (O(1))
- **Skip list**: score 순 정렬 (O(log N) 삽입/삭제/range)

용도:
- **리더보드** (게임 점수, 인기 글)
- **시간순 인덱스** (score=timestamp → 최근 N개)
- **우선순위 큐** (score=priority)
- **rate limit sliding window**
- **trending / 가중치 기반 추천**

> 출처: <https://redis.io/docs/latest/develop/data-types/sorted-sets/>

---

## 2. 기본 사용법

```
# 추가 (score member)
ZADD lb 1500 alice 2300 bob 980 carol 1875 dave 2750 eve

# 옵션
ZADD lb NX 100 alice           # NX: 없을 때만 추가, 이미 있으면 무시
ZADD lb XX 5000 alice          # XX: 있을 때만 업데이트
ZADD lb GT 1000 carol          # GT: 새 score가 기존보다 클 때만
ZADD lb LT 100 alice           # LT: 작을 때만
ZADD lb INCR 50 alice          # INCR: ZINCRBY 와 동일

# 점수 가져오기
ZSCORE lb alice                # "1500" (string으로 옴)
ZMSCORE lb alice bob carol     # 한 번에 여러 명

# 순위 (rank: 0부터, 낮은 score가 0)
ZRANK lb alice                 # 1 (carol 980 → alice 1500이 두 번째)
ZRANK lb alice WITHSCORE       # (Redis 7.2+) 점수도 같이
ZREVRANK lb alice              # 역순 순위 (높은 점수 = 0)

# 카운트
ZCARD lb                       # 5
ZCOUNT lb 1000 2000            # score 1000~2000 인원

# 정렬된 조회 (가장 자주 쓰는 명령)
ZRANGE lb 0 -1 WITHSCORES                # 점수 오름차순 전체
ZRANGE lb 0 9 REV WITHSCORES             # 내림차순 상위 10
ZRANGE lb 1000 2500 BYSCORE WITHSCORES   # score 범위
ZRANGE lb (1000 +inf BYSCORE             # 1000 초과 ~ 무한대
ZRANGE lb 0 9 BYSCORE LIMIT 10 5         # offset+count

# 사전순 (score가 같을 때만 의미)
ZRANGE lb [a [c BYLEX                    # member가 a~c 사이 (사전순)

# 증감
ZINCRBY lb 100 alice           # alice score +100 → 1600

# 제거
ZREM lb dave
ZREMRANGEBYRANK lb 0 4         # 하위 5개 제거 (TOP-N 유지 패턴)
ZREMRANGEBYSCORE lb -inf 1000  # score 1000 이하 모두 제거

# 결합 (집합 연산)
ZADD a 1 x 2 y
ZADD b 3 y 4 z
ZUNIONSTORE u 2 a b                       # 합 (같은 멤버는 score 합)
ZINTERSTORE i 2 a b WEIGHTS 1 2           # 가중치 부여 가능
ZDIFFSTORE d 2 a b
ZRANGESTORE dest src 0 -1                 # 결과 다른 키에 저장 (Redis 6.2+)

# 안전 순회
ZSCAN lb 0 COUNT 100
```

### 블로킹 pop (큐로 사용)

```
BZPOPMIN lb 5     # 5초 대기, 최저 score 멤버 pop
BZPOPMAX lb 0     # 무제한 대기, 최고 score 멤버 pop
```

---

## 3. 클라이언트 코드 예제

### Python — 게임 리더보드

```python
import redis, time
r = redis.Redis(decode_responses=True)

# 점수 갱신
def submit_score(player, score):
    r.zadd("leaderboard", {player: score})

submit_score("alice", 1500)
submit_score("bob",   2300)
submit_score("eve",   2750)

# TOP 3 (내림차순)
top3 = r.zrange("leaderboard", 0, 2, desc=True, withscores=True)
for rank, (player, score) in enumerate(top3, start=1):
    print(f"{rank}. {player}: {int(score)}")
# 1. eve: 2750
# 2. bob: 2300
# 3. alice: 1500

# alice 순위
my_rank = r.zrevrank("leaderboard", "alice")
print(f"alice 등수: {my_rank + 1}위")

# alice 주변 ±2명
alice_rank = r.zrevrank("leaderboard", "alice")
neighbors = r.zrange("leaderboard",
                     max(0, alice_rank - 2),
                     alice_rank + 2,
                     desc=True,
                     withscores=True)
```

### Python — 시간순 이벤트 인덱스 (score = unix timestamp)

```python
# 이벤트 적재
r.zadd("events", {f"evt-{i}": time.time() + i for i in range(10)})

# 최근 5분 이벤트만
now = time.time()
recent = r.zrangebyscore("events", now - 300, now)
```

### Node.js

```javascript
import { createClient } from "redis";
const r = createClient(); await r.connect();

await r.zAdd("lb", [
  { score: 1500, value: "alice" },
  { score: 2300, value: "bob" },
  { score: 2750, value: "eve" },
]);

// TOP 3 내림차순 + scores
const top = await r.zRangeWithScores("lb", 0, 2, { REV: true });
console.log(top); // [{value: 'eve', score: 2750}, ...]
```

---

## 4. 내부 동작

### 4.1 인코딩

| 인코딩 | 조건 |
|---|---|
| `listpack` | 멤버 수 ≤ `zset-max-listpack-entries` (기본 128) AND 각 멤버 길이 ≤ `zset-max-listpack-value` (기본 64) |
| `skiplist` | 위 조건 초과 — 사실은 **skiplist + hashtable 두 자료구조 병행** |

```
ZADD small 1 a 2 b
OBJECT ENCODING small        # "listpack"

# 130개 추가
for i in $(seq 1 130); do redis-cli ZADD big $i "m$i" > /dev/null; done
redis-cli OBJECT ENCODING big   # "skiplist"
```

### 4.2 왜 skiplist + hashtable 둘 다?

- **score 정렬 / range query** : skiplist 가 최적 (O(log N))
- **member로 score 즉시 조회** (`ZSCORE`) : hashtable이 O(1)

둘을 같이 유지해서 두 종류의 쿼리 모두 빠르게.
출처: <https://github.com/redis/redis/blob/8.6/src/t_zset.c> `zset` 구조체 — `dict + zskiplist` 두 필드를 함께 관리하는 코드 명시.

### 4.3 Big-O

| 명령 | 복잡도 |
|---|---|
| `ZADD`, `ZREM`, `ZSCORE`, `ZRANK` | **O(log N)** |
| `ZINCRBY` | O(log N) |
| `ZRANGE start stop` | O(log N + M)  M=반환 개수 |
| `ZRANGEBYSCORE`, `ZRANGEBYLEX` | O(log N + M) |
| `ZREMRANGEBYSCORE/RANK` | O(log N + M) |
| `ZSCAN` | O(1) per call |

> 출처: <https://redis.io/docs/latest/commands/zadd/> Time complexity 섹션

---

## 5. 흔한 함정

| 함정 | 설명 |
|---|---|
| **`ZRANGE 0 -1` 전체 조회** | 큰 ZSET이면 응답 폭발. 페이지네이션(`LIMIT`) 또는 점진적 ZSCAN. |
| **score를 정수처럼 다룸** | 내부는 `double`. 매우 큰 정수는 정밀도 손실 (>= 2^53). 큰 ID는 ZSET score로 부적합. |
| **동률(tie)에서 순서 기대** | 같은 score면 멤버 사전순. 이를 모르고 "최근 추가" 순으로 기대하면 버그. |
| **TOP-N 유지 안 함** | 무한 ZADD → 메모리. 주기적으로 `ZREMRANGEBYRANK lb 0 -101` (= 상위 100만 남김). |
| **ZINCRBY로 게임 점수 증감** | 동시성 안전 (단일 스레드). 그러나 음수 누적 등 비즈니스 규칙은 클라이언트에서 검증. |
| **Vector 검색용으로 ZSET 임시 사용** | 8.x부터 Vector Set이 정식 자료형. `VSIM` 사용. |

---

## 6. RedisInsight

Browser → ZSET 키 → score-member 표 (정렬 가능).
Workbench에서 `ZRANGEBYSCORE` 결과를 표로 시각화.

---

## 7. 패턴 모음

### 7.1 TOP-N 리더보드 자동 잘라내기
```
ZADD lb $score $player
ZREMRANGEBYRANK lb 0 -1001     # 상위 1000만 유지
```

### 7.2 시간 윈도 카운터 (sliding window rate limit)
```
NOW=$(date +%s)
ZADD reqs $NOW $request_id
ZREMRANGEBYSCORE reqs -inf $((NOW - 60))   # 60초 이전 제거
ZCARD reqs                                  # 최근 60초 요청 수
```

### 7.3 우선순위 큐
```
ZADD pq 1 high-priority-job
ZADD pq 2 normal
ZADD pq 3 low

# 가장 우선순위 높은 (score 작은) 작업 가져오기
BZPOPMIN pq 0
```

### 7.4 사전순 인덱스 (auto-complete 후보)
```
# score 모두 0으로 두면 BYLEX 만 의미 있음
ZADD names 0 alice 0 alex 0 bob 0 carol
ZRANGEBYLEX names "[al" "[am"     # al~am 시작 이름
```

---

## 8. 직접 해보기

1. 100명 이상 ZADD → 인코딩 전환 시점 (`zset-max-listpack-entries` 기본 128).
2. 동일 score 5개 → ZRANGE 결과 순서가 멤버 사전순인지 확인.
3. `ZADD k 9999999999999999 huge` → 점수가 정수 그대로 보이는가? (double 정밀도 한계)
4. 시간 윈도 rate limit 패턴 직접 구현 (Python 또는 cli 스크립트).
5. `ZUNIONSTORE` 로 두 게임의 합산 리더보드 만들기.

---

## 9. 참고 자료

- **[공식 문서] Redis Sorted Sets**
  - URL: <https://redis.io/docs/latest/develop/data-types/sorted-sets/>
  - 참고 부분: 사용 케이스 ("leaderboards", "secondary indexes") — §1 근거

- **[공식 문서] ZADD / ZRANGE / ZRANGEBYSCORE / ZINCRBY**
  - URL: <https://redis.io/docs/latest/commands/zadd/>, `/zrange/`, etc.
  - 참고 부분: Time complexity, NX/XX/GT/LT 옵션 — §2, §4.3 근거

- **[GitHub] redis/redis — src/t_zset.c (8.6)**
  - URL: <https://github.com/redis/redis/blob/8.6/src/t_zset.c>
  - 참고 부분: `zset` 구조체 (dict + zskiplist 병행) — §4.2 근거

- **[GitHub] redis/redis — redis.conf (8.6)**
  - URL: <https://github.com/redis/redis/blob/8.6/redis.conf>
  - 참고 부분: `zset-max-listpack-entries 128`, `zset-max-listpack-value 64` 기본값 — §4.1 근거
