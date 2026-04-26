/**
 * Reference: docs/04-pubsub-streams/01-pubsub.md
 *
 * Pub/Sub: subscribe / publish 별도 connection. node-redis duplicate() 사용.
 */
import { getClient, section } from "../_common.mjs";

const N_MSGS = 5;

const pub = getClient();
await pub.connect();

const sub = pub.duplicate();
await sub.connect();

let seen = 0;
const done = new Promise((resolve) => {
  sub.subscribe("news", async (msg) => {
    console.log(`[sub] got: ${msg}`);
    seen++;
    if (seen >= N_MSGS) resolve();
  });
});

section(`Pub/Sub — ${N_MSGS}개 메시지`);
await new Promise((res) => setTimeout(res, 200)); // subscriber 준비

for (let i = 0; i < N_MSGS; i++) {
  const count = await pub.publish("news", `breaking-${i}`);
  console.log(`[pub] sent (received by ${count} subscriber)`);
  await new Promise((res) => setTimeout(res, 150));
}

await done;

section("PUBSUB 진단");
console.log("CHANNELS:", await pub.pubSubChannels());
console.log("NUMSUB news:", await pub.pubSubNumSub("news"));

await sub.unsubscribe();
await sub.close();
await pub.close();
