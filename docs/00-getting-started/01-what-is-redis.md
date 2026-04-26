# 01. Redis란? — 왜 빠르고, 언제 쓰면 안 되는가

> **학습 목표**: Redis의 정체를 한 문장으로 정의하고, "왜 빠른가"의 핵심 이유 3가지와 "쓰면 안 되는 경우"를 댈 수 있다.
> **사전 지식**: 키-값 저장소 개념, 프로세스/스레드 차이
> **예상 소요**: 15분

---

## 1. 개념 (Concept)

**Redis** (REmote DIctionary Server)는 **인메모리(in-memory) 데이터 구조 서버 (data structure server)** 이다.
"키-값 저장소"라는 표현이 자주 쓰이지만, 이는 절반의 진실이다. Redis의 진짜 매력은 **값(value)의 자료형이 풍부**하다는 데 있다.

```
Memcached    : KEY → STRING               (값은 그냥 바이트 덩어리)
Redis        : KEY → STRING / LIST / HASH / SET / SORTED SET /
                     STREAM / BITMAP / HYPERLOGLOG / GEO / VECTOR SET
```

> 출처: <https://redis.io/docs/latest/develop/data-types/>
> 참고 부분: "Redis is an open source (BSD licensed), in-memory data structure store" 정의 + 자료형 목록

---

## 2. 왜 빠른가 (Why is it fast?)

### 2.1 인메모리 (In-memory)

모든 데이터를 RAM에 둔다. 디스크 I/O가 정상 경로에서 발생하지 않는다.
디스크는 영속성(persistence) 용으로만 쓰인다 (RDB 스냅샷, AOF 로그 — Phase 5에서 다룸).

| 매체 | 일반적 지연(latency) |
|---|---|
| L1 cache | ~0.5 ns |
| RAM | ~100 ns |
| SSD random read | ~25 µs (= 25,000 ns) |
| HDD seek | ~10 ms (= 10,000,000 ns) |

> 출처: <https://gist.github.com/jboner/2841832> ("Latency Numbers Every Programmer Should Know") — 본 표의 자릿수는 이 자료의 일반 합의 수치를 인용

### 2.2 단일 스레드 이벤트 루프 (Single-threaded event loop)

전통적 의미의 단일 스레드 명령 처리. (Redis 6+ 부터는 네트워크 I/O를 멀티스레드로 분리할 수 있는 옵션이 있지만, **명령 실행 자체는 여전히 단일 스레드**다.)

장점:
- **락(lock) 경쟁 없음**: 자료구조 내부 자체에 동시성 제어 로직이 필요 없다.
- **컨텍스트 스위칭 비용 없음**.
- **모든 명령이 사실상 원자적 (atomic)**: `INCR`, `LPUSH` 같은 명령이 중간에 끊기지 않는다.

함정:
- 한 번에 무거운 명령(`KEYS *`, 큰 `LRANGE 0 -1`) 하나가 들어오면 **전체 서버가 그 시간만큼 멈춘다**.
- 따라서 Redis에서는 "느린 명령을 쓰지 않는 능력"이 곧 운영 실력이다.

> 출처: <https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/cpu-profiling/>
> 참고 부분: "Redis is, mostly, a single-threaded server from the POV of commands execution" — 본 단락의 단일 스레드 정의는 이 문서 첫 단락 인용

### 2.3 효율적인 자료구조 (Efficient data structures)

같은 자료형이라도 크기에 따라 내부 인코딩(internal encoding)을 바꾼다.

```
HASH (작음)  → listpack   : 평면 바이트 배열, 캐시 친화적
HASH (큼)    → hashtable  : O(1) 룩업
SORTED SET   → listpack 또는 skiplist + hashtable 조합
```

이 의사결정을 자동으로 해주기 때문에 학습자는 외부 자료형(String/Hash/...)만 신경 쓰면 된다.
**왜 빠른가**의 핵심은 여기서 나온다 — 02-internals 챕터에서 깊게 다룬다.

> 출처: <https://redis.io/docs/latest/commands/object-encoding/>
> 참고 부분: "Returns the internal encoding for the Redis object stored at <key>" + 인코딩 목록

---

## 3. 비공식 한 줄 정의

> **"디스크 대신 RAM에 자료구조를 두고, 단일 스레드로 락 없이 처리하는 풍부한 자료형 서버."**

---

## 4. Redis가 잘하는 일 vs. 잘 못 하는 일

### 잘하는 일 ✅

