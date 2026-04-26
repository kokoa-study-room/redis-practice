# 07. Bitmap

> **학습 목표**: Bitmap이 사실 String 위의 비트 연산이라는 점, 사용자별 출석 체크/플래그 대량 저장에 적합함을 이해한다.
> **예상 소요**: 15분

---

## 1. 개념

Bitmap은 **별도 자료형이 아니다.** String의 각 비트를 0/1로 다루는 명령군일 뿐이다.

```
String: 1바이트 = 8비트
SETBIT k 7 1  → 키 k의 첫 바이트의 마지막 비트를 1로 설정
```

용도:
- **출석 체크 / 활동 트래킹**: user-id를 비트 인덱스로 (1억 명도 ~12.5MB)
- **A/B 테스트 그룹 표시**
- **불리언 플래그 대량 저장**

장점: **메모리 극단적 효율** (1비트 = 1 사용자/사건).

---

## 2. 기본 사용법

```
# 비트 설정 (offset, value)
SETBIT users:active:2026-04-26 1001 1
SETBIT users:active:2026-04-26 1002 1
SETBIT users:active:2026-04-26 5000 1

# 조회
GETBIT users:active:2026-04-26 1001       # 1
GETBIT users:active:2026-04-26 9999       # 0

# 1로 설정된 비트 개수
BITCOUNT users:active:2026-04-26          # 3

# 범위 카운트 (바이트 단위 또는 BIT 단위 — 7+ 옵션)
BITCOUNT users:active:2026-04-26 0 100 BYTE
BITCOUNT users:active:2026-04-26 0 100 BIT

# 1 (또는 0) 첫 위치
BITPOS users:active:2026-04-26 1          # 1001 (첫 1)
BITPOS users:active:2026-04-26 0          # 0 (첫 0)

# Bitwise 연산
SETBIT u1 5 1
SETBIT u1 9 1
SETBIT u2 5 1
SETBIT u2 7 1

BITOP AND result u1 u2                    # 양쪽 다 1인 비트만
BITCOUNT result                           # 1 (5번 비트만)

BITOP OR  result u1 u2                    # 한쪽이라도 1
BITOP XOR result u1 u2
BITOP NOT result u1

# 멀티 작업 (Redis 6.2+)
BITFIELD users:counters SET u8 #0 100 INCRBY u8 #1 5 GET u8 #0
# → user-0의 카운터를 100으로 SET, user-1의 카운터 +5, user-0의 카운터 조회
```

> 출처: <https://redis.io/docs/latest/develop/data-types/bitmaps/>

---

## 3. 클라이언트 코드 예제

### Python — DAU/MAU 측정

```python
import redis
from datetime import date, timedelta

r = redis.Redis(decode_responses=True)

def mark_active(user_id: int, day: date):
    key = f"users:active:{day.isoformat()}"
    r.setbit(key, user_id, 1)
    r.expire(key, 60 * 86400)  # 60일 보관

def dau(day: date) -> int:
    return r.bitcount(f"users:active:{day.isoformat()}")

def mau(end: date) -> int:
    keys = [f"users:active:{(end - timedelta(days=i)).isoformat()}" for i in range(30)]
    r.bitop("OR", "users:mau:tmp", *keys)
    count = r.bitcount("users:mau:tmp")
    r.delete("users:mau:tmp")
    return count

# 사용
mark_active(1001, date.today())
mark_active(1002, date.today())
print("DAU:", dau(date.today()))   # 2
print("MAU:", mau(date.today()))   # 2 (오늘만 활성이면)
```

---

## 4. 내부 동작

내부 인코딩은 **String** (`raw` / `embstr` / `int`).
`SETBIT` 가 호출되면 필요시 String을 자동 확장 (offset/8 바이트까지).

> 메모리 계산:
> - 100만 사용자: ~125 KB
> - 1억 사용자: ~12.5 MB
> - **단, 가장 큰 ID에 비트 1개만 SET해도 그 위치까지의 모든 바이트 alloc**.

### Big-O

| 명령 | 복잡도 |
|---|---|
| `SETBIT`, `GETBIT` | O(1) |
| `BITCOUNT` | O(N) (전체 길이) |
| `BITOP` | O(N) (두 키 중 더 긴 쪽) |
| `BITPOS` | O(N) |
| `BITFIELD` | O(1) per sub-command |

---

## 5. 흔한 함정

| 함정 | 설명 |
|---|---|
| **희소(sparse) 사용자 ID** | user_id가 큰 정수(예: snowflake)면 BITMAP에 잘 안 맞음. Set 또는 HyperLogLog 고려. |
| **`SETBIT k 1000000000 1`** | 즉시 125MB alloc. 의도한 건지 확인. |
| **BITCOUNT 큰 키** | O(N). 크면 BIT 옵션으로 범위 한정. |
| **TTL 미설정** | 일별 키가 영원히 쌓임. `EXPIRE` 필수. |
| **Bitmap이 별도 키 타입인 줄 안다** | `TYPE k` 결과는 `string` 이다. |

---

## 6. RedisInsight

Browser → String 키로 보임. Workbench에서 `BITCOUNT` / `BITOP` 직접 실행해 결과 확인.

---

## 7. 직접 해보기

1. 1만 명을 무작위로 `SETBIT users:active:today` → `BITCOUNT` 결과.
2. `STRLEN users:active:today` 로 키 크기(byte) 확인 → 1만/8 ≈ 1250 byte 부근?
3. 두 일자 BITMAP에 `BITOP AND` → 양일 모두 활성 사용자 수.
4. `BITFIELD u8 #0 INCRBY 1` 명령으로 user-0의 카운터를 5번 증가.

---

## 8. 참고 자료

- **[공식 문서] Redis Bitmaps**
  - URL: <https://redis.io/docs/latest/develop/data-types/bitmaps/>
  - 참고 부분: "Bitmaps are not an actual data type, but a set of bit-oriented operations defined on the String type" — §1 정의 근거

- **[공식 문서] BITCOUNT / BITOP / BITFIELD / BITPOS**
  - URL: <https://redis.io/docs/latest/commands/bitcount/>, etc.
  - 참고 부분: Time complexity 및 BIT/BYTE 옵션 — §2, §4 근거
