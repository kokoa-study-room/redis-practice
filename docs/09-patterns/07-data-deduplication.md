# 07. Data Deduplication (데이터 중복 제거)

> **학습 목표**: "이미 본 ID/이벤트인가?"를 빠르게 판단하는 4가지 자료형(Set / Bitmap / HyperLogLog / Bloom Filter)의 trade-off를 익히고 적합한 것을 선택할 수 있다.
> **예상 소요**: 25분

---

## 1. 문제

다음 중 하나:
- **이벤트 dedup**: 같은 event_id 가 두 번 들어왔는지 체크 (idempotency)
- **사용자 unique 카운트**: DAU / MAU 계산
- **URL 크롤링 중복 방지**: 이미 본 URL 인지
- **Spam dedup**: 같은 메시지 중복 발송 방지

→ 핵심 질문 두 가지:
1. **정확한 멤버 검사** 필요? (yes → Set / Bloom)
2. **숫자만** 필요? (yes → HyperLogLog / Bitmap)

---

## 2. 4가지 옵션 비교

| 자료형 | 메모리 (1억 원소) | 정확도 | 멤버 조회 | 카운트 |
|---|---|---|---|---|
| Set | ~수 GB | 100% | O(1) | O(1) (SCARD) |
| Bitmap | 12.5 MB | 100% | O(1) | O(N) (BITCOUNT) |
| HyperLogLog | 12 KB (고정) | ~99.19% (오차 0.81%) | ❌ (카운트만) | O(1) |
| Bloom Filter | ~수십 MB (조정) | False positive 가능, no false negative | O(K hash) | 별도 |

> 출처: <https://redis.io/solutions/deduplication/>

---

## 3. 옵션별 적합 시나리오

### 3.1 Set — "정확한 멤버 검사 + 작은 규모"

```python
def is_processed(event_id):
    """이미 처리한 이벤트인가?"""
    return r.sismember("processed:events", event_id) == 1

def mark_processed(event_id, ttl_sec=86400):
    r.sadd("processed:events", event_id)
    r.expire("processed:events", ttl_sec)
```

**적합**: 이벤트 ID < 100만 / 시간 윈도 짧음 (1일 이내).

### 3.2 Bitmap — "정수 ID + 대량 + 활성 카운트"

```python
def mark_active(user_id, day):
    r.setbit(f"active:{day}", user_id, 1)

def is_active(user_id, day):
    return r.getbit(f"active:{day}", user_id) == 1

def dau(day):
    return r.bitcount(f"active:{day}")
```

**적합**: 정수 ID (snowflake 등 큰 ID는 부적합), 일별 / 주별 활성 추적.

```python
# 주간 unique users (BITOP OR)
r.bitop("OR", "active:week", *[f"active:{d}" for d in last_7_days])
weekly_unique = r.bitcount("active:week")
```

### 3.3 HyperLogLog — "수만+ 원소 + 카운트만"

```python
def visit(visitor_id, day):
    r.pfadd(f"uv:{day}", visitor_id)

def daily_uv(day):
    return r.pfcount(f"uv:{day}")

def weekly_uv(end):
    keys = [f"uv:{(end - timedelta(days=i)).isoformat()}" for i in range(7)]
    return r.pfcount(*keys)
```

**적합**: UV / DAU / 검색어 unique 카운트, 메모리 극단 절약.
**부적합**: "이 user_id 가 왔는가?" 의 멤버 검사 (HLL 은 못함).

### 3.4 Bloom Filter — "정확 멤버 검사 + 큰 규모 + 약간의 false positive 허용"

`RedisBloom` 모듈 (Redis Stack 또는 별도 모듈):

```
BF.RESERVE crawled 0.001 100000000   # 1억 원소, 0.1% false positive
BF.ADD crawled "https://..."
BF.EXISTS crawled "https://..."      # 1: 있을 가능성 (false positive 0.1%), 0: 없음 확실
```

```python
def already_crawled(url):
    return r.execute_command("BF.EXISTS", "crawled", url) == 1

def mark_crawled(url):
    r.execute_command("BF.ADD", "crawled", url)
```

**적합**: URL 크롤링, 이메일 spam, "본 적 있는지" 가 false positive 살짝 있어도 OK 인 경우.
**부적합**: 결정적 답이 필요한 경우 (Set 또는 DB 사용).

> 출처: <https://redis.io/docs/latest/develop/data-types/probabilistic/bloom-filter/>

---

## 4. 패턴 결합 — Bloom + DB 검증

```python
def already_crawled_safe(url):
    bloom_says = r.execute_command("BF.EXISTS", "crawled", url)
    if bloom_says == 0:
        return False                      # 확실히 안 본 URL
    
    # Bloom 이 "있을 수도" → DB 정확 확인
    return db.exists("crawled_urls", url)

def mark_crawled(url):
    r.execute_command("BF.ADD", "crawled", url)
    db.insert("crawled_urls", url)
```

→ **DB 부하 99.9% 감소** (대부분 Bloom 에서 거름).

---

## 5. Cuckoo Filter — Bloom + 삭제 지원

