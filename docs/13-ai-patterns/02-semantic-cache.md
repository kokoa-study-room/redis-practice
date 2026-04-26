# 02. Semantic Cache — 의미 기반 LLM 응답 캐싱

> **학습 목표**: 사용자 질문이 의미적으로 유사하면 이전 LLM 응답을 재사용해서 비용/지연을 줄이는 패턴을 Vector Set으로 직접 구현한다.
> **예상 소요**: 30분

---

## 1. 왜 일반 캐시로는 안 되나?

```
일반 캐시 (key=질문 문자열):
  Q1: "Redis가 뭐야?"        → cached
  Q2: "Redis 란 무엇인가요?"  → MISS (다른 문자열)
  Q3: "Redis  란 뭐야?"      → MISS (공백 차이)
```

→ **질문이 살짝만 달라도 cache miss**. LLM 호출 비용 / 지연 매번 발생.

**Semantic Cache** = "두 질문의 임베딩 거리가 임계 이하면 같은 답"

```
Q1 임베딩 vs Q2 임베딩 → cosine similarity 0.97 → HIT (같은 답 재사용)
Q1 임베딩 vs Q3 임베딩 → 0.99 → HIT
Q1 임베딩 vs "오늘 날씨" 임베딩 → 0.20 → MISS
```

> 출처: <https://redis.io/redis-for-ai/>
> 참고 부분: semantic caching 사용 사례

---

## 2. 자료 모델

```
sc:vec               # Vector Set (멤버 = cache_id, 벡터 = 질문 임베딩)
sc:resp:<cache_id>   # Hash (question, response, model, ts, hit_count)
```

---

## 3. Python 구현

```python
import time, uuid, redis
from sentence_transformers import SentenceTransformer

r = redis.Redis(decode_responses=True)
model = SentenceTransformer("all-MiniLM-L6-v2")
DIM = 384
SIMILARITY_THRESHOLD = 0.92   # 이 이상이면 같은 답 재사용
CACHE_TTL = 86400 * 7         # 7일

def cache_get(question):
    q_emb = model.encode(question)
    args = ["VSIM", "sc:vec", "VALUES", str(DIM)]
    args.extend(str(x) for x in q_emb)
    args.extend(["COUNT", "1", "WITHSCORES"])
    
    result = r.execute_command(*args)
    if not result:
        return None
    
    cache_id = result[0]
    score = float(result[1])
    if score < SIMILARITY_THRESHOLD:
        return None
    
    cached = r.hgetall(f"sc:resp:{cache_id}")
    r.hincrby(f"sc:resp:{cache_id}", "hit_count", 1)
    return cached.get("response")

def cache_set(question, response, model_name="gpt-4o-mini"):
    cache_id = str(uuid.uuid4())
    q_emb = model.encode(question)
    
    args = ["VADD", "sc:vec", "VALUES", str(DIM)]
    args.extend(str(x) for x in q_emb)
    args.append(cache_id)
    r.execute_command(*args)
    
    r.hset(f"sc:resp:{cache_id}", mapping={
        "question": question,
        "response": response,
        "model": model_name,
        "ts": int(time.time()),
        "hit_count": 0,
    })
    r.expire(f"sc:resp:{cache_id}", CACHE_TTL)

def ask(question):
    cached = cache_get(question)
    if cached:
        print("[CACHE HIT]")
        return cached
    
    print("[CACHE MISS] LLM 호출 중...")
    response = call_llm(question)   # OpenAI / Anthropic 호출
    cache_set(question, response)
    return response

# 시연
print(ask("Redis가 뭐야?"))                    # MISS
print(ask("Redis란 무엇인가요?"))              # HIT (의미 유사)
print(ask("오늘 서울 날씨 어때?"))             # MISS (다른 주제)
```

---

## 4. 임계값 (threshold) 튜닝

| threshold | 효과 |
|---|---|
| 0.99 | 거의 같은 질문만 hit (재사용률 낮음, 정확도 높음) |
| 0.95 | 적절한 trade-off (대부분 RAG / 일반 챗봇) |
| 0.90 | 광범위 매칭 (요약 / 분류 등 대범한 응답에 적합) |
| 0.80 | 너무 광범위 — 다른 의도까지 매칭 가능 |

→ **워크로드별 측정 필수**. test set으로 precision / recall.

---

## 5. 무효화 (Invalidation)

응답이 시간이 지나면 stale:
- TTL (위 예제: 7일)
- 외부 이벤트 (DB 변경) → 관련 cache_id 삭제
- 사용자가 "더 정확한 답 다시" → cache 우회 (force_refresh 플래그)

```python
def invalidate_by_topic(topic_keyword):
    """topic 관련 캐시 모두 삭제 (간단 패턴 매칭)"""
    # cache_id 들 순회
    cursor = 0
    while True:
        cursor, keys = r.scan(cursor, match="sc:resp:*", count=100)
        for key in keys:
            q = r.hget(key, "question") or ""
            if topic_keyword in q:
                cache_id = key.split(":")[-1]
                r.execute_command("VREM", "sc:vec", cache_id)
                r.delete(key)
        if cursor == 0:
            break
```

