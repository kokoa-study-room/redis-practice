# 07. rax — Radix Tree (Stream의 본체)

> **학습 목표**: rax(라딕스 트리)가 무엇이며, Stream의 ID 인덱싱과 Cluster의 channel 매칭에 어떻게 쓰이는지 이해한다.
> **예상 소요**: 20분

---

## 1. Radix Tree란?

**Trie의 압축 버전**. 자식이 하나뿐인 노드 체인을 하나로 합쳐 메모리 절약.

```
Trie:                    Radix Tree (compact):
  r                        r—o—m
  └─o                       ├─e
     ├─m                    └─u—l—u—s
     ├─e
     └─u
       └─l
         └─u
           └─s
```

장점:
- **공통 prefix 공유** → 메모리 효율
- **정렬된 순회** 자연스러움
- **lookup O(k)** k=key 길이

---

## 2. Redis가 rax를 쓰는 곳

### 2.1 Stream

Stream의 entry ID (`<ms-time>-<seq>`)는 단조 증가. ID를 키로 한 정렬된 인덱스가 필요.

```
rax leaf → 작은 listpack 묶음 (entry 그룹)
```

- ID가 시간 단조라 prefix 공통 (앞자리들이 같음) → 압축 효과 매우 큼.
- 범위 쿼리 (`XRANGE - +`) 자연스러움.

> 출처: <https://github.com/redis/redis/blob/8.6/src/t_stream.c>

### 2.2 Cluster — channel/keyspace notification 매칭

`PSUBSCRIBE news.*` 같은 패턴 매칭에서 활용.

### 2.3 기타

ACL 사용자 lookup 등 일부 내부 사용처.

---

## 3. 코드 위치 / 자료

```
src/rax.h, src/rax.c
src/t_stream.c   # Stream에서 rax 사용 부분
```

> 출처: <https://github.com/redis/redis/blob/8.6/src/rax.c>
> 참고 부분: `raxNew`, `raxInsert`, `raxFind`, `raxIterator` 함수 — rax API

---

## 4. 비교: 다른 자료구조 대신 rax?

| 자료 | 단점 |
|---|---|
| Hash Table | 정렬 순회 안 됨 → range query 어려움 |
| Skip List | 메모리 큼 (각 노드별 메타) |
| B-Tree | 디스크 친화. 메모리에선 오버헤드 |
| Sorted Array | 삽입/삭제 O(N) |
| **Radix Tree** | prefix 공유 + 정렬 + O(k) lookup → Stream에 최적 |

---

## 5. 흔한 오해

| 오해 | 실제 |
|---|---|
| Stream은 ZSET을 쓴다 | 아니다. rax + listpack |
| rax는 일반 자료형이다 | 외부 노출 안 됨 (내부 자료구조) |
| `OBJECT ENCODING <stream-key>` 가 rax 반환 | "stream" 만 반환 |

---

## 6. 직접 해보기

1. `XADD events '*' user 1` 을 1만 번 → `XLEN events` 확인.
2. `MEMORY USAGE events` → 같은 entry 수의 List와 비교 (rax + listpack 효율 확인).
3. `XINFO STREAM events FULL` → 내부 노드 구조 메타 확인.
4. (코드 읽기) <https://github.com/redis/redis/blob/8.6/src/t_stream.c> 의 `streamCreateID`, `streamLookupConsumer` 함수 위주로.

---

## 7. 참고 자료

- **[GitHub] redis/redis — src/rax.h, src/rax.c (8.6)**
  - URL: <https://github.com/redis/redis/blob/8.6/src/rax.c>
  - 참고 부분: rax 구현 전체 — §1, §3 근거

- **[GitHub] redis/redis — src/t_stream.c**
  - URL: <https://github.com/redis/redis/blob/8.6/src/t_stream.c>
  - 참고 부분: Stream에서 rax + listpack 사용 — §2.1 근거

- **[GitHub] redis/redis 8.8-M02 release notes**
  - URL: <https://github.com/redis/redis/releases/tag/8.8-m02>
  - 참고 부분: "Optimize rax (radix tree) insert and lookup for sequential key patterns" (#14885) — rax가 8.8에서 더 최적화 중임을 시사

- **[Wikipedia] Radix tree**
  - URL: <https://en.wikipedia.org/wiki/Radix_tree>
  - 참고 부분: 정의 / Trie 비교 — §1 근거
