# 01. 인코딩 개관 (Encoding Overview)

> **학습 목표**: 외부 자료형과 내부 인코딩의 매핑 규칙을 알고, redis.conf 임계값을 바꾸면 인코딩이 어떻게 변하는지 직접 확인할 수 있다.
> **예상 소요**: 25분

---

## 1. 한 가지 사실

> **`OBJECT ENCODING <key>` 결과가 같은 자료형이라도 다를 수 있다.**

```
SET small "hi"
OBJECT ENCODING small        # "embstr"

SET small 100
OBJECT ENCODING small        # "int"

SET small "$(python -c 'print("a"*50)')"
OBJECT ENCODING small        # "raw"
```

세 명령 모두 String 키지만 인코딩은 달랐다. 이게 "왜 빠른가"의 절반의 답이다.

---

## 2. 인코딩 매핑 표 (자세히)

### 2.1 String

| 인코딩 | 조건 | 메모리 | 비고 |
|---|---|---|---|
| `int` | 값이 64-bit 정수 표현 가능 (`SET k 1234`) | 가장 작음 (값을 포인터에 직접) | INCR/DECR에 최적 |
| `embstr` | ≤ 44 byte 문자열 | 작음 (redisObject + sds 한 번 alloc) | 캐시 친화적 |
| `raw` | ≥ 45 byte 문자열 | 보통 | 별도 alloc |

> 임계 44byte: <https://github.com/redis/redis/blob/8.6/src/object.c> `OBJ_ENCODING_EMBSTR_SIZE_LIMIT 44`

### 2.2 List

| 인코딩 | 조건 |
|---|---|
| `listpack` (단일) | 한 노드에 다 들어갈 정도로 작음 |
| `quicklist` | 일반적인 경우 (listpack 노드들의 링크드 리스트) |

임계: `list-max-listpack-size -2` (한 노드 8KB)

### 2.3 Hash

| 인코딩 | 조건 |
|---|---|
| `listpack` | 필드 수 ≤ 128 (`hash-max-listpack-entries`) **AND** 모든 값 ≤ 64 byte (`hash-max-listpack-value`) |
| `hashtable` | 위 둘 중 하나라도 깨짐 |

### 2.4 Set

| 인코딩 | 조건 |
|---|---|
| `intset` | 모든 멤버가 정수 **AND** 개수 ≤ 512 (`set-max-intset-entries`) |
| `listpack` | 모든 멤버 ≤ 64 byte **AND** 개수 ≤ 128 (`set-max-listpack-entries`) (Redis 7.2+) |
| `hashtable` | 위 조건 깨짐 |

### 2.5 Sorted Set

| 인코딩 | 조건 |
|---|---|
| `listpack` | 멤버 수 ≤ 128 (`zset-max-listpack-entries`) **AND** 각 멤버 ≤ 64 byte (`zset-max-listpack-value`) |
| `skiplist` | 위 깨짐 — **실은 skiplist + hashtable** 두 자료구조 동시 운영 |

### 2.6 Stream

`stream` 한 가지. 내부는 rax tree + listpack 노드.

> 출처: <https://redis.io/docs/latest/commands/object-encoding/> + <https://github.com/redis/redis/blob/8.6/redis.conf>

---

## 3. 전환 방향성 (단방향)

| 전환 | 가능 |
|---|---|
| `listpack` → `hashtable` | ✅ 임계 초과 시 자동 |
| `intset` → `listpack`/`hashtable` | ✅ 비정수 또는 큰 셋 |
| 그 반대 (`hashtable` → `listpack`) | ❌ 거의 안 일어남 (성능 비용) |

**결과**: 한 번 큰 자료구조로 전환되면, 요소를 다 지워도 원래 인코딩으로 돌아오지 않는다.
운영 팁: 키를 **삭제 후 재생성** 하면 다시 작은 인코딩이 된다.

```
HSET h f1 v1   # listpack
HSET h big "..."  # hashtable
HDEL h big f1
OBJECT ENCODING h   # 여전히 hashtable

UNLINK h
HSET h f1 v1
OBJECT ENCODING h   # 다시 listpack
```

---

## 4. 임계값 직접 바꿔보기

