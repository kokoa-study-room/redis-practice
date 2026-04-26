"""Reference: docs/05-transactions-scripting/02-lua-scripts.md, docs/09-patterns/02-rate-limiter.md

Token Bucket Rate Limiter — Lua 로 atomic 구현.
"""
import sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from _common import get_client, section  # noqa: E402


TOKEN_BUCKET = """
local capacity = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local data = redis.call('HMGET', KEYS[1], 'tokens', 'last')
local tokens = tonumber(data[1]) or capacity
local last = tonumber(data[2]) or now

local elapsed = (now - last) / 1000
tokens = math.min(capacity, tokens + elapsed * rate)

if tokens < 1 then
    redis.call('HSET', KEYS[1], 'tokens', tokens, 'last', now)
    return 0
else
    tokens = tokens - 1
    redis.call('HSET', KEYS[1], 'tokens', tokens, 'last', now)
    redis.call('PEXPIRE', KEYS[1], math.ceil(capacity / rate * 1000))
    return 1
end
"""


def allowed(r, key, capacity, rate):
    now_ms = int(time.time() * 1000)
    return r.eval(TOKEN_BUCKET, 1, key, capacity, rate, now_ms) == 1


def main():
    r = get_client()
    KEY = "rl:user:1"
    r.delete(KEY)

    with section("Token Bucket: capacity=5, rate=1/sec"):
        # 즉시 5 burst 통과 가능
        for i in range(8):
            ok = allowed(r, KEY, capacity=5, rate=1)
            print(f"  request {i+1}: {'PASS' if ok else 'BLOCK'}")

    with section("2초 대기 (refill ~2 토큰)"):
        time.sleep(2)
        for i in range(4):
            ok = allowed(r, KEY, capacity=5, rate=1)
            print(f"  request: {'PASS' if ok else 'BLOCK'}")

    r.delete(KEY)


if __name__ == "__main__":
    main()
