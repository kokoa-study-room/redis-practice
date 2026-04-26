# 09. Query Caching — DB 쿼리 결과 캐싱

> **학습 목표**: DB 쿼리 결과를 Redis 에 캐싱하는 패턴, 무효화 전략 (TTL / 이벤트 기반 / write-through), 쿼리 키 설계와 cache key collision 방지를 익힌다.
> **예상 소요**: 25분

---

## 1. Cache-aside 와의 차이

| 측면 | Cache-aside (객체 단위) | Query caching (쿼리 단위) |
|---|---|---|
| 키 | `user:1234` (객체) | `q:hash(SQL)` (쿼리 결과) |
| 사용 케이스 | 단일 객체 GET | 복잡한 SQL JOIN / aggregate |
| 무효화 | 객체 변경 시 1키 | 쿼리 영향 받는 모든 캐시 키 |
| 메모리 사용 | 작음 (객체 1개씩) | 큼 (쿼리별 결과 셋) |

→ 두 패턴은 보통 **함께 사용**. 객체는 cache-aside, 무거운 집계 쿼리는 query caching.

---

## 2. 키 설계

```python
import hashlib, json

def query_cache_key(sql, params):
    payload = json.dumps([sql, params], sort_keys=True)
    h = hashlib.sha256(payload.encode()).hexdigest()
    return f"qc:{h}"
```

장점:
- SQL + params 의 SHA256 → unique key
- params 순서 무관 (sort_keys)

단점:
- 같은 쿼리 의도지만 SQL이 다르면 (대문자 / 공백) → 다른 캐시 키. **canonicalization 필요**.

---

## 3. 단순 구현

```python
import time, json

CACHE_TTL = 300

def query_cached(sql, params):
    key = query_cache_key(sql, params)
    cached = r.get(key)
    if cached:
        return json.loads(cached)
    
    rows = db.execute(sql, params).fetchall()
    rows_serializable = [dict(row) for row in rows]
    r.set(key, json.dumps(rows_serializable), ex=CACHE_TTL)
    return rows_serializable

# 사용
top_products = query_cached(
    "SELECT id, name FROM products WHERE category = %s ORDER BY rank LIMIT 10",
    ("electronics",)
)
```

---

## 4. TTL 만 사용 — 단순하지만 stale 가능

```python
CACHE_TTL = 300   # 5분

# product 테이블이 자주 변경되어도 5분간 stale
```

적합:
- top sellers, dashboard 같은 "약간 stale OK" 데이터
- read-heavy + 변경 드문

부적합:
- 가격 / 재고 / 주문 상태 같이 **정확성 중요**

---

## 5. 이벤트 기반 무효화 — 정확

DB write 시 관련 캐시 무효화.

### 5.1 단일 객체 변경 → 그 객체 + 관련 쿼리 무효화

```python
def update_product(product_id, data):
    db.update("products", product_id, data)
    
    # 해당 product 의 모든 query cache 무효화
    invalidate_pattern(f"qc:product:{product_id}:*")
```

문제: query cache 키는 SHA256 hash 라 product_id 와 직접 매핑 어려움.

### 5.2 Tag 기반 무효화

```python
def query_cached_with_tags(sql, params, tags):
    key = query_cache_key(sql, params)
    
    cached = r.get(key)
    if cached:
        return json.loads(cached)
    
    rows = db.execute(sql, params).fetchall()
    
    pipe = r.pipeline()
    pipe.set(key, json.dumps(rows), ex=CACHE_TTL)
    for tag in tags:
        pipe.sadd(f"qc:tag:{tag}", key)        # tag → cache key 들
        pipe.expire(f"qc:tag:{tag}", CACHE_TTL)
    pipe.execute()
    
    return rows

# 사용
products = query_cached_with_tags(
    "SELECT * FROM products WHERE category = %s",
    ("electronics",),
    tags=["product:category:electronics"]
)
```

무효화:
```python
def invalidate_tag(tag):
    keys = r.smembers(f"qc:tag:{tag}")
    if keys:
        r.delete(*keys)
    r.delete(f"qc:tag:{tag}")

def update_product(pid, data):
    db.update("products", pid, data)
    product = db.get_product(pid)
    invalidate_tag(f"product:category:{product['category']}")
    invalidate_tag(f"product:id:{pid}")
```

---

## 6. Write-through (캐시도 같이 업데이트)

```python
def update_product_writethrough(pid, data):
    db.update("products", pid, data)
    
    # 캐시 키 직접 업데이트 (가능한 경우)
    r.set(f"product:{pid}", json.dumps(data), ex=CACHE_TTL)
    
    # query cache 는 무효화
    invalidate_tag(f"product:category:{data['category']}")
```

장점: read-after-write 일관성 강함.
단점: write 비용 증가, 캐시-DB 불일치 가능 (트랜잭션 깨짐 시).

---

## 7. ORM 통합

