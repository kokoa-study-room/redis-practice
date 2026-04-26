/**
 * Reference: docs/01-data-types/01-string.md
 *
 * String SET/GET, 만료, INCR, APPEND, MSET/MGET, embstr/raw 인코딩.
 */
import { withClient, section } from "../_common.mjs";

await withClient(async (r) => {
  section("SET / GET / EX / NX");
  await r.set("greeting", "Hello", { EX: 10 });
  console.log("greeting =", await r.get("greeting"), "TTL=", await r.ttl("greeting"));

  const first = await r.set("lock:demo", "client-1", { NX: true, EX: 30 });
  const second = await r.set("lock:demo", "client-2", { NX: true, EX: 30 });
  console.log("first lock ->", first);
  console.log("second lock (이미 있음) ->", second);

  section("INCR / DECR / INCRBYFLOAT");
  await r.set("visits", "0");
  await r.incr("visits");
  await r.incrBy("visits", 10);
  await r.incrByFloat("visits", 0.5);
  console.log("visits =", await r.get("visits"));

  section("APPEND / STRLEN / GETRANGE");
  await r.set("msg", "hello");
  await r.append("msg", " world");
  console.log("msg =", await r.get("msg"), "len=", await r.strLen("msg"));
  console.log("msg[0:4] =", await r.getRange("msg", 0, 4));

  section("MSET / MGET");
  await r.mSet({ a: "1", b: "2", c: "3" });
  console.log(await r.mGet(["a", "b", "c", "missing"]));

  section("Encoding 전환 (int / embstr / raw)");
  for (const [k, v] of [
    ["k_int", "42"],
    ["k_emb", "short"],
    ["k_raw", "x".repeat(100)],
  ]) {
    await r.set(k, v);
    const enc = await r.sendCommand(["OBJECT", "ENCODING", k]);
    console.log(`${k} (${JSON.stringify(v).slice(0, 20).padStart(22)}) -> ${enc}`);
  }

  section("정리");
  await r.del(["greeting", "lock:demo", "visits", "msg",
               "a", "b", "c", "k_int", "k_emb", "k_raw"]);
  console.log("done.");
});
