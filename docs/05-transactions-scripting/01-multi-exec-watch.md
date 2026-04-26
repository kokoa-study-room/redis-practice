# 01. MULTI / EXEC / WATCH

> **학습 목표**: MULTI/EXEC가 명령을 큐잉 후 일괄 실행한다는 점, WATCH로 낙관적 락을 구현하는 방법, "Redis 트랜잭션은 롤백이 없다"는 사실을 이해한다.
> **예상 소요**: 25분

---

## 1. 개념

```
MULTI                 # 트랜잭션 시작
SET k1 1              # 큐잉
SET k2 2              # 큐잉
INCR counter          # 큐잉
EXEC                  # 한 번에 실행, 결과 배열 반환
```

**핵심**:
- EXEC 중에는 다른 클라이언트 명령이 끼어들 수 없음 (단일 스레드).
- 명령 자체에 문법 오류 있으면 EXEC 시점에 거부 (안전).
- 런타임 오류(예: WRONGTYPE)는 그 명령만 실패하고 **나머지는 그대로 실행** — **자동 롤백 없음**.

---

## 2. 사용 예

```
127.0.0.1:6379> MULTI
OK
127.0.0.1:6379> SET balance 100
QUEUED
127.0.0.1:6379> DECRBY balance 30
QUEUED
127.0.0.1:6379> INCRBY history:tx 1
QUEUED
127.0.0.1:6379> EXEC
1) OK
2) (integer) 70
3) (integer) 1
```

### 취소 — DISCARD

```
MULTI
SET k v
DISCARD                 # 큐 비움, 트랜잭션 종료
```

---

## 3. WATCH — 낙관적 락 (Optimistic Locking)

문제: "값을 읽은 후, 그 값에 따라 다른 명령을 실행하는데, 그 사이에 다른 클라이언트가 값을 바꾸면 안 됨"

```python
import redis
r = redis.Redis(decode_responses=True)

with r.pipeline() as pipe:
    while True:
        try:
            pipe.watch("balance")
            current = int(pipe.get("balance") or 0)
            if current < 30:
                pipe.unwatch()
                print("잔액 부족")
                break
            pipe.multi()
            pipe.decrby("balance", 30)
            pipe.incrby("history:tx", 1)
            pipe.execute()    # WATCH 한 키가 변하지 않았으면 성공
            print("성공")
            break
        except redis.WatchError:
            print("재시도 — 다른 클라이언트가 balance를 변경함")
            continue
```

**WATCH 동작**:
- WATCH 한 키가 EXEC 시점까지 다른 클라이언트에 의해 **변경되면 EXEC가 nil 반환** (실패).
- 클라이언트는 잡아서 **재시도** 하면 됨.
- 변경 안 됐으면 정상 실행.

> 출처: <https://redis.io/docs/latest/develop/interact/transactions/>
> 참고 부분: "Optimistic locking using check-and-set" 섹션 — 본 절 근거

---

## 4. 왜 롤백이 없는가?

> "MULTI/EXEC 안의 명령 중 하나가 런타임 오류로 실패해도, 나머지는 실행된다."

이유 (Redis 설계자의 입장):
- 런타임 오류는 **프로그래머 버그** (잘못된 자료형에 명령 적용 등).
- 프로덕션 코드에서는 절대 일어나지 말아야 할 종류 → 런타임 롤백 메커니즘은 복잡도만 늘림.
- 데이터 일관성은 **WATCH + 재시도** 로 보장.

> 출처: <https://redis.io/docs/latest/develop/interact/transactions/#what-about-rollbacks>

문법 오류 (예: 명령 자체가 존재 안 함, 인자 개수 틀림)는 EXEC 시점에 전체 트랜잭션이 거부됨.

---

## 5. Pipeline vs Transaction

같은 `pipeline()` 객체로 둘 다 표현 가능 (라이브러리 따라 옵션).

| 항목 | Pipeline | Transaction (MULTI/EXEC) |
|---|---|---|
| 목적 | RTT 절약 (네트워크 왕복) | 원자적 실행 + 격리 |
| 명령 사이 다른 클라이언트 끼어듦 | **가능** | 불가 |
| EXEC 한 번에 결과 | ✅ | ✅ |

```python
# Pipeline (transaction=False)
with r.pipeline(transaction=False) as pipe:
    pipe.set("k1", 1)
    pipe.set("k2", 2)
    pipe.execute()      # MULTI/EXEC 없이 그냥 batch 전송

# Transaction (기본값)
with r.pipeline() as pipe:
    pipe.set("k1", 1)
    pipe.set("k2", 2)
    pipe.execute()      # MULTI ... EXEC
```

---

## 6. 흔한 함정

| 함정 | 설명 |
|---|---|
| 런타임 오류에 자동 롤백 기대 | **롤백 없음.** WATCH 패턴 또는 Lua로 보장. |
| MULTI 안에서 결과를 보고 분기 | 큐잉만 됨 (`QUEUED`). 결과 반환은 EXEC 후. 조건 분기 필요하면 WATCH 패턴 또는 Lua. |
| WATCH 한 키를 EXEC 안에서 다시 수정 | 자기 자신 수정은 트리거 X. 다른 클라이언트만. |
| MULTI 후 DISCARD 안 함 | connection 상태가 트랜잭션 모드로 남음. 라이브러리 기본은 with 블록으로 자동 처리. |
| Cluster에서 MULTI/EXEC | 한 트랜잭션의 모든 키가 **같은 슬롯** 에 있어야 함. hashtag `{user:1}` 사용. |

---

## 7. 직접 해보기

1. cli에서 MULTI / 잘못된 명령 / EXEC → 에러 결과.
2. 두 터미널 — A에서 WATCH counter / GET counter 후 B에서 INCR counter → A에서 EXEC nil.
3. Python에서 잔액 차감 + 히스토리 증가를 WATCH 패턴으로.
4. Lua 한 줄로 같은 작업: 02-lua-scripts.md 학습 후 비교.

---

## 8. 참고 자료

- **[공식 문서] Transactions**
  - URL: <https://redis.io/docs/latest/develop/interact/transactions/>
  - 참고 부분: "What about Rollbacks?" + "Optimistic locking" — §3, §4 근거

- **[공식 문서] MULTI / EXEC / WATCH / DISCARD**
  - URL: <https://redis.io/docs/latest/commands/multi/>, etc.
  - 참고 부분: 동작 정의 — §2, §3 근거