### 7.1 SQLAlchemy + 데코레이터

```python
def cached_query(ttl=300, tags=None):
    def decorator(func):
        def wrapper(*args, **kwargs):
            key_payload = (func.__name__, args, sorted(kwargs.items()))
            key = "qc:" + hashlib.sha256(
                json.dumps(key_payload, default=str).encode()
            ).hexdigest()
            
            cached = r.get(key)
            if cached:
                return json.loads(cached)
            
            result = func(*args, **kwargs)
            
            pipe = r.pipeline()
            pipe.set(key, json.dumps(result, default=str), ex=ttl)
            for tag in (tags or []):
                pipe.sadd(f"qc:tag:{tag}", key)
                pipe.expire(f"qc:tag:{tag}", ttl)
            pipe.execute()
            
            return result
        return wrapper
    return decorator

@cached_query(ttl=600, tags=["products"])
def get_top_products(category, limit=10):
    return session.query(Product).filter_by(category=category).limit(limit).all()
```

### 7.2 Django low-level cache + Redis backend

Django 의 `cache.get` / `cache.set` 을 Redis backend 로 → ORM 결과 직접 캐싱.

---

## 8. 분산 lock — Cache stampede 방지

여러 워커가 동시에 같은 캐시 miss → 동시에 DB 호출.

해결: 09-patterns/01-cache-aside.md 의 락 패턴 참고. 또는 PROBABILISTIC EARLY REFRESH (XFetch).

---

## 9. 메모리 관리

```
maxmemory 4gb
maxmemory-policy allkeys-lru
```

→ 가득 차면 LRU 로 자동 evict. **query cache 는 크기 큰 응답이므로 maxmemory 모니터링 필수**.

```
INFO memory
INFO stats | grep evicted
```

evicted_keys 가 너무 많으면:
- maxmemory 증가
- TTL 단축
- top N 빈도 가장 높은 쿼리만 캐싱

---

## 10. 보안 — 캐시 키에 민감 정보

캐시 키에 사용자 ID 가 들어가면 다른 사용자 응답을 받을 가능성:
```python
# WRONG
key = query_cache_key("SELECT * FROM users WHERE id = %s", (user_id,))
# 모든 사용자가 다른 결과 → 캐시 효율 낮음
```

→ 사용자별 데이터는 보통 query cache 부적합. **공통 데이터** (top products, popular posts) 가 적합.

---

## 11. 측정 / 튜닝

```python
# 캐시 hit rate 추적
def query_cached_with_metrics(sql, params, tags=None):
    key = query_cache_key(sql, params)
    cached = r.get(key)
    if cached:
        r.incr("metrics:qc:hits")
        return json.loads(cached)
    r.incr("metrics:qc:misses")
    ...
```

```
hit_rate = hits / (hits + misses)
```

목표: 80%+ (캐시 효율 좋음). 50% 미만이면 TTL/대상 쿼리 재검토.

---

## 12. 흔한 함정

| 함정 | 설명 |
|---|---|
| SQL canonicalization 없음 | 대소문자 / 공백 차이로 키 분리 → cache miss 증가. |
| 사용자별 캐시 키 분리 안 함 | privacy 사고 (다른 사용자 데이터 반환). |
| Tag 무효화 누락 | DB 변경 후 stale 응답 영원. write 시 모든 영향 받는 tag invalidate. |
| 매우 큰 결과 캐싱 | 1MB+ 결과 → 메모리 폭증. LIMIT / pagination. |
| TTL 너무 김 | stale 길어짐. 데이터 변동성에 맞춤. |
| TTL 너무 짧음 | 효과 적음. trade-off 측정. |
| Cluster 에서 tag → key 매핑이 다른 슬롯 | hashtag 로 묶어야 한 노드. `{qc:tag:foo}` |

---

## 13. 직접 해보기

1. 단순 query cache 데코레이터 → hit/miss 측정.
2. Tag 기반 무효화 → DB write 후 관련 캐시 모두 사라지는지.
3. 1000번 동시 cache miss 시뮬 → DB 호출 횟수 (락 적용 vs 미적용).
4. maxmemory 작게 + 큰 쿼리 결과 캐싱 → eviction 발생.
5. ORM (SQLAlchemy) 데코레이터 통합.

---

## 14. 참고 자료

- **[Redis Solutions] Query caching** — <https://redis.io/solutions/query-caching-with-redis-enterprise/>
  - 참고 부분: 패턴 / 사용 사례 — §1, §11 근거

- **[공식 문서] Eviction policies** — <https://redis.io/docs/latest/operate/oss_and_stack/management/eviction/>
  - 참고 부분: allkeys-lru / maxmemory — §9 근거

- **[공식 문서] CLIENT TRACKING (server-assisted query cache invalidation)** — <https://redis.io/docs/latest/develop/reference/client-side-caching/>
  - 참고 부분: 더 진보된 패턴 — 08-clients/04 와 결합 가능
