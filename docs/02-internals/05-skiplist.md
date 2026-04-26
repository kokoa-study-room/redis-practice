# 05. Skip List — Sorted Set의 본체

> **학습 목표**: 스킵리스트가 왜 균형 트리(red-black 등) 대신 선택됐는지, 평균 O(log N) 작동의 직관, ZSET이 skiplist + hashtable 조합인 이유.
> **예상 소요**: 30분

---

## 1. 스킵리스트란?

스킵리스트(Skip List)는 **확률적 자료구조**. 정렬된 링크드 리스트에 **다층의 "건너뛰기" 포인터**를 추가한 것.

```
Level 3: HEAD ───────────────────────────────────────→ NIL
Level 2: HEAD ──────────→ 25 ──────────→ 70 ────────→ NIL
Level 1: HEAD → 10 ────→ 25 ───→ 50 ──→ 70 ─→ 90 ──→ NIL
Level 0: HEAD → 10 → 18 → 25 → 40 → 50 → 70 → 80 → 90 → NIL
```

검색: 가장 위 레벨에서 시작 → 다음 노드가 검색값보다 크면 한 단계 내려감 → 반복.

평균 O(log N), 최악 O(N) (아주 운이 나쁠 때).

---

## 2. 왜 균형 트리 대신?

| 장점 (vs Red-Black/AVL) | |
|---|---|
| 구현 단순 | 회전 같은 복잡한 연산 없음 |
| range query 자연스러움 | level 0 의 doubly linked list로 순서대로 이동 |
| concurrency 잠재력 | (Redis는 단일 스레드라 직접 활용은 안 함) |

> antirez 본인 의견: "Implementation is simpler and more readable" — 스킵리스트 도입 이유.
> 출처: <http://antirez.com/news/55> (옛 글이지만 ZSET 설계 의도 설명)

---

## 3. Redis의 zskiplist 구현

```c
typedef struct zskiplistNode {
    sds ele;                                   // 멤버
    double score;                              // 점수
    struct zskiplistNode *backward;            // 이전 노드 (level 0)
    struct zskiplistLevel {
        struct zskiplistNode *forward;         // 다음 노드 (이 레벨)
        unsigned long span;                    // 다음 노드까지 점프하는 노드 수
    } level[];                                 // FAM, 레벨별 정보
} zskiplistNode;
```

> 출처: <https://github.com/redis/redis/blob/8.6/src/server.h> `zskiplistNode` 정의 또는 src/t_zset.c

핵심 필드:
- `score`: ZSET의 정렬 키 (double)
- `ele`: 멤버 (SDS)
- `level[i].span`: rank 계산에 사용 — 노드 간 거리 합으로 ZRANK O(log N)
- `backward`: 역방향 순회 (`ZREVRANGE`)

---

## 4. 레벨 결정 (확률)

새 노드의 레벨은 동전 던지기:
```
level = 1
while (random() < 0.25 && level < 32):
    level += 1
```

p=0.25 → 평균 4번에 1번꼴로 한 단계 위로 올라감.
최대 레벨 32 (현재 Redis 기준).

---

## 5. ZSET = skiplist + hashtable

```c
typedef struct zset {
    dict *dict;            // 멤버 → score 빠른 조회
    zskiplist *zsl;        // score 순 정렬
} zset;
```

| 쿼리 | 사용 자료구조 | 복잡도 |
|---|---|---|
| `ZSCORE k m` | dict | O(1) |
| `ZADD k score m` | dict 갱신 + zsl 삽입 | O(log N) |
| `ZRANGE k 0 -1` | zsl 순회 | O(log N + M) |
| `ZRANGEBYSCORE k a b` | zsl 검색 | O(log N + M) |
| `ZRANK k m` | zsl 검색 + span 합산 | O(log N) |
| `ZREM k m` | dict 삭제 + zsl 삭제 | O(log N) |

**왜 둘 다?** 멤버 lookup도 O(1)이고 score 정렬도 O(log N)으로 빠르게.
**메모리 두 배 비용**을 감수하면서.

---

## 6. listpack과의 전환

작은 ZSET은 listpack 으로:
```
[total][num][score][member][backlen][score][member][backlen]...[end]
```
- 멤버 수 ≤ 128 (`zset-max-listpack-entries`) AND 각 멤버 ≤ 64 byte (`zset-max-listpack-value`).
- 임계 초과 시 skiplist + hashtable 로 전환.

```
ZADD k 1 a 2 b
OBJECT ENCODING k       # "listpack"

# 130개 추가
for i in $(seq 1 130); do redis-cli ZADD k $i "m$i" > /dev/null; done
redis-cli OBJECT ENCODING k    # "skiplist"
```

---

## 7. 흔한 함정

| 함정 | 설명 |
|---|---|
| **score를 큰 정수로** | double은 53-bit 정밀도. 9007199254740992(2^53) 이상은 정밀도 손실. snowflake ID 같은 64-bit는 score로 부적합 — 멤버 이름 또는 별도 Hash로. |
| **동률 시 순서 의존** | 같은 score면 멤버 사전순. 시간 순서 의존하면 score=timestamp 사용. |
| **`ZRANGE 0 -1`** 큰 ZSET | 전체 응답 큼. 페이지네이션 또는 ZSCAN. |
| **listpack → skiplist 후 메모리 회수 안 됨** | 키 재생성. |

---

## 8. 직접 해보기

1. `ZADD k 1 a 2 b` 후 `OBJECT ENCODING` → listpack.
2. 130개 추가 → skiplist 전환.
3. `MEMORY USAGE` 비교.
4. `ZADD k 9007199254740993 huge` (2^53+1) → `ZSCORE k huge` 가 그대로 9007199254740993 인가? (정밀도 손실 여부)
5. `INFO commandstats` 에서 ZADD/ZRANGE 의 평균 호출 시간 확인.

---

## 9. 참고 자료

- **[GitHub] redis/redis — src/server.h, src/t_zset.c (8.6)**
  - URL: <https://github.com/redis/redis/blob/8.6/src/t_zset.c>
  - 참고 부분: `zset` 구조체 (dict + zskiplist), `zslInsert`, `zslDelete`, `zslGetRank` — §3, §5 근거

- **[GitHub] redis/redis — redis.conf (8.6)** `zset-max-listpack-entries 128`
  - URL: <https://github.com/redis/redis/blob/8.6/redis.conf>
  - 참고 부분: 임계값 — §6 근거

- **[블로그] antirez — Skip Lists in Redis (옛 글)**
  - URL: <http://antirez.com/news/55>
  - 참고 부분: skiplist를 채택한 이유 — §2 근거

- **[원논문] Pugh, William. "Skip lists: A probabilistic alternative to balanced trees." (1990)**
  - URL: <https://homepage.cs.uiowa.edu/~ghosh/skip.pdf>
  - 참고 부분: 평균 O(log N) 증명 — §1 알고리즘 근거
