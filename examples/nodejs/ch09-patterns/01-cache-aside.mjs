/**
 * Reference: docs/09-patterns/01-cache-aside.md
 *
 * Cache-aside + negative caching.
 */
import { withClient, section } from "../_common.mjs";

const CACHE_TTL = 30;
const NULL_TTL = 5;
const NULL_MARKER = "__NULL__";

const _DB = new Map([
  [1, { id: 1, name: "Alice" }],
  [2, { id: 2, name: "Bob" }],
]);
let _DB_HITS = 0;

async function dbFetch(userId) {
  _DB_HITS++;
  await new Promise((res) => setTimeout(res, 50)); // 50ms 시뮬
  return _DB.get(userId);
}

async function getUser(r, userId) {
  const key = `user:${userId}`;
  const cached = await r.get(key);
  if (cached === NULL_MARKER) return null;
  if (cached) return JSON.parse(cached);

  const user = await dbFetch(userId);
  if (user === undefined) {
    await r.set(key, NULL_MARKER, { EX: NULL_TTL });
    return null;
  }
  await r.set(key, JSON.stringify(user), { EX: CACHE_TTL });
  return user;
}

async function updateUser(r, userId, data) {
  Object.assign(_DB.get(userId), data);
  await r.del(`user:${userId}`);
}

await withClient(async (r) => {
  section("처음 read — DB 호출 (cache miss)");
  _DB_HITS = 0;
  for (let i = 0; i < 5; i++) {
    console.log("got:", await getUser(r, 1));
  }
  console.log(`DB hits: ${_DB_HITS} (1번이어야 정상)`);

  section("update 후 read — 무효화 + 재조회");
  _DB_HITS = 0;
  await updateUser(r, 1, { name: "Alice-Renamed" });
  console.log("after update:", await getUser(r, 1));
  console.log(`DB hits: ${_DB_HITS} (1번이어야 정상)`);

  section("없는 ID — negative caching");
  _DB_HITS = 0;
  for (let i = 0; i < 5; i++) {
    console.log("got:", await getUser(r, 999));
  }
  console.log(`DB hits: ${_DB_HITS} (1번이어야 정상)`);

  section("정리");
  await r.del(["user:1", "user:2", "user:999"]);
  console.log("done.");
});
