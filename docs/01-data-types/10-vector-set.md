# 10. Vector Set (Redis 8.x 신규)

> **학습 목표**: Vector Set이 Redis 8.x에 추가된 native 자료형이며, HNSW 기반 유사도 검색을 외부 모듈 없이 OSS에서 쓸 수 있다는 점을 이해하고, RAG / 임베딩 검색에 사용할 수 있다.
> **예상 소요**: 30분

---

## 1. 개념

> **"문자열 멤버 + 그에 연관된 벡터(부동소수점 배열) 의 집합. 새 벡터로 가장 유사한 멤버를 찾는다."**

```
key = "movie-embeddings"
  "Inception"          → [0.12, -0.43, 0.88, ...]   (예: 768차원)
  "Interstellar"       → [0.15, -0.40, 0.91, ...]
  "The Dark Knight"    → [-0.05, 0.33, 0.50, ...]

VSIM movie-embeddings VALUES 768 0.13 -0.42 0.89 ...
→ ["Inception", "Interstellar", "The Dark Knight"]   ← 코사인 유사도 순
```

내부적으로 **HNSW** (Hierarchical Navigable Small World) 인덱스 + **양자화 옵션**.

용도:
- **RAG** (Retrieval Augmented Generation) — 임베딩 → 문서 후보
- **추천** — 유사 콘텐츠
- **이미지/영상 검색** — 임베딩 모델 출력
- **클러스터링 / 유사 사용자 찾기**

> 출처: <https://redis.io/docs/latest/develop/data-types/vector-sets/> (Redis 8.x 추가 자료형)
> 출처 (8.6 SIMD 최적화): <https://github.com/redis/redis/releases/tag/8.6.0> "Vector set: vectorized binary quantization path" 등

---

## 2. 기본 사용법

```
# 추가
VADD <key> [REDUCE <dim>] [CAS] [NOQUANT|Q8|BIN] VALUES <dim> <v0> <v1> ... <member>
#   - REDUCE n      : 차원 축소 (random projection)
#   - CAS           : Check-And-Set (멤버가 이미 있으면 update only)
#   - NOQUANT/Q8/BIN: 양자화 안 함 / 8-bit / 1-bit (메모리 절약)

VADD movies VALUES 4 0.1 0.2 0.3 0.4 "Inception"
VADD movies VALUES 4 0.15 0.18 0.32 0.41 "Interstellar"
VADD movies VALUES 4 -0.05 0.33 0.50 0.20 "The Dark Knight"

# 카드 (멤버 수)
VCARD movies                 # 3

# 차원 (벡터 차원)
VDIM movies                  # 4

# 멤버의 벡터 가져오기
VEMB movies "Inception"      # 1) "0.1" 2) "0.2" ...

# 유사도 검색 (가장 자주 쓰는 명령)
VSIM movies VALUES 4 0.12 0.21 0.31 0.40
# → 가까운 순으로 멤버

# 옵션
VSIM movies VALUES 4 0.12 0.21 0.31 0.40 COUNT 5     # 5개만
VSIM movies VALUES 4 0.12 0.21 0.31 0.40 WITHSCORES  # 점수 함께
VSIM movies ELE "Inception" COUNT 5                  # 멤버 기준 검색

# 범위 조회 (ID 순; Redis 8.6+ node-redis 5.11에 추가된 VRANGE)
VRANGE movies 0 -1 WITHSCORES

# 메타 정보
VINFO movies                 # 인덱스 통계 / 양자화 / 차원

# 삭제
VREM movies "Inception"
```

> 출처 (VRANGE): <https://github.com/redis/node-redis/releases/tag/redis%405.11.0> "add VRANGE command for vector sets"

---

## 3. 클라이언트 코드 예제

### Python — 임베딩 + 검색

```python
import redis
import random

r = redis.Redis()

# 4차원 더미 벡터 (실전에서는 sentence-transformers, OpenAI embeddings 등에서 생성)
movies = {
    "Inception":       [0.10, 0.20, 0.30, 0.40],
    "Interstellar":    [0.15, 0.18, 0.32, 0.41],
    "The Dark Knight": [-0.05, 0.33, 0.50, 0.20],
}

for title, vec in movies.items():
    # raw 명령 사용 (redis-py 7.4 기준 VADD 헬퍼는 클라이언트 버전 따라 다름)
    args = ["VADD", "movies", "VALUES", str(len(vec))] + [str(x) for x in vec] + [title]
    r.execute_command(*args)

# 검색
query = [0.12, 0.21, 0.31, 0.40]
res = r.execute_command(
    "VSIM", "movies", "VALUES", str(len(query)), *map(str, query),
    "COUNT", "3", "WITHSCORES"
)
print(res)
# [b'Inception', b'0.998...', b'Interstellar', b'0.996...', b'The Dark Knight', b'0.45...']
```

> 클라이언트 라이브러리에서 Vector Set 명령에 대한 **고수준 헬퍼**가 정착되는 중이라, 위처럼 `execute_command` 가 가장 안정적. 버전 업데이트와 함께 점진적으로 `r.vadd(...)` 같은 메서드가 추가될 예정.