```
# redis-cli에서 즉시 변경 (재시작 안 함; 운영에선 conf 파일에)
CONFIG SET hash-max-listpack-entries 8
CONFIG SET hash-max-listpack-value 16

# 확인
CONFIG GET hash-max-listpack-entries

# 작은 Hash
HSET h f1 v1 f2 v2
OBJECT ENCODING h   # listpack

# 9번째 필드 추가 → 임계 초과
HSET h f3 v3 f4 v4 f5 v5 f6 v6 f7 v7 f8 v8 f9 v9
OBJECT ENCODING h   # hashtable
```

---

## 5. 메모리 차이 측정

```
# listpack Hash
HSET small a 1 b 2 c 3
MEMORY USAGE small      # 예: 80~100 byte 부근

# hashtable Hash (같은 데이터)
CONFIG SET hash-max-listpack-entries 0
DEL small2
HSET small2 a 1 b 2 c 3
MEMORY USAGE small2     # 예: 200+ byte
```

> 정확한 수치는 시스템/할당자(jemalloc 버전)에 따라 다르지만 **listpack이 항상 더 적음**.

---

## 6. 인코딩이 영향을 주는 명령

| 인코딩 | 같은 명령이라도 차이 나는 부분 |
|---|---|
| `listpack` (Hash) | `HGETALL` 은 O(N), N이 작아 사실상 O(1) |
| `hashtable` (Hash) | `HGETALL` 은 O(N), N이 큼 |
| `intset` (Set) | `SISMEMBER` 가 binary search → O(log N) |
| `hashtable` (Set) | `SISMEMBER` 가 hash lookup → O(1) (하지만 상수항 커서 작은 셋은 intset이 빠를 수 있음) |
| `listpack` (ZSET) | `ZADD/ZRANGE` 가 O(N), N이 작아 빠름 |
| `skiplist` (ZSET) | `ZADD/ZRANGE` 가 O(log N) |

---

## 7. 흔한 함정

| 함정 | 설명 |
|---|---|
| `hash-max-listpack-entries` 같은 옵션을 **외운 값으로 단정** | 운영 환경에서 다르게 설정돼 있을 수 있음. `CONFIG GET` 으로 확인. |
| 한 번 hashtable로 가면 listpack 회귀 안 됨을 모름 | 메모리 분석 시 혼란 |
| `OBJECT ENCODING` 결과를 외우려고 함 | 외우지 말고 임계값 + 자료를 보면 자연 결정 |
| 여러 자료형의 임계값 옵션 이름이 비슷해서 헷갈림 | `hash-max-*`, `set-max-*`, `zset-max-*`, `list-max-*` 4가지로 분류 기억 |

---

## 8. 직접 해보기

1. 다섯 가지 자료형(String/List/Hash/Set/ZSET) 각각 작게 만들고 `OBJECT ENCODING` 확인.
2. 각 자료형의 임계값 옵션을 1로 낮춘 후 한 요소 추가 → 인코딩 전환 시점 관찰.
3. 같은 데이터 두 키에 대해 `MEMORY USAGE` 비교 (listpack vs hashtable).
4. 임계 옵션을 다시 큰 값으로 되돌렸을 때 기존 키의 인코딩이 "다시 바뀌나?" 확인 (안 바뀜 — 새 키부터 적용).

---

## 9. 참고 자료

- **[공식 문서] OBJECT ENCODING**
  - URL: <https://redis.io/docs/latest/commands/object-encoding/>
  - 참고 부분: 자료형별 가능 인코딩 목록 — §2 표 근거

- **[GitHub] redis/redis — redis.conf (8.6)**
  - URL: <https://github.com/redis/redis/blob/8.6/redis.conf>
  - 참고 부분: `hash-max-listpack-*`, `set-max-listpack-*`, `zset-max-listpack-*`, `list-max-listpack-size`, `set-max-intset-entries` 기본값 주석 — §2 임계값 근거

- **[GitHub] redis/redis — src/object.c (8.6)**
  - URL: <https://github.com/redis/redis/blob/8.6/src/object.c>
  - 참고 부분: `OBJ_ENCODING_EMBSTR_SIZE_LIMIT 44` 매크로 — §2.1 embstr 임계 근거
