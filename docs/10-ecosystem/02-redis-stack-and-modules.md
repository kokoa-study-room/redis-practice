# 02. Redis Stack & 모듈 (RediSearch / RedisJSON 등)

> **학습 목표**: Redis Stack의 위상, 8.x에서 OSS에 흡수된 모듈들, 각 모듈의 핵심 기능, "언제 OSS Redis 로 충분하고 언제 Stack/모듈이 필요한가".
> **예상 소요**: 25분

---

## 1. 모듈 시스템

Redis는 **공유 라이브러리(.so)** 를 동적으로 로드해서 새 명령 / 자료형 추가 가능.

```
loadmodule /path/to/redisearch.so
```

또는 redis.conf 시작 시.

대표 모듈 (구 Redis Stack 묶음):
- **RediSearch** — 풀텍스트 검색 + 벡터 인덱스 (HNSW/FLAT) + 보조 쿼리
- **RedisJSON** — JSON 자료형 + JSONPath
- **RedisTimeSeries** — 시계열 + 자동 다운샘플
- **RedisBloom** — Bloom / Cuckoo / Top-K / t-digest / Count-Min Sketch

> 출처: <https://redis.io/docs/latest/develop/reference/modules/>

---

## 2. Redis 8.x — 모듈의 OSS 흡수

> Redis 8 부터 위 모듈들의 핵심 기능이 **OSS 본체에 흡수** 되어, 별도 모듈 로드 없이 사용 가능.

| 기능 | Redis 7.x | Redis 8.x |
|---|---|---|
| Vector 검색 (Vector Set) | RediSearch 모듈 | OSS native (`VADD/VSIM`) |
| JSON | RedisJSON 모듈 | (8.x에서 통합 진행) |
| TimeSeries | 모듈 | 일부 통합 |
| Bloom 등 확률적 | 모듈 | 일부 통합 |

> 자세한 통합 범위는 redis_version 별로 다름. INFO modules / CONFIG GET 으로 실제 가용성 확인.

---

## 3. Redis Stack — 통합 배포판

```bash
docker run -p 6379:6379 redis/redis-stack:latest
```

특징:
- Redis OSS + 위 4개 모듈을 함께 묶은 배포판
- 호환성 / 마이그레이션 용으로 여전히 유용
- 8.x 흡수가 진행되면서 Stack의 차별화는 점차 줄어드는 중

---

## 4. 각 모듈 짧게

### 4.1 RediSearch — 풀텍스트 + 벡터

```
FT.CREATE myidx ON HASH PREFIX 1 doc: SCHEMA \
    title TEXT WEIGHT 5.0 \
    body TEXT \
    tags TAG \
    embedding VECTOR HNSW 6 TYPE FLOAT32 DIM 768 DISTANCE_METRIC COSINE

FT.SEARCH myidx "@title:redis @tags:{db}"
FT.SEARCH myidx "*=>[KNN 5 @embedding $vec AS score]" PARAMS 2 vec "..."
```

- BM25 / TF-IDF 스코어링
- 다중 필드 인덱스
- 벡터 인덱스 (HNSW, FLAT)
- Aggregations / GROUPBY

> Vector Set이 OSS에 들어왔지만 **메타데이터 필터링** 이 풍부한 검색은 RediSearch가 강함.

### 4.2 RedisJSON — JSON 자료형

```
JSON.SET user:1 '$' '{"name":"Kim","tags":["a","b"]}'
JSON.GET user:1 '$.tags[0]'
JSON.ARRAPPEND user:1 '$.tags' '"c"'
JSON.NUMINCRBY user:1 '$.age' 1
```

- JSONPath
- 부분 수정 (Hash보다 깊은 nested 가능)
- RediSearch와 결합 → JSON 필드 인덱싱

### 4.3 RedisTimeSeries

```
TS.CREATE temperature LABELS sensor 1 location seoul
TS.ADD temperature * 23.5
TS.RANGE temperature - + AGGREGATION avg 60000
```

