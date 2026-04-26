# 03. listpack & quicklist

> **학습 목표**: listpack이 왜 작은 자료구조의 메모리 효율 챔피언인지, quicklist가 큰 List에서 어떻게 listpack과 링크드 리스트의 장점을 합치는지 설명할 수 있다. (8.x에는 ziplist가 사실상 사라졌다.)
> **예상 소요**: 25분

---

## 1. listpack 이전 — ziplist의 한계

Redis ≤ 6.x에서는 작은 자료구조용 인코딩이 **ziplist** 였다.

ziplist는 가변 길이 인코딩 + 끝에서부터 거꾸로 순회 가능한 메타로 메모리는 작지만:

- **cascading update**: 중간 항목의 길이가 늘어나면 뒤따르는 모든 항목의 prevlen 필드가 연쇄 갱신 → O(N²) 최악.
- **버그가 많은 prevlen 인코딩**.

이를 해결하려고 Redis 7.0에서 **listpack** 도입, 8.x에서는 ziplist를 거의 모두 listpack으로 대체했다.

> 출처: <https://github.com/redis/redis/blob/8.6/src/listpack.c> 파일 상단 주석 — listpack 도입 동기

---

## 2. listpack — 촘촘한 바이트 배열

```
[total bytes (4)] [num elements (2)] [element 1] [element 2] ... [end byte (1=0xFF)]
```

각 element:
```
[encoding type] [data] [back-len]
```

- `back-len` 은 항상 element의 끝에 붙어 있어서 **앞으로도 뒤로도 순회 가능**.
- prevlen 같은 cascading 필드가 **없다** → ziplist의 cascade 문제 해결.

특징:
- 캐시 친화적 (한 덩어리 메모리)
- 작은 자료구조에서 **메모리/속도 모두 좋음**
- O(N) 탐색이지만 **N이 작을 때만 사용**되므로 실제로는 매우 빠름

---

## 3. quicklist — listpack 노드의 양방향 링크드 리스트

```
HEAD ←→ [listpack node] ←→ [listpack node] ←→ [listpack node] ←→ TAIL
                                ▲
                                node 안에는 작은 listpack 1개
```

각 노드 `quicklistNode`:
- 이전/다음 노드 포인터
- 자신의 listpack 포인터
- 메타 (개수, 압축 여부)

> 출처: <https://github.com/redis/redis/blob/8.6/src/quicklist.h>
> 참고 부분: `quicklistNode` 구조체 정의

### 3.1 노드 크기 정책

```
list-max-listpack-size -2
```

| 값 | 의미 |
|---|---|
| `-1` | 한 노드 4KB |
| `-2` | 한 노드 8KB **(기본)** |
| `-3` | 16KB |
| `-4` | 32KB |
| `-5` | 64KB |
| 양수 N | 한 노드에 N개 요소 |

### 3.2 압축 (선택)

```
list-compress-depth 0       # 0 = 압축 안 함 (기본)
                            # 1 = head/tail 1개씩 빼고 중간 노드 LZF 압축
                            # 2 = 양 끝 2개씩 빼고
```

큰 List를 메모리 절약 위해 압축할 수 있지만, **압축 노드 접근 시 복원 비용**이 든다. 큐 패턴(양 끝만 사용)에서는 효과가 좋다.

---

## 4. 작은 List는 단일 listpack

Redis 7.2+ 부터 **List가 충분히 작으면 quicklist 노드 1개도 만들지 않고 단일 listpack 인코딩**으로 둔다.

```
RPUSH q a b c
OBJECT ENCODING q       # "listpack"  (단일 listpack)

# 임계 초과시
for i in $(seq 1 1000); do redis-cli RPUSH q "item-$i" > /dev/null; done
redis-cli OBJECT ENCODING q   # "quicklist"
```

---

## 5. 메모리 절약 효과

| 자료형 | 작은 인코딩 | 큰 인코딩 | 절약 |
|---|---|---|---|
| Hash 100필드 | listpack ~수 KB | hashtable ~10+ KB (table 자체) | 2~5x |
| Set 100원소 (정수) | intset ~수백 byte | hashtable ~수 KB | 5~10x |
| ZSET 100원소 | listpack ~수 KB | skiplist+ht ~10+ KB | 2~5x |

> 출처: <https://github.com/redis/redis/blob/8.6/redis.conf>
> 참고 부분: listpack 임계값 옵션 주석 — "the listpack representation is used"

---

## 6. 흔한 함정

| 함정 | 설명 |
|---|---|
| ziplist 단어를 8.x에서 본다 | 일부 옛 옵션 이름은 호환을 위해 남아 있음 (`hash-max-ziplist-*` 등). 새 옵션은 listpack 이름. |
| `list-max-listpack-size` 값 -2를 8KB가 아닌 8바이트로 오해 | 음수 = KB 단위 의미, 양수 = 요소 개수 |
| 작은 List에 `LSET 100 ...` 시도 | listpack 단일 인코딩에서도 인덱스 접근은 O(N). |
| 큰 List에서 자주 중간 접근 | List 자체가 적합 자료형이 아님. ZSET / Hash 고려. |

---

## 7. 직접 해보기

1. `RPUSH q a b c` 후 `OBJECT ENCODING` → "listpack" 인지.
2. `list-max-listpack-size 8` 로 줄인 후 같은 명령 → encoding 차이.
3. `MEMORY USAGE` 로 listpack vs quicklist 메모리 비교.
4. 1000개 List 만들고 `list-compress-depth 1` 후 `MEMORY USAGE` 차이.

---

## 8. 참고 자료

- **[GitHub] redis/redis — src/listpack.c (8.6)**
  - URL: <https://github.com/redis/redis/blob/8.6/src/listpack.c>
  - 참고 부분: 파일 상단 주석 — §1 ziplist 한계와 listpack 도입 동기 근거

- **[GitHub] redis/redis — src/quicklist.h (8.6)**
  - URL: <https://github.com/redis/redis/blob/8.6/src/quicklist.h>
  - 참고 부분: `quicklistNode`, `quicklist` 구조체 — §3 근거

- **[GitHub] redis/redis — redis.conf (8.6)** `list-max-listpack-size`, `list-compress-depth`
  - URL: <https://github.com/redis/redis/blob/8.6/redis.conf>
  - 참고 부분: 옵션 의미 주석 — §3.1, §3.2 근거

- **[블로그] How Redis Lists Work Internally — OneUptime (2026-03-31)**
  - URL: <https://oneuptime.com/blog/post/2026-03-31-redis-lists-work-internally-quicklist-listpack/view>
  - 참고 부분: list-max-listpack-size -2 (8KB) 기본값 설명 — §3.1 교차 검증
