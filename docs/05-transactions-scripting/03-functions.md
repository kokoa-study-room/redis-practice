# 03. Redis Functions (Redis 7+)

> **학습 목표**: Functions가 Lua 스크립트를 영속적으로 등록·관리하는 7+ 기능임을 이해하고, 라이브러리 단위로 함수를 등록·호출할 수 있다.
> **예상 소요**: 20분

---

## 1. 개념

> **EVAL + 영속 등록 + 네임스페이스.** Lua 스크립트를 라이브러리(library)로 묶어서 Redis에 등록하면, 재시작 후에도 살아있고 RDB/AOF로 백업도 됨.

라이브러리 = Lua 코드 모듈 + 그 안의 여러 named functions.

```lua
#!lua name=mylib

redis.register_function('myadd', function(keys, args)
    return tonumber(args[1]) + tonumber(args[2])
end)

redis.register_function('mygetset', function(keys, args)
    local prev = redis.call('GET', keys[1])
    redis.call('SET', keys[1], args[1])
    return prev
end)
```

---

## 2. 등록 / 호출

### 등록

```bash
redis-cli FUNCTION LOAD "$(cat mylib.lua)"
# "mylib"

# 또는 REPLACE로 갱신
redis-cli FUNCTION LOAD REPLACE "$(cat mylib.lua)"
```

### 목록

```
FUNCTION LIST                # 등록된 라이브러리들
FUNCTION DUMP                # 모든 라이브러리 직렬화 (백업)
FUNCTION RESTORE <data>      # 복원
```

### 호출

```
FCALL myadd 0 3 4            # 0 = numkeys
(integer) 7

FCALL mygetset 1 mykey "newval"   # 1 key, then arg
```

read-only 변형:
```
FCALL_RO myadd 0 3 4          # write 못하는 함수만
```

### 삭제

```
FUNCTION DELETE mylib
FUNCTION FLUSH                # 전부
```

---

## 3. Lua 차이점 (vs EVAL)

| 항목 | EVAL | Functions |
|---|---|---|
| 등록 단위 | 스크립트 한 개 | 여러 함수를 묶은 라이브러리 |
| 영속 | SHA 캐시만 (재시작 사라짐) | RDB/AOF에 저장 |
| 호출 | `EVAL` / `EVALSHA` | `FCALL` / `FCALL_RO` |
| FCALL_RO | 없음 | ✅ (read-only로 명확히 구분) |
| 라이브러리 메타 | 없음 | 이름 / 함수 목록 |

---

## 4. 실전 예 — Rate Limiter Library

```lua
#!lua name=ratelimit

-- Token Bucket
redis.register_function('token_bucket', function(keys, args)
    local capacity = tonumber(args[1])
    local rate = tonumber(args[2])
    local now = tonumber(args[3])
    
    local data = redis.call('HMGET', keys[1], 'tokens', 'last')
    local tokens = tonumber(data[1]) or capacity
    local last = tonumber(data[2]) or now
    
    local elapsed = (now - last) / 1000
    tokens = math.min(capacity, tokens + elapsed * rate)
    
    if tokens < 1 then
        redis.call('HSET', keys[1], 'tokens', tokens, 'last', now)
        return 0
    else
        tokens = tokens - 1
        redis.call('HSET', keys[1], 'tokens', tokens, 'last', now)
        redis.call('PEXPIRE', keys[1], math.ceil(capacity / rate * 1000))
        return 1
    end
end)

-- Sliding Window (ZSET 기반)
redis.register_function('sliding_window', function(keys, args)
    local window_ms = tonumber(args[1])
    local limit = tonumber(args[2])
    local now = tonumber(args[3])
    
    redis.call('ZREMRANGEBYSCORE', keys[1], 0, now - window_ms)
    local count = redis.call('ZCARD', keys[1])
    
    if count >= limit then
        return 0
    else
        redis.call('ZADD', keys[1], now, now)
        redis.call('PEXPIRE', keys[1], window_ms)
        return 1
    end
end)
```

호출:
```bash
redis-cli FUNCTION LOAD REPLACE "$(cat ratelimit.lua)"

redis-cli FCALL token_bucket 1 user:1 10 1 $(date +%s%3N)
# 1: 허용, 0: 거부

redis-cli FCALL sliding_window 1 user:1 60000 100 $(date +%s%3N)
```

---

## 5. Python 클라이언트

```python
import redis
r = redis.Redis()

with open("ratelimit.lua") as f:
    r.function_load(f.read(), replace=True)

allowed = r.fcall("token_bucket", 1, "user:1", 10, 1, int(time.time()*1000))
```

---

## 6. 흔한 함정

| 함정 | 설명 |
|---|---|
| `#!lua name=...` 첫 줄 빼먹음 | 라이브러리 이름 필수. LOAD 실패. |
| Cluster에서 여러 슬롯 KEYS | EVAL 과 동일하게 거부됨. hashtag. |
| `FCALL` 인자 순서 | `FCALL <name> <numkeys> <key1>...<arg1>...` (EVAL과 동일 패턴) |
| 라이브러리 통째 갱신만 가능 | 함수 한 개만 갱신은 안 됨. REPLACE 로 라이브러리 전체. |
| FCALL_RO 함수에서 write 호출 | 거부됨. write 가 필요하면 FCALL. |

---

## 7. EVAL을 Functions로 마이그레이션

### Before
```python
SCRIPT = """if redis.call('GET', KEYS[1]) == ARGV[1] then ... end"""
sha = r.script_load(SCRIPT)
r.evalsha(sha, 1, "lock:1", "my-token")
```

### After
```lua
-- locks.lua
#!lua name=locks
redis.register_function('release', function(keys, args)
    if redis.call('GET', keys[1]) == args[1] then
        return redis.call('DEL', keys[1])
    else
        return 0
    end
end)
```

```python
r.function_load(open("locks.lua").read(), replace=True)
r.fcall("release", 1, "lock:1", "my-token")
```

장점: 재시작 후에도 살아있고, `FUNCTION LIST` 로 목록 한눈에.

---

## 8. 직접 해보기

1. 위 ratelimit 라이브러리 LOAD → FCALL token_bucket.
2. FUNCTION LIST 로 등록 확인.
3. `docker compose down && docker compose up -d` 후 FUNCTION LIST → 그대로 살아있나?
4. FCALL_RO 로 read-only 함수 호출, FCALL 안 쓰고도 잘 되는지.
5. FUNCTION DUMP → 다른 인스턴스에 RESTORE.

---

## 9. 참고 자료

- **[공식 문서] Functions**
  - URL: <https://redis.io/docs/latest/develop/programmability/functions-intro/>
  - 참고 부분: 라이브러리 정의, `register_function`, FCALL 의미 — §1, §2 근거

- **[공식 문서] FUNCTION LOAD / FCALL / FCALL_RO**
  - URL: <https://redis.io/docs/latest/commands/function-load/>, etc.
  - 참고 부분: 명령 정의 — §2 근거