- 시계열 자동 다운샘플
- 라벨 기반 다중 시리즈
- Prometheus 비슷한 쿼리

### 4.4 RedisBloom

```
BF.RESERVE myfilter 0.01 1000000     # 100만 원소, 오차 1%
BF.ADD myfilter "user-1"
BF.EXISTS myfilter "user-1"          # 1 (또는 false positive)

CF.ADD cuckoo "x"
CF.DEL cuckoo "x"

TOPK.RESERVE topk 10 2000 7 0.9
TOPK.ADD topk "search-term"
TOPK.LIST topk
```

- Bloom: 가입 여부 빠른 확률적 체크
- Cuckoo: Bloom + 삭제 가능
- Top-K: 가장 빈번한 N개
- Count-Min Sketch: 빈도 추정

---

## 5. 언제 모듈/Stack을 써야 하나?

| 상황 | OSS 8.x 충분 | 모듈/Stack 필요 |
|---|---|---|
| 캐시 / 세션 / 큐 | ✅ | — |
| 단순 벡터 검색 | ✅ (Vector Set) | — |
| 복잡한 풀텍스트 + 벡터 + 메타데이터 필터 | △ | **RediSearch** |
| 깊은 JSON 객체 수정 | △ (Hash + JSON 직렬화) | **RedisJSON** |
| 시계열 + 자동 집계 | △ (Stream) | **RedisTimeSeries** |
| 대규모 dedup (1억+) | △ (HyperLogLog로 카운트만) | **RedisBloom** |

---

## 6. Cluster에서 모듈 사용

대부분 모듈은 cluster mode 지원하지만 일부 명령은 **단일 슬롯 강제** (hashtag).

---

## 7. 흔한 함정

| 함정 | 설명 |
|---|---|
| 모듈 동작이 Redis OSS와 같다고 가정 | 일부 명령은 DUMP/RESTORE 호환 안 됨 (모듈 자료형) |
| 8.x로 올라가면 모듈 자동 흡수 | 흡수된 일부 기능만. 풀 기능은 별도 모듈 필요할 수도 |
| Valkey는 RediSearch 없음 | Valkey 자체 검색 모듈 / 포크 사용 |
| Stack 이미지가 모든 기능 최신 | Stack의 모듈 버전이 한 박자 늦을 수 있음 |

---

## 8. 직접 해보기

1. `docker run -p 6380:6379 redis/redis-stack:latest` → 별도 컨테이너로.
2. `FT.CREATE` 로 인덱스 + `FT.SEARCH` 실험.
3. `JSON.SET / JSON.GET / JSON.NUMINCRBY` 로 nested JSON 조작.
4. RedisInsight에서 Stack 인스턴스에 연결 → JSON / Search 탭.
5. OSS 8.x에서 같은 기능을 Vector Set / Hash로 재현 (어디까지 되는지).

---

## 9. 참고 자료

- **[공식 문서] Redis Modules**
  - URL: <https://redis.io/docs/latest/develop/reference/modules/>
  - 참고 부분: 모듈 시스템 — §1 근거

- **[공식 문서] RediSearch / RedisJSON / RedisTimeSeries / RedisBloom**
  - URL: <https://redis.io/docs/latest/develop/interact/search-and-query/>
  - 참고 부분: 각 모듈 명령 — §4 근거

- **[GitHub] RediSearch / RedisJSON / RedisTimeSeries / RedisBloom**
  - URL: <https://github.com/RediSearch/RediSearch>, etc.
  - 참고 부분: 최신 릴리즈 노트 — 버전 / 기능 근거

- **[공식 발표] Redis 8 GA — modules absorbed**
  - URL: <https://redis.io/blog/announcing-redis-86-performance-improvements-streams/>
  - 참고 부분: "Vector set: ..." 섹션 — §2 근거
