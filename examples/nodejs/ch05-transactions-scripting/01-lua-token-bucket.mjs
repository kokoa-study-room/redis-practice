/**
 * Reference: docs/05-transactions-scripting/02-lua-scripts.md, docs/09-patterns/02-rate-limiter.md
 *
 * Token Bucket — Lua 로 atomic 구현.
 */
import { withClient, section } from "../_common.mjs";

const TOKEN_BUCKET = `
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
`;

async function allowed(r, key, capacity, rate) {
  const nowMs = Date.now();
  const result = await r.eval(TOKEN_BUCKET, {
    keys: [key],
    arguments: [String(capacity), String(rate), String(nowMs)],
  });
  return result === 1;
}

await withClient(async (r) => {
  const KEY = "rl:user:1";
  await r.del(KEY);

  section("Token Bucket: capacity=5, rate=1/sec");
  for (let i = 0; i < 8; i++) {
    const ok = await allowed(r, KEY, 5, 1);
    console.log(`  request ${i + 1}: ${ok ? "PASS" : "BLOCK"}`);
  }

  section("2초 대기 (refill ~2 토큰)");
  await new Promise((res) => setTimeout(res, 2000));
  for (let i = 0; i < 4; i++) {
    const ok = await allowed(r, KEY, 5, 1);
    console.log(`  request: ${ok ? "PASS" : "BLOCK"}`);
  }

  await r.del(KEY);
});
