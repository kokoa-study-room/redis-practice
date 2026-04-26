/**
 * Reference: docs/00-getting-started/03-redis-cli-basics.md
 *
 * Redis 연결 + SET/GET/INCR + OBJECT ENCODING.
 * 실행: node ch00-getting-started/01-ping-and-set.mjs
 */
import { withClient, section } from "../_common.mjs";

await withClient(async (r) => {
  section("PING");
  console.log("PING ->", await r.ping());

  section("SET / GET");
  await r.set("hello", "안녕하세요 Redis!");
  console.log("GET hello ->", await r.get("hello"));

  section("INCR (원자성)");
  await r.set("counter", "0");
  for (let i = 0; i < 5; i++) await r.incr("counter");
  console.log("counter =", await r.get("counter"));

  section("OBJECT ENCODING");
  await r.set("short", "hi");
  await r.set("number", "12345");
  await r.set("long", "x".repeat(50));
  for (const k of ["short", "number", "long"]) {
    const enc = await r.sendCommand(["OBJECT", "ENCODING", k]);
    console.log(`${k.padStart(8)}  encoding= ${enc}`);
  }

  section("정리");
  await r.del(["hello", "counter", "short", "number", "long"]);
  console.log("done.");
});