---

## 6. Vector Set 메모리 관리

캐시가 무한히 자라지 않게:

### 6.1 LRU-like (hit_count + ts 기반)

주기적으로 가장 오래/적게 쓴 항목 제거:
```python
def evict_lru(target_size=10000):
    current = int(r.execute_command("VCARD", "sc:vec"))
    if current <= target_size:
        return
    
    # 모든 cache_id 의 (hit_count, ts) 수집 후 정렬
    # 작은 hit_count + 오래된 ts 제거
    # ... (단순화)
```

### 6.2 TTL 기반
TTL 만료 시 Hash는 자동 삭제. 단 Vector Set 은 멤버가 그대로 → 주기적으로 비고아 cleanup.

```python
def cleanup_orphans():
    cursor = "0"
    while True:
        # VSCAN 같은 명령은 없음 → VRANGE 로 전체 순회 (작은 셋만)
        # 또는 별도로 cache_id 의 set 키 유지
        ...
```

→ Vector Set 의 멤버 수가 너무 커지지 않게 LRU + 정기 evict.

---

## 7. 비용 절감 추정

LLM 호출 비용 / 지연:
- GPT-4o-mini: ~$0.15 / 1M tokens, ~500ms
- Claude Haiku: 유사 가격

캐시 hit 비용:
- VSIM 1개: ~수 ms
- HGETALL: ~1ms

→ **hit rate 50%** 면 LLM 호출 절반 → 비용 50%, 평균 latency 1/3 (cache hit는 빠름).

---

## 8. 보안 / 프라이버시 고려

- **개인 정보 포함 질문**: 다른 사용자에게 cache hit 되면 누설.
  - 해결: 사용자별 namespace (`sc:vec:user:1234`)
  - 또는 PII 제거 후 임베딩
- **로깅**: 질문 / 응답 보관 → 정책 준수 (GDPR 등) 확인

---

## 9. semantic cache + RAG 결합

```
질문 → semantic cache HIT? 
  Yes → 응답 즉시 반환
  No  → RAG (유사 문서 검색 + LLM) → 응답 → cache set
```

이 조합이 production LLM 앱의 표준 패턴.

---

## 10. RedisVL SemanticCache

```python
from redisvl.extensions.cache.llm import SemanticCache

cache = SemanticCache(
    name="my_llmcache",
    redis_url="redis://localhost:6379",
    distance_threshold=0.1,
)

# Get
match = cache.check("Redis가 뭐야?")
if match:
    print(match[0]["response"])

# Set
cache.store("Redis가 뭐야?", "Redis는 인메모리 데이터 구조 서버...")
```

> 출처: <https://github.com/redis/redis-vl-python>
> RedisVL 의 `SemanticCache` 가 위 §3 의 패턴을 추상화.

---

## 11. 흔한 함정

| 함정 | 설명 |
|---|---|
| threshold 너무 낮음 | 다른 의도까지 매칭 → 잘못된 답. 0.92~0.95 권장. |
| chunked context 무시 | 같은 질문이라도 RAG context 가 다르면 답이 달라야 할 수 있음. |
| 사용자별 분리 안 함 | privacy 누설. namespace 분리. |
| TTL 없음 | 영원히 stale. 7~30일 TTL 권장. |
| 너무 큰 Vector Set | 검색 시간 증가. 정기 evict. |
| 임베딩 모델 변경 후 기존 캐시 사용 | 차원/거리 의미 바뀜. 모델 변경 시 cache flush. |

---

## 12. 직접 해보기

1. 30개 다른 phrasing 의 같은 질문 (예: "Redis 가 뭐야?", "what is Redis?", "Redis란?") → hit/miss 매트릭스.
2. threshold 0.85 / 0.92 / 0.97 → hit rate 변화.
3. hit_count 가 가장 높은 캐시 항목 출력 (인기 질문 분석).
4. user 별 namespace 적용.
5. (도전) RedisVL SemanticCache 와 raw 구현 비교.

---

## 13. 참고 자료

- **[Redis For AI] Semantic Cache** — <https://redis.io/redis-for-ai/>
  - 참고 부분: semantic caching 사용 사례 — §1 근거

- **[Redis Tutorial] Semantic caching with Redis LangCache** — <https://redis.io/tutorials/semantic-caching-with-redis-langcache/>
  - 참고 부분: LangCache 통합 / threshold 튜닝 — §4 근거

- **[GitHub] redis/redis-vl-python — SemanticCache** — <https://github.com/redis/redis-vl-python>
  - 참고 부분: SemanticCache extension — §10 근거

- **[공식 문서] Vector Sets** — <https://redis.io/docs/latest/develop/data-types/vector-sets/>
  - 참고 부분: VADD / VSIM — §3 근거
