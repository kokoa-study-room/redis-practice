# 02. List

> **학습 목표**: List가 양방향 링크드 리스트라는 점, quicklist + listpack 인코딩, BLPOP 블로킹의 의미를 이해하고 큐로 안전하게 쓸 수 있다.
> **예상 소요**: 25분

---

## 1. 개념

Redis List는 **양 끝(head/tail)에서 push/pop이 O(1)** 인 시퀀스 자료형. 내부적으로는 **quicklist** (8.x 기준) — listpack 노드들의 양방향 링크드 리스트.

```
HEAD                                                    TAIL
 ↓                                                       ↓
[listpack node][listpack node][listpack node][listpack node]
   ↑─ 한 노드가 작은 listpack(촘촘한 바이트 배열) 을 들고 있다
```

용도: **큐 / 스택 / 최근 N개 로그 / 작업 분배**.
크기: 한 List에 최대 2^32-1 (≈ 42억) 개 요소.

> 출처: <https://redis.io/docs/latest/develop/data-types/lists/>
> 참고 부분: "A list of strings, sorted by insertion order" + 사용처 표 — §1 근거

---

## 2. 기본 사용법

```
# 양 끝 push/pop
LPUSH q a b c        # head 쪽으로 c → b → a 순으로 들어가서 결과: [c, b, a]
RPUSH q x y          # tail 쪽으로 push 결과: [c, b, a, x, y]
LPOP q               # "c"
RPOP q               # "y"
LLEN q               # 3 (남은 개수)

# 인덱스 접근 (0부터, 음수 = 뒤에서)
LINDEX q 0           # 첫 요소
LINDEX q -1          # 마지막 요소

# 범위 조회
LRANGE q 0 -1        # 전체
LRANGE q 0 9         # 처음 10개
LRANGE q -10 -1      # 마지막 10개

# 잘라내기 (TTL 없는 무한 큐 방지)
LTRIM q 0 99         # 앞 100개만 남기고 나머지 삭제

# 삽입 / 수정
LSET q 0 "new"       # 0번 요소를 "new"로 교체 (인덱스 없으면 에러)
LINSERT q BEFORE "b" "newb"

# 블로킹 pop (큐 컨슈머)
BLPOP q 5            # 5초까지 대기. 들어오면 즉시 pop, timeout 시 nil
BRPOP q 0            # 0 = 무제한 대기

# 한 번에 여러 keys
BLPOP q1 q2 q3 5     # 셋 중 먼저 들어오는 데서 pop
```

### Redis 7+: LPOP/RPOP의 COUNT 옵션

```
LPUSH q a b c d e
LPOP q 3             # ["e", "d", "c"]  ← 한 번에 여러 개
```

### Redis 6.2+: LMOVE / BLMOVE (다른 List로 원자적 이동)

```
LMOVE src dst LEFT RIGHT     # src의 head → dst의 tail (작업 큐 패턴)
BLMOVE src dst LEFT RIGHT 5  # src 비어 있으면 5초 대기
```

> 출처: <https://redis.io/docs/latest/commands/lmove/>
> 참고 부분: "Atomically returns and removes the first/last element" — 작업 큐 패턴 안전성 근거

---

## 3. 클라이언트 코드 예제

### Python — 작업 큐 컨슈머 패턴

```python
import redis

r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)

# 프로듀서
r.rpush("jobs", "task-1", "task-2", "task-3")

# 컨슈머 — BLPOP 무한 루프
while True:
    item = r.blpop("jobs", timeout=5)  # (queue_name, value) or None
    if item is None:
        print("5초 동안 일감 없음, 헬스체크 등 다른 일")
        continue
    queue, payload = item
    print(f"처리: {payload}")
    # 처리 로직...
```

### Node.js — 같은 패턴 (node-redis)

```javascript
import { createClient } from "redis";
const r = createClient(); await r.connect();

await r.rPush("jobs", ["task-1", "task-2", "task-3"]);

while (true) {
  const item = await r.blPop("jobs", 5);  // {key, element} or null
  if (!item) { console.log("idle"); continue; }
  console.log("처리:", item.element);
}
```

---

## 4. 내부 동작 / 시간 복잡도

### 4.1 인코딩

| 인코딩 | 조건 | 설명 |
|---|---|---|
| `listpack` | 단일 listpack로 충분히 작은 List (한 노드 안에 다 들어감) — Redis 7.2+ 부터 작은 List는 단일 listpack 인코딩 | 캐시 친화적, 메모리 효율 |
| `quicklist` | 일반적인 경우 | listpack 노드들의 링크드 리스트 |

임계 옵션:
```
list-max-listpack-size -2        # -2 = 한 노드당 8KB (기본)
                                 # 양수면 요소 개수 기준
list-compress-depth 0            # 양 끝 N개를 제외한 중간 노드는 LZF 압축 (0 = 비활성)
```

