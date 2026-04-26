/**
 * Reference: docs/09-patterns/03-distributed-lock-redlock.md
 *
 * SET NX EX + Lua 안전 해제.
 */
import { randomUUID } from "node:crypto";
import { getClient, section } from "../_common.mjs";

const RELEASE = `
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
else
    return 0
end
`;

async function acquire(r, name, ttl = 5) {
  const token = randomUUID();
  const ok = await r.set(`lock:${name}`, token, { NX: true, EX: ttl });
  return ok ? token : null;
}

async function release(r, name, token) {
  return r.eval(RELEASE, {
    keys: [`lock:${name}`],
    arguments: [token],
  });
}

async function worker(name, holdSec) {
  const r = getClient();
  await r.connect();
  console.log(`[${name}] acquire 시도`);
  const token = await acquire(r, "shared-resource", 10);
  if (!token) {
    console.log(`[${name}] FAIL — 누군가 잡고 있음`);
    await r.close();
    return;
  }
  console.log(`[${name}] OK — ${holdSec}초 hold`);
  await new Promise((res) => setTimeout(res, holdSec * 1000));
  const released = await release(r, "shared-resource", token);
  console.log(`[${name}] release returned ${released}`);
  await r.close();
}

const setup = getClient();
await setup.connect();
await setup.del("lock:shared-resource");
await setup.close();

section("두 워커 동시에 같은 락");
await Promise.all([
  worker("worker-A", 1),
  (async () => {
    await new Promise((res) => setTimeout(res, 50));
    await worker("worker-B", 1);
  })(),
]);

section("순차 실행 — 첫 락 해제 후 두 번째 성공");
await worker("worker-A", 0.3);
await worker("worker-B", 0.3);

const cleanup = getClient();
await cleanup.connect();
await cleanup.del("lock:shared-resource");
await cleanup.close();
