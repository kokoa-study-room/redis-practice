/**
 * Reference: docs/01-data-types/02-list.md
 *
 * List 큐 — RPUSH/LPOP, BLPOP, LTRIM, LMOVE.
 */
import { withClient, section, getClient } from "../_common.mjs";

await withClient(async (r) => {
  section("RPUSH / LPOP — FIFO 큐");
  await r.del("jobs");
  await r.rPush("jobs", ["task-1", "task-2", "task-3"]);
  console.log("LLEN =", await r.lLen("jobs"));
  while (true) {
    const job = await r.lPop("jobs");
    if (!job) break;
    console.log("처리:", job);
  }

  section("LPUSH / LRANGE — 최근 N개 로그");
  await r.del("log");
  for (let i = 0; i < 20; i++) await r.lPush("log", `event-${i}`);
  await r.lTrim("log", 0, 9);
  console.log("최근 10개:", await r.lRange("log", 0, -1));

  section("BLPOP — 다른 producer가 push 할 때까지 대기");
  await r.del("waitq");

  // 별도 connection으로 producer (BLPOP은 connection을 점유함)
  const producer = getClient();
  await producer.connect();
  setTimeout(async () => {
    await producer.rPush("waitq", "delayed-task");
    await producer.close();
  }, 500);

  const result = await r.blPop("waitq", 3);
  console.log("BLPOP returned:", result);

  section("LMOVE — 신뢰성 큐 (src → dst, atomic)");
  await r.del(["src", "processing"]);
  await r.rPush("src", ["a", "b", "c"]);
  const item = await r.lMove("src", "processing", "LEFT", "RIGHT");
  console.log("이동:", item, "| processing =", await r.lRange("processing", 0, -1));
  await r.lRem("processing", 1, item);
  console.log("ack 후 processing =", await r.lRange("processing", 0, -1));

  section("정리");
  await r.del(["jobs", "log", "waitq", "src", "processing"]);
  console.log("done.");
});
