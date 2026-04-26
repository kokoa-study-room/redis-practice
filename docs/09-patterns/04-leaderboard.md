# 04. Leaderboard (리더보드)

> **학습 목표**: ZSET으로 게임/콘텐츠 리더보드 구현, TOP-N 자동 유지, 사용자 주변 ±N명 / 일별·주별 분리·합산 패턴.
> **예상 소요**: 25분

---

## 1. 기본

```
ZADD lb 1500 alice 2300 bob 980 carol
ZRANGE lb 0 -1 WITHSCORES REV     # 점수 내림차순 전체
```

`O(log N)` 삽입 + `O(log N + M)` range. M = 반환 개수.

---

## 2. 점수 갱신

```
ZINCRBY lb 100 alice              # alice +100
ZADD lb GT 2000 alice             # 새 score가 더 클 때만 업데이트
```

`GT/LT` 옵션으로 단조 증가/감소 강제.

---

## 3. TOP-N 유지 (메모리 한계)

리더보드를 영원히 유지할 수 없다. 상위 1000만 보관:

```
ZADD lb $score $player
ZREMRANGEBYRANK lb 0 -1001        # 상위 1000만 남기고 나머지 삭제 (REV 기준 0이 최고)
```

> ZREMRANGEBYRANK은 오름차순 기준이라, 상위 1000을 남기려면 `0 ~ -1001` (전체에서 상위 1000을 뺀 나머지) 삭제.

---

## 4. 사용자 순위 + 주변

```python
def my_rank_and_neighbors(player, n=2):
    rank = r.zrevrank("lb", player)
    if rank is None:
        return None, []
    start = max(0, rank - n)
    end = rank + n
    neighbors = r.zrange("lb", start, end, desc=True, withscores=True)
    return rank + 1, neighbors    # rank는 0-base
```

---

## 5. 일별 / 주별 / 합산

키를 시간 단위로 분리:
```
lb:daily:2026-04-26
lb:daily:2026-04-25
...
lb:weekly:2026-W17
lb:monthly:2026-04
```

추가 시 동시에 여러 키:
```python
def submit(player, score, day):
    pipe = r.pipeline()
    pipe.zadd(f"lb:daily:{day}", {player: score}, gt=True)
    pipe.zadd(f"lb:weekly:{week_of(day)}", {player: score}, gt=True)
    pipe.zadd(f"lb:monthly:{day[:7]}", {player: score}, gt=True)
    pipe.execute()
```

합산 (예: 지난 7일 누적):
```python
day_keys = [f"lb:daily:{d}" for d in last_7_days]
r.zunionstore("lb:7d", day_keys)        # SUM (기본)
top10 = r.zrange("lb:7d", 0, 9, desc=True, withscores=True)
r.expire("lb:7d", 3600)                  # 임시 키
```

---

## 6. 동률(tie-breaker) 처리

같은 score면 멤버 사전순. 시간 가산을 score에 포함하면 "먼저 도달한 사람 우선":

```
score_with_time = score - timestamp_seconds * 0.000001
```

또는 별도 ZSET (시간 인덱스).

---

## 7. ZRANGEBYLEX 활용 — 사전순 인덱스

같은 score(예: 모두 0) 일 때 멤버 사전순으로 검색:
```
ZADD names 0 alice 0 bob 0 carol 0 alex
ZRANGEBYLEX names "[al" "[am"     # al~am 시작
```

자동완성 후보 등에 응용.

---

## 8. Cluster에서 리더보드

ZSET은 한 노드에 들어가야 모든 멤버가 정렬됨. 거대 리더보드는:
- **샤딩** (사용자 ID 해시로 여러 ZSET → 각 노드가 자기 일부)
- 글로벌 TOP-N은 모든 샤드에서 부분 TOP-N 가져와 머지

라이브러리/직접 구현 모두 가능. 1000만+ 사용자라도 단일 ZSET이 보통 충분 (수 GB 메모리).

---

## 9. 흔한 함정

| 함정 | 설명 |
|---|---|
| ZRANGE 0 -1 으로 전체 가져옴 | 큰 ZSET이면 응답 폭증. 페이지네이션 / TOP-N 한정. |
| score 큰 정수 | double 53-bit 정밀도. snowflake 등 불가. |
| TTL 없는 일별 ZSET | 무한 누적. EXPIRE 또는 별도 정리 cron. |
| 동률 처리 안 함 | "같은 점수에서 누가 먼저인가" 로직 의도적으로. |
| 모든 게임을 한 ZSET | 게임/시즌 분리 → 키 분리 |

---

## 10. RedisInsight

ZSET 키 → 표 (rank/member/score). 정렬 토글, 페이지네이션, score 편집.

---

## 11. 직접 해보기

1. 5명 ZADD → ZRANGE 결과 확인.
2. ZINCRBY로 점수 갱신 → 등수 변동.
3. TOP-100 유지 패턴 시뮬레이션 (10000개 추가 후 ZCARD).
4. 일별 키 7일치 + ZUNIONSTORE 로 주간 합산.
5. RedisInsight로 ZSET 시각화.

---

## 12. 참고 자료

- **[공식 문서] Redis Sorted Sets**
  - URL: <https://redis.io/docs/latest/develop/data-types/sorted-sets/>
  - 참고 부분: leaderboard 사용 사례 — §1 근거

- **[공식 문서] ZADD options (GT/LT/NX/XX)**
  - URL: <https://redis.io/docs/latest/commands/zadd/>
  - 참고 부분: 옵션 정의 — §2 근거

- **[공식 문서] ZUNIONSTORE / ZINTERSTORE**
  - URL: <https://redis.io/docs/latest/commands/zunionstore/>
  - 참고 부분: AGGREGATE / WEIGHTS — §5 근거