`CF.RESERVE crawled 1000000`
- Bloom 처럼 false positive 가능
- **추가로 삭제 가능** (CF.DEL)
- Bloom 보다 살짝 더 메모리 사용

```
CF.ADD seen item1
CF.EXISTS seen item1      # 1
CF.DEL seen item1
CF.EXISTS seen item1      # 0
```

---

## 6. Top-K — "가장 자주 본 N개"

빈도 dedup 의 변형 (TopK 모듈):

```
TOPK.RESERVE topk 10 2000 7 0.9
TOPK.ADD topk "search-term"
TOPK.LIST topk            # 가장 빈번한 10개
```

검색어 / 트렌딩 / 인기 콘텐츠 분석에 유용.

---

## 7. 시간 윈도 dedup

이벤트가 **특정 윈도 내에서만 dedup** 되어야 하면:

### 7.1 ZSET (정확)
```python
def dedup_with_window(event_id, window_sec=300):
    now = time.time()
    key = "dedup:events"
    
    pipe = r.pipeline()
    pipe.zremrangebyscore(key, 0, now - window_sec)
    pipe.zadd(key, {event_id: now}, nx=True)
    pipe.expire(key, window_sec)
    _, added, _ = pipe.execute()
    
    return added == 1   # 1 이면 첫 발생, 0 이면 중복
```

### 7.2 키별 TTL (간단)
```python
def dedup_by_ttl(event_id, ttl_sec=300):
    return r.set(f"dedup:{event_id}", "1", nx=True, ex=ttl_sec) is True
```

→ key 자체가 dedup 마커. TTL 후 자동 삭제.

---

## 8. 메모리 비교 — 1억 dedup

| 방법 | 메모리 (대략) | 정확도 | 카운트 가능 |
|---|---|---|---|
| Set + 평균 16-byte 멤버 | ~5 GB | 100% | O(1) |
| Bitmap (정수 ID) | 12.5 MB | 100% | O(N) |
| HyperLogLog | 12 KB | ~99.19% | O(1) |
| Bloom (1% FP) | 120 MB | ~99% | 별도 |
| Bloom (0.01% FP) | 240 MB | ~99.99% | 별도 |
| Cuckoo (1% FP) | 130 MB | ~99% (삭제 가능) | 별도 |

→ **메모리 vs 정확도 trade-off** 가 dedup 자료형 선택의 핵심.

---

## 9. 흔한 함정

| 함정 | 설명 |
|---|---|
| Set 으로 1억 dedup 시도 | 메모리 폭증. Bitmap (정수) 또는 Bloom 권장. |
| Bitmap 인데 ID 가 sparse | bit 위치만큼 alloc. user_id 1억 부근만 SET → 12MB. user_id 100억 → 1.2GB. ID 압축 필요. |
| HLL 로 멤버 검사 | 불가능. dedup 카운트만. |
| Bloom 의 false positive 무시 | "있을 수도" 를 "있다" 로 단정. DB 검증 결합. |
| TTL 없는 dedup 키 | 무한 누적. EXPIRE 필수. |
| 시간 윈도 무시 | 6개월 전 이벤트와 dedup 충돌. 윈도 명시. |

---

## 10. 결정 트리

```
정확한 멤버 검사 필요?
  ├─ Yes
  │   ├─ 규모 < 100만 → Set
  │   ├─ 정수 ID + 100만~10억 → Bitmap
  │   └─ 그 외 / 매우 큼 → DB / Bloom + DB 검증
  └─ No (카운트 또는 fuzzy 판단만)
      ├─ 정확 카운트 → Set + SCARD
      ├─ 추정 카운트 + 절대 적은 메모리 → HyperLogLog
      └─ 멤버 fuzzy 검사 (false positive OK) → Bloom / Cuckoo
```

---

## 11. 직접 해보기

1. 1만 random ID 를 4가지 방법(Set/Bitmap/HLL/Bloom) 으로 dedup → MEMORY USAGE 비교.
2. HLL 로 100만 ID → PFCOUNT 결과의 오차율 측정.
3. Bloom 1% FP 로 1만 add → 1만 random check → false positive 비율.
4. ZSET 시간 윈도 dedup 으로 5분 안 같은 event 차단.

---

## 12. 참고 자료

- **[Redis Solutions] Data deduplication** — <https://redis.io/solutions/deduplication/>
  - 참고 부분: 4가지 자료형 비교 — §2 근거

- **[Tutorial] Data deduplication with Redis** — <https://redis.io/tutorials/data-deduplication-with-redis/>
  - 참고 부분: 패턴 예시 — §3 근거

- **[공식 문서] Bloom Filter** — <https://redis.io/docs/latest/develop/data-types/probabilistic/bloom-filter/>
  - 참고 부분: BF.RESERVE / BF.ADD / BF.EXISTS — §3.4 근거

- **[공식 문서] Cuckoo Filter** — <https://redis.io/docs/latest/develop/data-types/probabilistic/cuckoo-filter/>
  - 참고 부분: CF.* 명령 — §5 근거

- **[공식 문서] Top-K** — <https://redis.io/docs/latest/develop/data-types/probabilistic/top-k/>
  - 참고 부분: TOPK.* 명령 — §6 근거
