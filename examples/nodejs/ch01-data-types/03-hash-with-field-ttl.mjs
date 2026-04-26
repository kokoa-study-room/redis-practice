/**
 * Reference: docs/01-data-types/03-hash.md
 *
 * Hash + Redis 7.4+ field-level TTL (HEXPIRE).
 */
import { withClient, section } from "../_common.mjs";

const KEY = "user:1001";

await withClient(async (r) => {
  section("HSET / HGETALL");
  await r.del(KEY);
  await r.hSet(KEY, {
    name: "Kim",
    email: "k@example.com",
    level: "10",
  });
  console.log(await r.hGetAll(KEY));

  section("HINCRBY / HMGET");
  await r.hIncrBy(KEY, "level", 5);
  console.log(await r.hmGet(KEY, ["name", "level"]));

  section("Field-level TTL (Redis 7.4+) — token 5초 후 자동 삭제");
  await r.hSet(KEY, "session_token", "xyz789");
  try {
    await r.hExpire(KEY, "session_token", 5);
    const ttl = await r.hTTL(KEY, "session_token");
    console.log("session_token TTL(s):", ttl);
    console.log("HGETALL 직후:", await r.hGetAll(KEY));

    await new Promise((res) => setTimeout(res, 6000));
    console.log("6초 후 HGETALL (token만 사라져야 함):", await r.hGetAll(KEY));
  } catch (e) {
    console.log("HEXPIRE 미지원 (Redis 7.4 미만 또는 클라이언트):", e.message);
  }

  section("HSCAN — 큰 Hash 안전 순회");
  await r.del("big_hash");
  const fields = {};
  for (let i = 0; i < 50; i++) fields[`f${i}`] = String(i);
  await r.hSet("big_hash", fields);

  let cursor = "0";
  let seen = 0;
  do {
    const res = await r.hScan("big_hash", cursor, { COUNT: 10 });
    cursor = res.cursor;
    seen += res.tuples.length;
  } while (cursor !== "0");
  console.log(`순회 끝 (seen=${seen})`);

  section("Encoding 전환 (listpack → hashtable)");
  await r.del("h_small");
  await r.hSet("h_small", { a: "1", b: "2" });
  console.log("작은 Hash:", await r.sendCommand(["OBJECT", "ENCODING", "h_small"]));
  await r.hSet("h_small", "big", "x".repeat(200));
  console.log("긴 값 추가 후:", await r.sendCommand(["OBJECT", "ENCODING", "h_small"]));

  section("정리");
  await r.del([KEY, "big_hash", "h_small"]);
  console.log("done.");
});
