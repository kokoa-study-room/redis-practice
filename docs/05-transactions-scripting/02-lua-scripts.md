# 02. Lua 스크립트 (EVAL / EVALSHA)

> **학습 목표**: Redis가 Lua 스크립트를 서버에서 atomic하게 실행한다는 점, KEYS/ARGV 분리 이유, EVALSHA로 RTT를 줄이는 패턴을 익힌다.
> **예상 소요**: 25분

---

## 1. 개념

```
EVAL "script" numkeys key1 key2 ... arg1 arg2 ...
```

- **서버에서 실행** → 네트워크 왕복 1회로 복잡한 로직 처리.
- 실행 동안 다른 명령 끼어들지 않음 (단일 스레드 + atomic).
- **Lua 5.1** 기반 (Redis 7.x까지). Redis 7.4부터 `Lua 5.4` 도 옵션.

용도:
- 여러 자료형 결합 (예: ZADD + LPUSH + INCR 한 번에)
- WATCH 패턴이 너무 복잡할 때
- Rate Limiter (Token Bucket / Sliding Window)
- 분산 락의 안전한 해제 (해당 락이 내 락인지 확인 후 해제)

---

## 2. 기본 사용법

### EVAL

```
EVAL "return 'hello'" 0
"hello"

EVAL "return redis.call('GET', KEYS[1])" 1 mykey
```

### KEYS vs ARGV

```
EVAL "return KEYS[1]..':'..ARGV[1]" 1 user "Kim"
"user:Kim"
```

- **KEYS[N]**: 키 (Cluster에서 슬롯 라우팅에 사용)
- **ARGV[N]**: 일반 인자

> Cluster에서는 모든 KEYS가 같은 슬롯에 있어야 함. hashtag 사용.

### EVALSHA — 캐싱

```
SCRIPT LOAD "return redis.call('GET', KEYS[1])"
"a8b8e..."     ← SHA1

EVALSHA a8b8e... 1 mykey
```

장점: 같은 스크립트를 여러 번 실행할 때 **본문 전송 안 해도 됨** → 네트워크 절약.

라이브러리 패턴: `EVALSHA` 시도 → `NOSCRIPT` 에러면 `EVAL` 로 자동 fallback.

---

## 3. 실전 예 — Redlock 안전 해제

```lua
-- KEYS[1] = lock key
-- ARGV[1] = my client id
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
else
    return 0
end
```

```python
RELEASE_LOCK = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
else
    return 0
end
"""

def release_lock(r, key, my_token):
    return r.eval(RELEASE_LOCK, 1, key, my_token)
```

이렇게 안 하면 — 내 락이 만료된 후 다른 클라이언트가 같은 키로 락 잡았는데 내가 DEL 하는 사고 발생.

---

## 4. 실전 예 — Token Bucket Rate Limiter

```lua
-- KEYS[1] = bucket key
-- ARGV[1] = capacity   (e.g., 10)
-- ARGV[2] = refill_rate (per sec, e.g., 1)
-- ARGV[3] = now_ms

local capacity = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local data = redis.call('HMGET', KEYS[1], 'tokens', 'last')
local tokens = tonumber(data[1]) or capacity
local last = tonumber(data[2]) or now

-- refill
local elapsed = (now - last) / 1000
tokens = math.min(capacity, tokens + elapsed * rate)

if tokens < 1 then
    redis.call('HSET', KEYS[1], 'tokens', tokens, 'last', now)
    return 0   -- 거부
else
    tokens = tokens - 1
    redis.call('HSET', KEYS[1], 'tokens', tokens, 'last', now)
    redis.call('PEXPIRE', KEYS[1], math.ceil(capacity / rate * 1000))
    return 1   -- 허용
end
```

---

## 5. Lua API 핵심

### redis.call vs redis.pcall

```
redis.call('GET', 'k')      -- 에러 시 스크립트 중단 + 에러 전파
redis.pcall('GET', 'k')     -- 에러 시 에러 객체 반환, 스크립트 계속
```

### 반환 타입 매핑

| Lua 타입 | Redis (RESP) |
|---|---|
| number | integer (소수점 손실됨!) |
| string | bulk string |
| table (배열) | array |
| true | integer 1 |
| false | nil |
| nil | nil |

### 스크립트 안에서 시간

> **`os.time` / 시스템 시계 직접 사용 금지** — 스크립트는 결정적이어야 복제·AOF 안전. 필요하면 클라이언트에서 `now`를 ARGV로 넘김.

> 출처: <https://redis.io/docs/latest/develop/programmability/eval-intro/>
> 참고 부분: "Scripts as pure functions" — 결정성 요구 근거

---

## 6. SCRIPT 명령

```
SCRIPT EXISTS <sha>             # 1: 캐시됨, 0: 없음
SCRIPT LOAD <body>              # 캐시에 등록 + sha 반환
SCRIPT FLUSH                    # 모든 캐시 비움
SCRIPT KILL                     # 무한 루프 종료 (write 안 한 경우만)
```

---

## 7. 흔한 함정

| 함정 | 설명 |
|---|---|
| 매우 긴 스크립트 | 그동안 서버 정지. `lua-time-limit` (기본 5초) 초과 시 SCRIPT KILL 가능 (단, 어떤 write도 안 한 경우). |
| 결정적이지 않은 함수 사용 | `os.time`, `math.random` (시드 안 줄 때) → 복제/AOF 시 결과 다름. |
| `redis.call` 안에서 KEYS 외 키 직접 사용 | Cluster에서 슬롯 매칭 안 됨 → 거부됨. |
| number 반환의 소수점 손실 | Lua → Redis integer 변환에서 잘림. 소수가 필요하면 string으로. |
| Cluster에서 여러 슬롯 KEYS | 거부됨. hashtag로 같은 슬롯 강제. |

---

## 8. Lua vs Functions (다음 챕터)

| 항목 | Lua (EVAL) | Functions (Redis 7+) |
|---|---|---|
| 영속 등록 | SCRIPT LOAD 후 캐시 (재시작 시 사라짐) | 영속 (RDB/AOF에 저장) |
| 네임스페이스 | 없음 | `library` 단위 |
| 라이브러리 관리 | `SCRIPT FLUSH` 만 | `FUNCTION DELETE/FLUSH/LOAD/LIST` |
| 코드 재사용 | EVALSHA로 SHA만 공유 | 명명된 function 호출 |

운영 권장 (7+): **Functions로 점진 이전**.

---

## 9. 직접 해보기

1. `EVAL "return ARGV[1]+ARGV[2]" 0 3 4` → 7?
2. SCRIPT LOAD → 같은 스크립트 EVALSHA — 차이 없는 결과.
3. Redlock 안전 해제 스크립트를 cli에서 실행.
4. Rate Limiter 스크립트로 1초에 100회 요청 → 일부만 통과하는지.
5. (도전) `redis.pcall` 로 일부 실패 처리하는 스크립트.

---

## 10. 참고 자료

- **[공식 문서] EVAL Introduction**
  - URL: <https://redis.io/docs/latest/develop/programmability/eval-intro/>
  - 참고 부분: KEYS vs ARGV, Pure functions — §2, §5 근거

- **[공식 문서] Lua API reference**
  - URL: <https://redis.io/docs/latest/develop/programmability/lua-api/>
  - 참고 부분: redis.call vs pcall, 반환 타입 매핑 — §5 근거

- **[공식 문서] EVAL / EVALSHA / SCRIPT**
  - URL: <https://redis.io/docs/latest/commands/eval/>, etc.
  - 참고 부분: 동작 정의 — §2, §6 근거