확인:
```
LPUSH small a b c
OBJECT ENCODING small            # "listpack"

# 큰 데이터 push
for i in $(seq 1 1000); do redis-cli RPUSH big "item-$i" > /dev/null; done
redis-cli OBJECT ENCODING big    # "quicklist"
```

> 출처 (인코딩/임계): <https://github.com/redis/redis/blob/8.6/redis.conf>
> 참고 부분: `list-max-listpack-size` 와 `list-compress-depth` 주석 — 기본값 -2 / 0 근거

### 4.2 Big-O

| 명령 | 복잡도 | 비고 |
|---|---|---|
| `LPUSH`, `RPUSH`, `LPOP`, `RPOP`, `LLEN` | **O(1)** | 양 끝 작업 |
| `LINDEX`, `LSET` | O(N) | 중간 인덱스 접근 → 노드 순회 필요 |
| `LRANGE start stop` | O(S+N) | S=시작 위치, N=반환할 요소 수 |
| `LREM count value` | O(N+M) | N=리스트 길이, M=제거할 개수 |
| `LINSERT` | O(N) | pivot 찾기 |
| `BLPOP/BRPOP` | O(1) (대기 시간 제외) | |

---

## 5. 흔한 함정

| 함정 | 설명 |
|---|---|
| **무한 RPUSH 후 LPOP 안 함** | 메모리 폭증. 반드시 `LTRIM` 으로 길이 제한 또는 `MAXLEN` 패턴. |
| **인덱스 접근 남발** | `LINDEX`/`LSET`은 O(N). List는 양 끝 작업이 본질. 중간 접근이 잦으면 **다른 자료형 선택** (Sorted Set 등). |
| **BLPOP 안에서 다른 명령** | 블로킹된 connection은 그동안 다른 명령 못 보냄. 컨슈머 connection을 별도 pool로. |
| **Pub/Sub처럼 이벤트로 사용** | List는 push/pop이지 fan-out이 아니다. 같은 요소를 여러 컨슈머에 보내려면 Stream + Consumer Group 사용. |
| **LREM 비효율** | 큰 List에서 특정 값 삭제는 O(N). 자주 필요하면 Set 또는 Hash로 모델링. |

---

## 6. RedisInsight에서 확인

Browser → List 키 클릭 → 우측에:
- Push to head / tail 버튼
- 행 단위 수정/삭제
- Encoding 확인 (`listpack` / `quicklist`)

요소가 많으면 페이지네이션으로 잘라 본다.

---

## 7. 큐 패턴 비교

| 패턴 | 명령 | 특징 |
|---|---|---|
| **Reliable queue** | `RPUSH src` + `BLMOVE src dst LEFT RIGHT 0` | 컨슈머가 dst를 처리 후 `LREM dst 1 <item>` 으로 ack. 죽으면 dst에 남아 재처리 가능. |
| **Simple queue** | `RPUSH` + `BLPOP` | 단순. 컨슈머 죽으면 메시지 손실 (in-flight). |
| **At-least-once 큐 필요** | Stream + Consumer Group 사용 (06-stream.md) | List보다 안전하지만 복잡 |

---

## 8. 직접 해보기

1. `RPUSH log "msg-1" "msg-2" ... "msg-1000"` 후 `LTRIM log -100 -1` → 마지막 100개만 남기는지 확인.
2. 두 터미널에서 한 쪽은 `BLPOP q 0`, 다른 쪽은 `RPUSH q "data"`. 즉시 풀리는지.
3. 작은 List, 큰 List 각각 만들어 `OBJECT ENCODING` 비교.
4. `LREM` 으로 중간 요소 삭제 후 List가 어떻게 변하는지 LRANGE로 확인.

---

## 9. 참고 자료

- **[공식 문서] Redis Lists**
  - URL: <https://redis.io/docs/latest/develop/data-types/lists/>
  - 참고 부분: "Insertion order" + 사용 케이스 — §1 근거

- **[공식 문서] LPUSH / RPUSH / BLPOP / LMOVE**
  - URL: <https://redis.io/docs/latest/commands/lpush/>, `/blpop/`, `/lmove/`
  - 참고 부분: 각 명령의 Time complexity — §4.2 근거

- **[GitHub] redis/redis — src/quicklist.h (8.6)**
  - URL: <https://github.com/redis/redis/blob/8.6/src/quicklist.h>
  - 참고 부분: `quicklistNode` 구조체 정의 — quicklist의 노드 단위 listpack 보관 근거

- **[GitHub] redis/redis — redis.conf (8.6)**
  - URL: <https://github.com/redis/redis/blob/8.6/redis.conf>
  - 참고 부분: `list-max-listpack-size -2` 기본값 주석 — §4.1의 임계값 근거