| 패턴 | 예 |
|---|---|
| 캐시 | DB 쿼리 결과 / 세션 / 토큰 |
| 카운터 | 좋아요 수 / 방문자 수 (`INCR`) |
| 랭킹 | 게임 리더보드 (`ZSET`) |
| 큐 / 작업 분배 | Pub/Sub, Stream + Consumer Group |
| 분산 락 | `SET NX EX` |
| 실시간 분석 | HyperLogLog (UV 추정), BITFIELD |
| 지오 | GEORADIUS 기반 근처 검색 |
| 벡터 검색 | Vector Set (8.x 신규) / RediSearch |

### 잘 못 하는 일 ❌

| 상황 | 이유 |
|---|---|
| 데이터셋이 RAM보다 큼 | 인메모리 전제 깨짐. 일부 캐시 패턴은 가능하지만 "DB 대체"는 무리. |
| 복잡한 다중 테이블 조인 / 트랜잭션 ACID | RDBMS의 영역. Redis의 트랜잭션은 "묶음 실행"이지 일반적 ACID가 아님. |
| 풀텍스트 검색 (모듈 없이) | RediSearch 모듈을 쓸 게 아니면 Elasticsearch가 적합. |
| 영속성이 절대 깨지면 안 되는 금융 원장 | RDB는 주기 손실 가능, AOF도 fsync 정책에 따라 1초까지 손실. PostgreSQL 등 권장. |

> 출처: <https://redis.io/docs/latest/develop/get-started/data-store/>
> 참고 부분: "Redis is a data structure server. It excels at caching, real-time analytics..." — 위 표의 잘하는 일 목록의 근거

---

## 5. 흔한 함정 (Pitfalls)

| 함정 | 설명 |
|---|---|
| **`KEYS *` 사용** | O(N) 명령. 운영에서 절대 금지. `SCAN` 사용. |
| **무한 LPUSH** | TTL 없이 큐에만 push 하면 RAM 폭증. |
| **단일 큰 키 (Big Key)** | 한 키에 GB 단위 List/Hash. 만료/삭제 시 서버 멈춤. |
| **TTL 미설정 캐시** | 메모리 가득 → eviction policy 의존 → 의도치 않은 키 손실 |
| **외부 노출 + 무인증** | "최근 Redis 침해 사고"의 단골. 학습 환경도 `127.0.0.1` 바인드 권장. |

---

## 6. 용어 정리

| 한국어 | 영어 | 의미 |
|---|---|---|
| 인메모리 | in-memory | RAM에만 데이터를 둠 |
| 자료형 | data type / structure | String, List 등 외부 자료형 |
| 인코딩 | encoding | 같은 자료형의 내부 저장 방식 (listpack 등) |
| 영속성 | persistence | 디스크에 보존 (RDB / AOF) |
| 복제 | replication | master → replica 동기화 |
| 슬롯 | slot | Cluster의 16384개 키 분배 단위 |
| 만료 | TTL / expire | 키에 시간 제한 부여 |

---

## 7. 직접 해보기 (실습 과제)

다음 챕터로 넘어가기 전에:

1. 위 "Redis가 잘 못 하는 일" 4가지 중 본인이 가장 의외였던 것 한 줄 메모.
2. 본인의 직전 프로젝트에서 Redis로 대체할 만한 후보(쿼리/구조)를 1개 찾아본다.

---

## 8. 참고 자료 (References)

- **[공식 문서] Introduction to Redis — redis.io**
  - URL: <https://redis.io/docs/latest/develop/get-started/data-store/>
  - 참고 부분: "Redis is a data structure server" 정의 + "잘하는 일" 목록 — 본 문서의 §1, §4 작성 근거

- **[공식 문서] OBJECT ENCODING — redis.io**
  - URL: <https://redis.io/docs/latest/commands/object-encoding/>
  - 참고 부분: 인코딩 목록 (listpack, hashtable, skiplist 등) — §2.3의 인코딩 자동 전환 설명 근거

- **[공식 문서] CPU Profiling — redis.io**
  - URL: <https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/cpu-profiling/>
  - 참고 부분: "Redis is, mostly, a single-threaded server" 단락 — §2.2 단일 스레드 정의 근거

- **[공식 블로그] Announcing Redis 8.6**
  - URL: <https://redis.io/blog/announcing-redis-86-performance-improvements-streams/>
  - 참고 부분: 8.6의 성능 개선·신기능 설명 — 본 프로젝트의 8.6 기준 채택 근거

- **[일반 자료] Latency Numbers Every Programmer Should Know — Jonas Bonér**
  - URL: <https://gist.github.com/jboner/2841832>
  - 참고 부분: RAM ~100ns, SSD ~25µs, HDD seek ~10ms — §2.1 표의 자릿수 인용