### Node.js (node-redis 5.12 — VRANGE 헬퍼 명시)

```javascript
import { createClient } from "redis";
const r = createClient(); await r.connect();

await r.sendCommand(["VADD", "movies", "VALUES", "4", "0.10", "0.20", "0.30", "0.40", "Inception"]);
await r.sendCommand(["VADD", "movies", "VALUES", "4", "0.15", "0.18", "0.32", "0.41", "Interstellar"]);

const result = await r.sendCommand([
  "VSIM", "movies", "VALUES", "4", "0.12", "0.21", "0.31", "0.40",
  "COUNT", "3", "WITHSCORES"
]);

console.log(result);
```

---

## 4. 내부 동작

### 4.1 인덱스 — HNSW

> **HNSW (Hierarchical Navigable Small World)**
> 다층 그래프. 상위층은 sparse, 하위층은 dense. 검색 시 위층에서 빠르게 영역 좁힌 뒤 아래로 내려가며 정밀 탐색.
> 일반적으로 **검색 O(log N)**, 메모리 트레이드오프.

### 4.2 양자화 (Quantization)

| 옵션 | 메모리/속도 | 정확도 |
|---|---|---|
| `NOQUANT` | 가장 큼 / 가장 정확 | 100% |
| `Q8` (8-bit) | ~4배 절약 | 미세 손실 |
| `BIN` (1-bit) | 32배 절약 | 큰 손실 (대량 후보 빠른 필터링용) |

Redis 8.6 에서 SIMD(AVX/AVX2) 최적화 추가:
- 8-bit 양자화 거리 계산 벡터화 (Intel/AMD)
- 1-bit popcount AVX2/ARM NEON
- 출처: <https://github.com/redis/redis/releases/tag/8.6.0> "Performance and resource utilization improvements"

### 4.3 Big-O

| 명령 | 복잡도 |
|---|---|
| `VADD` | 평균 O(log N) (HNSW 삽입) |
| `VSIM` | 평균 O(log N + k) k=COUNT |
| `VREM` | O(log N) |
| `VEMB / VINFO` | O(1) |

---

## 5. 흔한 함정

| 함정 | 설명 |
|---|---|
| **차원 불일치** | `VADD` 한 차원과 다른 `VSIM` 호출 → 에러. `VDIM`으로 확인. |
| **임베딩 정규화 안 함** | 일부 거리 함수는 정규화 가정. 모델 문서 확인 후 normalize. |
| **양자화 모드 무지성 사용** | BIN으로는 미세한 차이 분간 못 함. 추천 시스템에선 NOQUANT/Q8 권장. |
| **클라이언트 헬퍼 부재** | 신규 명령이라 라이브러리 헬퍼 미숙. `execute_command`/`sendCommand` 직접 호출 필요할 수 있음. |
| **8.x 미만에서 사용 시도** | 자료형 자체가 없음. `redis_version` 확인. |

---

## 6. RediSearch + RedisJSON과의 차이

| 항목 | Vector Set (OSS 8.x) | RediSearch + 벡터 인덱스 |
|---|---|---|
| 외부 모듈 필요 | ❌ (OSS native) | ✅ |
| 메타데이터 필터링 (예: WHERE category="horror") | 단일 자료형이라 어려움 | ✅ FT.SEARCH로 풍부 |
| 인덱스 종류 | HNSW만 | HNSW / FLAT |
| 학습 난이도 | 낮음 | 높음 (FT.CREATE/FT.SEARCH 문법) |
| 적합한 상황 | "벡터만 빠르게 비교" | "벡터 + 메타데이터 풍부 검색" |

---

## 7. 직접 해보기

1. 4차원 더미 벡터로 5개 멤버 VADD → VSIM으로 가장 가까운 3개.
2. 같은 데이터를 `Q8` 옵션으로 다시 만들고 `VINFO` 로 메모리 차이 확인.
3. `VEMB` 로 저장된 벡터를 가져와서 원래 입력과 비교 (양자화 시 약간 다름).
4. (도전) sentence-transformers 등으로 한국어 문장 임베딩 100개 만들어 VADD → 의미가 비슷한 문장이 가깝게 나오는지.

---

## 8. 참고 자료

- **[공식 문서] Vector Sets**
  - URL: <https://redis.io/docs/latest/develop/data-types/vector-sets/>
  - 참고 부분: 자료형 정의 + HNSW 사용 — §1, §4.1 근거

- **[GitHub] redis/redis 8.6.0 release notes**
  - URL: <https://github.com/redis/redis/releases/tag/8.6.0>
  - 참고 부분: "Vector set: vectorized binary quantization path", "vectorized 8-bit vector distance" — §4.2 SIMD 최적화 근거

- **[GitHub] redis/node-redis 5.11.0 release notes**
  - URL: <https://github.com/redis/node-redis/releases/tag/redis%405.11.0>
  - 참고 부분: "feat(client): add VRANGE command for vector sets" — §2 VRANGE 가용성 근거

- **[논문] HNSW Original Paper — Malkov & Yashunin, 2018**
  - URL: <https://arxiv.org/abs/1603.09320>
  - 참고 부분: 알고리즘 개요 — §4.1 HNSW 동작 원리 근거
