# 08. HyperLogLog (HLL)

> **학습 목표**: HLL이 distinct count를 **고정 ~12KB로 추정 (오차 ~0.81%)** 한다는 트레이드오프를 이해하고 UV/방문자 카운트에 사용할 수 있다.
> **예상 소요**: 15분

---

## 1. 개념

> **"몇 개의 서로 다른 값을 봤는가?"** 를 적은 메모리로 **추정** 해주는 확률적 자료구조.

```
일반 Set으로 1000만 unique 사용자 추적: 수백 MB
HyperLogLog 로:                     ~12KB (고정), 오차 ~0.81%
```

용도:
- DAU / UV (unique visitor) 카운트
- 검색어 중복 제거 카운트
- 재방문/이탈 비율

**정확한 원소 목록은 알 수 없다.** 카운트만.

> 출처: <https://redis.io/docs/latest/develop/data-types/probabilistic/hyperloglogs/>
> 참고 부분: "small constant amount of memory ... standard error 0.81%" — §1 수치 근거

---

## 2. 기본 사용법

```
# 추가 (요소가 이미 있는지 모름; 그냥 던지면 됨)
PFADD visits "user-1" "user-2" "user-3"
# → 1: HLL 카드값이 변함, 0: 변화 없음

# 추정 카운트
PFCOUNT visits                # 3 부근

# 여러 키 합쳐서 카운트 (병합 후 추정)
PFADD a "u1" "u2"
PFADD b "u2" "u3"
PFCOUNT a b                   # 3 부근 (합집합 추정)

# 영구 병합
PFMERGE total a b
PFCOUNT total                 # 3 부근
```

---

## 3. 클라이언트 코드 예제

### Python — 일별 UV + 주간 UV

```python
import redis
from datetime import date, timedelta

r = redis.Redis(decode_responses=True)

def visit(user_id: str, day: date):
    r.pfadd(f"uv:{day.isoformat()}", user_id)

def daily_uv(day: date) -> int:
    return r.pfcount(f"uv:{day.isoformat()}")

def weekly_uv(end: date) -> int:
    keys = [f"uv:{(end - timedelta(days=i)).isoformat()}" for i in range(7)]
    return r.pfcount(*keys)   # 임시 병합 후 카운트 (저장 안 함)

# 사용
for u in ["a","b","a","c","d","b"]:
    visit(u, date.today())
print(daily_uv(date.today()))   # 4 부근
```

---

## 4. 내부 동작

### 4.1 인코딩

| 인코딩 | 조건 | 메모리 |
|---|---|---|
| `sparse` | 멤버 적음 (대부분 빈 레지스터) | 가변, 매우 작음 |
| `dense` | 일정 임계 초과 | **고정 12,304 byte** |

전환 임계: `hll-sparse-max-bytes` (기본 3000)

```
PFADD k a b c
OBJECT ENCODING k          # 모르고 호출해도 OK; HLL은 String으로 보고 sparse / dense 인코딩

DEBUG OBJECT k             # encoding 정보 확인 (학습용)
```

### 4.2 알고리즘 한 줄 설명

각 요소를 해시 → 해시값의 leading-zero 분포로 카드값을 추정.
"매우 드문 패턴이 보였다 = 큰 집합이다" 를 통계적으로 역추적.

> 자세한 수학은 [HyperLogLog 원논문](https://en.wikipedia.org/wiki/HyperLogLog) 참고.

### 4.3 Big-O

| 명령 | 복잡도 |
|---|---|
| `PFADD` | O(1) per element |
| `PFCOUNT k` | O(1) (단일 키), 캐시된 카드값 사용 |
| `PFCOUNT k1 k2 ...` | O(N) (HLL 병합 필요) |
| `PFMERGE` | O(N) (대상 HLL 수) |

---

## 5. 흔한 함정

| 함정 | 설명 |
|---|---|
| **정확한 원소 목록 필요** | HLL은 카운트만. 원소 검사가 필요하면 Set이나 Bloom Filter (RedisBloom 모듈). |
| **작은 집합에 사용** | 100명 정도면 그냥 Set이 더 정확하고 메모리도 비슷. HLL은 1만+ 부터 의미 있음. |
| **TTL 안 부여** | 일별 키가 영원히 누적. `EXPIRE` 필수. |
| **서로 다른 hash로 두 시스템 비교** | HLL끼리만 PFMERGE 가능 (Redis 자체 hash 사용). |
| **오차 0.81%를 "거의 정확"으로 오해** | 1억에 80만 오차. 광고 빌링 등에는 부적합. |

---

## 6. RedisInsight

`TYPE` 에서는 `string` 으로 보이나, RedisInsight는 HLL 키임을 헤더로 인식해서 PFCOUNT 결과를 같이 표시.

---

## 7. 직접 해보기

1. `PFADD k $(seq 1 1000)` 후 `PFCOUNT k` → 1000 ± 8 부근 (오차 ~0.81%).
2. 같은 요소를 여러 번 PFADD → `PFCOUNT` 가 안 변하는지.
3. 두 일자의 UV를 PFMERGE → 합집합 카운트가 어떤지.
4. `STRLEN` 으로 sparse/dense 변환 시점 관찰.

---

## 8. 참고 자료

- **[공식 문서] HyperLogLog**
  - URL: <https://redis.io/docs/latest/develop/data-types/probabilistic/hyperloglogs/>
  - 참고 부분: "standard error of 0.81%", "12k bytes per key" — §1, §4.1 수치 근거

- **[공식 문서] PFADD / PFCOUNT / PFMERGE**
  - URL: <https://redis.io/docs/latest/commands/pfadd/>, etc.
  - 참고 부분: Time complexity — §4.3 근거

- **[GitHub] redis/redis — redis.conf** `hll-sparse-max-bytes 3000`
  - URL: <https://github.com/redis/redis/blob/8.6/redis.conf>
  - 참고 부분: HLL sparse/dense 임계 — §4.1 근거
