# 01. 자료형 (Data Types)

> **이 챕터의 목표**: Redis가 제공하는 10개 자료형을 구분해서 쓸 수 있다. 각 자료형의 핵심 명령, Big-O, 흔한 함정, 어디에 좋은지 한 줄로 답할 수 있다.

---

## 자료형 한눈에 보기 (Cheat Sheet)

| # | 자료형 | 한 줄 정의 | 대표 사용처 | 주요 명령 |
|---|---|---|---|---|
| 01 | **String** | 바이트/숫자 1개 | 캐시, 카운터, 세션 토큰 | `SET`/`GET`/`INCR`/`APPEND` |
| 02 | **List** | 양방향 링크드 리스트 | 큐, 스택, 최근 N개 로그 | `LPUSH`/`RPOP`/`LRANGE`/`BLPOP` |
| 03 | **Hash** | field-value 맵 | 객체(사용자 프로필 등), 필드별 TTL (8.x+) | `HSET`/`HGETALL`/`HEXPIRE` |
| 04 | **Set** | 중복 없는 집합 | 태그, 친구 목록, 합/교/차 연산 | `SADD`/`SMEMBERS`/`SINTER` |
| 05 | **Sorted Set** | 점수 정렬된 집합 | 리더보드, 시간순 인덱스, 우선순위 큐 | `ZADD`/`ZRANGE`/`ZRANGEBYSCORE` |
| 06 | **Stream** | append-only 이벤트 로그 | Kafka-lite, 작업 큐 + Consumer Group | `XADD`/`XREAD`/`XREADGROUP` |
| 07 | **Bitmap** | 비트 배열 (String 기반) | 사용자별 출석 체크, 0/1 플래그 대량 | `SETBIT`/`GETBIT`/`BITCOUNT` |
| 08 | **HyperLogLog** | 고유값 카운트 추정 (오차 ~0.81%) | UV 카운트, 대규모 distinct count | `PFADD`/`PFCOUNT`/`PFMERGE` |
| 09 | **Geospatial** | 좌표 + 반경 검색 | 근처 매장 찾기, 위치 기반 추천 | `GEOADD`/`GEOSEARCH`/`GEODIST` |
| 10 | **Vector Set** | 벡터 + 유사도 검색 (8.x 신규) | RAG, 임베딩 검색 | `VADD`/`VSIM`/`VRANGE` |

> 출처: <https://redis.io/docs/latest/develop/data-types/>
> 참고 부분: 자료형 목록과 정의 — 본 표의 행 구성 근거

---

## 학습 순서

| # | 파일 | 핵심 |
|---|---|---|
| 01 | [01-string.md](01-string.md) | embstr / raw / int 인코딩, INCR 원자성 |
| 02 | [02-list.md](02-list.md) | quicklist + listpack, BLPOP 블로킹 |
| 03 | [03-hash.md](03-hash.md) | listpack ↔ hashtable, **field TTL (8.x)** |
| 04 | [04-set.md](04-set.md) | intset / listpack / hashtable, 집합 연산 |
| 05 | [05-sorted-set.md](05-sorted-set.md) | listpack ↔ skiplist+ht, range 쿼리 |
| 06 | [06-stream.md](06-stream.md) | rax 기반, Consumer Group, XADD IDMP (8.6) |
| 07 | [07-bitmap.md](07-bitmap.md) | String 위에 비트 연산 |
| 08 | [08-hyperloglog.md](08-hyperloglog.md) | sparse/dense 인코딩, ~12KB 고정 |
| 09 | [09-geospatial.md](09-geospatial.md) | Geohash + Sorted Set |
| 10 | [10-vector-set.md](10-vector-set.md) | HNSW, 양자화 (8.x 신규) |

---

## 자료형 선택 의사결정 트리

```
값이 단일?                 → String  (숫자면 INCR 가능, 그래도 String)
값이 순서있는 다수?        → List    (양 끝 push/pop, 인덱스 접근)
값이 키-필드 묶음?         → Hash    (객체 1개를 메모리 효율적으로)
값이 중복없는 집합?        → Set
점수로 정렬한 집합?        → Sorted Set (리더보드, 시간순 인덱스)
이벤트 로그/큐?            → Stream  (Pub/Sub의 영속 버전)
대량 0/1 플래그?           → Bitmap
대량 distinct 카운트?      → HyperLogLog
좌표 검색?                 → Geospatial
유사도 검색?               → Vector Set
```

---

## 모든 자료형 공통 — 키 관리

```
EXISTS k [k ...]           # 존재 개수
TYPE k                     # 자료형
OBJECT ENCODING k          # 내부 인코딩 (자료형별로 가능한 값이 다름)
TTL k / PTTL k             # 남은 만료 시간 (초/밀리초)
EXPIRE k <s>               # 초 단위 만료
PEXPIRE k <ms>             # 밀리초 단위
EXPIREAT k <unix-time>     # 절대 시각
PERSIST k                  # 만료 제거
RENAME k1 k2               # 이름 변경
COPY k1 k2 [DB n]          # 복사
DUMP k / RESTORE k         # 직렬화/복원 (마이그레이션)
DEL k [k ...] / UNLINK k   # 삭제 (UNLINK는 비동기)
```

> **`UNLINK` vs `DEL`**: 큰 키를 `DEL` 하면 단일 스레드라 그 시간만큼 멈춘다. `UNLINK` 는 백그라운드 삭제. 운영에서는 거의 항상 `UNLINK` 권장.
> 출처: <https://redis.io/docs/latest/commands/unlink/>

---

준비됐으면 [01-string.md](01-string.md) 부터 시작.
