/**
 * Reference: docs/01-data-types/06-stream.md, docs/04-pubsub-streams/03-streams-consumer-group.md
 *
 * Stream + Consumer Group. 두 컨슈머가 메시지를 분배 받음.
 */
import { withClient, section, getClient } from "../_common.mjs";

const STREAM = "demo:tasks";
const GROUP = "workers";

async function consume(consumerName, maxMsgs) {
  const r = getClient();
  await r.connect();
  let consumed = 0;
  while (consumed < maxMsgs) {
    const resp = await r.xReadGroup(
      GROUP, consumerName,
      [{ key: STREAM, id: ">" }],
      { COUNT: 1, BLOCK: 2000 }
    );
    if (!resp || resp.length === 0) break;
    for (const stream of resp) {
      for (const msg of stream.messages) {
        console.log(`[${consumerName}] got ${msg.id} :: ${JSON.stringify(msg.message)}`);
        await r.xAck(STREAM, GROUP, msg.id);
        consumed++;
      }
    }
  }
  console.log(`[${consumerName}] consumed ${consumed} done`);
  await r.close();
}

await withClient(async (r) => {
  await r.del(STREAM);

  try {
    await r.xGroupCreate(STREAM, GROUP, "0", { MKSTREAM: true });
  } catch (_e) {
    // BUSYGROUP — 이미 존재
  }

  section("프로듀서가 10개 메시지 추가");
  for (let i = 0; i < 10; i++) {
    await r.xAdd(STREAM, "*", { task: `job-${i}` });
  }
  console.log("XLEN =", await r.xLen(STREAM));
});

section("두 컨슈머 동시 실행");
await Promise.all([consume("worker-A", 5), consume("worker-B", 5)]);

await withClient(async (r) => {
  section("그룹 상태");
  console.log(await r.xInfoGroups(STREAM));

  section("정리");
  await r.del(STREAM);
  console.log("done.");
});
