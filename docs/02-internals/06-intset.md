# 06. intset — 정수 전용 정렬 배열

> **학습 목표**: intset이 메모리 극단 절약 + 캐시 효율을 위해 어떻게 설계되었는지, 비정수 원소 추가 시 어떻게 listpack/hashtable로 변환되는지 이해한다.
> **예상 소요**: 15분

---

## 1. 개념

```c
typedef struct intset {
    uint32_t encoding;   // INTSET_ENC_INT16 / INT32 / INT64
    uint32_t length;     // 원소 개수
    int8_t contents[];   // 정렬된 정수 배열 (encoding에 따라 2/4/8 byte씩)
} intset;
```

핵심:
- **모든 원소가 정수** 일 때만 사용 (Set 한정).
- **정렬된 배열** → `SISMEMBER` 가 binary search → O(log N).
- **encoding 자동 승격** : 큰 정수 들어오면 16→32, 32→64로.

> 출처: <https://github.com/redis/redis/blob/8.6/src/intset.c>

---

## 2. 인코딩 승격 (Upgrade)

```
SADD k 1 2 3                  # encoding = INT16 (2 byte씩)
OBJECT ENCODING k             # "intset"

SADD k 100000                 # 16-bit 한계(32767) 넘음
                              # 전체 contents를 INT32 (4 byte씩)로 재배치
OBJECT ENCODING k             # 여전히 "intset"

SADD k 5000000000             # 32-bit 한계 넘음 → INT64로 승격
OBJECT ENCODING k             # 여전히 "intset"
```

승격은 **단방향** — 큰 인코딩으로만 가고 작은 쪽으로는 안 돌아온다.

---

## 3. 비정수 들어오면?

```
SADD k 1 2 3
OBJECT ENCODING k             # "intset"

SADD k "abc"                  # 정수 아닌 멤버 추가
OBJECT ENCODING k             # "listpack" 또는 "hashtable" (개수에 따라)
```

전환 후에는 더 큰 인코딩(listpack/hashtable)을 쓰므로 **메모리 증가**.

---

## 4. 임계값

```
set-max-intset-entries 512
```

512개 초과 시 정수 셋이라도 hashtable로 전환.
이유: intset의 binary search O(log N)가 N이 커지면 hashtable의 O(1)보다 느려질 수 있음.

> 출처: <https://github.com/redis/redis/blob/8.6/redis.conf> `set-max-intset-entries 512`

---

## 5. 메모리 비교 예

| 셋 | intset | hashtable |
|---|---|---|
| 100 정수 (16-bit 가능) | 200 byte (정렬 배열만) | 수 KB (table + node) |
| 1000 정수 | 2 KB | 10+ KB |

---

## 6. SISMEMBER 복잡도

| 인코딩 | 복잡도 |
|---|---|
| `intset` | O(log N) (binary search) |
| `listpack` | O(N) |
| `hashtable` | O(1) (평균) |

작은 셋이면 intset이 cache hit이 더 좋아 hashtable보다도 빠를 수 있다.

---

## 7. 흔한 함정

| 함정 | 설명 |
|---|---|
| **정수처럼 생긴 문자열도 intset에 가는가?** | `SADD k "1"` 도 redis가 정수로 해석하면 intset으로 들어감. `OBJECT ENCODING` 으로 확인. |
| **승격 비용** | INT16→INT32 시 contents 전체 재할당. 큰 셋이면 1회성 비용. |
| **set-max-intset-entries 작게** | 정수 많은 셋이 일찍 hashtable로 → 메모리 증가. |
| **음수 정수도 OK** | 부호 있는 표현. INT16 = -32768 ~ 32767 |

---

## 8. 직접 해보기

1. `SADD k 1 2 3` → encoding intset, `MEMORY USAGE` 확인.
2. `SADD k 70000` → encoding intset 유지하지만 알고리즘 내부적으로 INT32 승격.
3. `SADD k "abc"` → encoding 변화 + 메모리 증가 비교.
4. `set-max-intset-entries 4` 로 줄이고 5번째 정수 추가 → hashtable로 전환 확인.

---

## 9. 참고 자료

- **[GitHub] redis/redis — src/intset.c, src/intset.h (8.6)**
  - URL: <https://github.com/redis/redis/blob/8.6/src/intset.c>
  - 참고 부분: intset 구조체, `intsetAdd`, `intsetUpgradeAndAdd` 함수 — §1, §2 근거

- **[GitHub] redis/redis — redis.conf** `set-max-intset-entries 512`
  - URL: <https://github.com/redis/redis/blob/8.6/redis.conf>
  - 참고 부분: 임계값 주석 — §4 근거
