# 04. hashtable (dict) & 점진적 rehashing

> **학습 목표**: Redis의 dict이 두 개의 hash table을 관리하는 이유 — **점진적 rehashing**. 이를 통해 단일 스레드인데도 큰 Hash가 멈추지 않는다.
> **예상 소요**: 25분

---

## 1. 왜 두 개의 테이블?

일반적인 hash table은 부하율(load factor)이 높아지면 더 큰 배열로 옮긴다 (rehashing).

**문제**: 키가 1억 개라면 한 번에 1억 개를 옮기는 동안 단일 스레드 Redis는 멈춘다.

**해결**: dict 안에 **`ht[2]` 두 개**를 두고, **rehashing 중에는 양쪽을 동시에 사용**.

```c
typedef struct dict {
    dictType *type;
    dictEntry **ht_table[2];     // 두 개의 hash table
    unsigned long ht_used[2];
    long rehashidx;              // -1: rehashing 안 함, 0+: 진행 중인 버킷 인덱스
    ...
} dict;
```

> 출처: <https://github.com/redis/redis/blob/8.6/src/dict.h>

---

## 2. 점진적 rehashing 동작

```
초기:        ht[0] = [...], ht[1] = NULL
load_factor 임계 초과:
             ht[1] = malloc(2 * ht[0].size)
             rehashidx = 0
명령마다:    rehashidx 위치의 버킷을 ht[0] → ht[1] 이동, rehashidx++
완료:        ht[0] = ht[1], ht[1] = NULL, rehashidx = -1
```

**검색 (`dictFind`)**:
```c
if (rehashidx != -1) check_both_ht();   // 양쪽 다 봄
else check_ht0();
```

**삽입**: `ht[1]` 에 직접.
**삭제 / 갱신**: 양쪽 다 봐야 함.

추가로 `serverCron` (1초당 N번 호출) 안에서도 일정 시간 rehashing 작업.

> 출처: <https://github.com/redis/redis/blob/8.6/src/dict.c> `dictRehash`, `_dictRehashStep` 함수

---

## 3. 부하율 (Load Factor)

```
load_factor = used / size
```

- 5 (= 500%) 이상 → rehashing 시작.
- BGSAVE / BGREWRITEAOF 동안에는 rehashing 보류 (CoW와 충돌 방지).

> 출처: <https://github.com/redis/redis/blob/8.6/src/dict.c> `dict_force_resize_ratio`

---

## 4. 충돌 해결 — chaining

각 버킷은 단일 연결 리스트.
충돌이 적으면 O(1), 많아지면 O(체인 길이).
좋은 hash 함수 + 적절한 부하율 관리로 평균 O(1) 유지.

```
ht[0]
  bucket 0 → entry → entry → entry
  bucket 1 → entry
  bucket 2 → NULL
  ...
```

---

## 5. SipHash로 dictionary attack 방어

Redis 4.0 이후 **SipHash 1-2** 를 사용. 매번 임의 시드로 초기화되어 외부에서 의도적으로 충돌을 유발하는 공격을 어렵게 한다.

> 출처: <https://github.com/redis/redis/blob/8.6/src/siphash.c>

---

## 6. SCAN과 점진적 rehashing

```
SCAN 0 COUNT 10
```

`SCAN` 은 cursor 비트 reverse 알고리즘을 사용해서 **rehashing 중에도 안전하게 순회**한다 (중복 가능, 누락 방지). KEYS와 결정적으로 다른 점.

> 출처: <https://redis.io/docs/latest/commands/scan/>
> 참고 부분: "cursor never goes backward" + 양 hash table 동시 순회 설명

---

## 7. 큰 Hash 다루는 팁

- `HGETALL` 대신 `HSCAN` 으로 페이지네이션
- 매우 큰 Hash는 자료 모델 분할 검토 (예: `user:1001:profile`, `user:1001:settings` 분리)
- 한 키 안의 필드가 1만 개를 넘으면 sharding 패턴 (`user:1001:p1`, `:p2`) 고려
- **`UNLINK`** 로 삭제 (DEL 시 단일 스레드 멈춤)

---

## 8. 메모리 분석

```
HSET h f1 v1 ... f200 v200      # listpack 임계 넘어 hashtable
MEMORY USAGE h                  # hash table overhead 포함

# 같은 데이터, listpack로 두면:
CONFIG SET hash-max-listpack-entries 1000
DEL h2
HSET h2 f1 v1 ... f200 v200
MEMORY USAGE h2                 # 더 작음
```

**hashtable의 오버헤드**: 빈 버킷 + dictEntry 포인터 + chaining 노드.

---

## 9. 흔한 함정

| 함정 | 설명 |
|---|---|
| `KEYS *` | hash table 전체 + chain 모두 순회. SCAN 사용. |
| 매우 큰 키를 `DEL` | 단일 스레드 멈춤. UNLINK. |
| listpack→hashtable 전환 후 메모리 회수 안 됨 | 키를 새로 만들거나 UNLINK. |
| `OBJECT FREQ k` 가 안 됨 | LFU 정책일 때만 사용 가능. |

---

## 10. 직접 해보기

1. 100, 1000, 10000개 필드 Hash 만들고 `MEMORY USAGE` 비교.
2. 큰 Hash에서 `HSCAN` 으로 cursor 순회 — cursor가 0으로 돌아오는 시점 확인.
3. `INFO memory` → `mem_fragmentation_ratio` 관찰.
4. 초기화 후 작은 Hash 만들고 `OBJECT ENCODING` → 임계 초과시 변화.

---

## 11. 참고 자료

- **[GitHub] redis/redis — src/dict.h, src/dict.c (8.6)**
  - URL: <https://github.com/redis/redis/blob/8.6/src/dict.h>, <https://github.com/redis/redis/blob/8.6/src/dict.c>
  - 참고 부분: `dict` 구조체 (ht[2], rehashidx) 및 `dictRehash` 함수 — §1, §2 근거

- **[공식 문서] SCAN**
  - URL: <https://redis.io/docs/latest/commands/scan/>
  - 참고 부분: cursor 알고리즘 설명 — §6 근거

- **[GitHub] redis/redis — src/siphash.c**
  - URL: <https://github.com/redis/redis/blob/8.6/src/siphash.c>
  - 참고 부분: SipHash 사용 — §5 근거

- **[블로그] antirez — Hash table reactive resizing (옛 글)**
  - URL: <http://antirez.com/news/82>
  - 참고 부분: 점진적 rehashing 도입 동기 — §1 보충 근거
