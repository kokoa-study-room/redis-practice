/**
 * Reference: docs/07-performance/04-pipeline-and-batching.md
 *
 * Pipeline 으로 RTT 절감 측정. 1000개 SET — 세 가지 방법 비교.
 * node-redis 5+ 는 Promise.all 시 자동 pipelining (auto-pipelining).
 */
import { withClient, section } from "../_common.mjs";

const N = 1000;

async function timeIt(fn) {
  const t0 = process.hrtime.bigint();
  await fn();
  const t1 = process.hrtime.bigint();
  return Number(t1 - t0) / 1e6; // ms
}

await withClient(async (r) => {
  // 정리
  for await (const k of r.scanIterator({ MATCH: "pipe:*" })) {
    await r.del(k);
  }

  section(`${N}개 SET — 세 가지 방법 비교`);

  const tNaive = await timeIt(async () => {
    for (let i = 0; i < N; i++) {
      await r.set(`pipe:naive:${i}`, String(i));
    }
  });

  const tAutoPipe = await timeIt(async () => {
    const promises = [];
    for (let i = 0; i < N; i++) {
      promises.push(r.set(`pipe:autopipe:${i}`, String(i)));
    }
    await Promise.all(promises);
  });

  const tMulti = await timeIt(async () => {
    const multi = r.multi();
    for (let i = 0; i < N; i++) {
      multi.set(`pipe:multi:${i}`, String(i));
    }
    await multi.exec();
  });

  console.log(`  naive (각각 await):    ${tNaive.toFixed(1).padStart(8)} ms (${(N / tNaive * 1000).toFixed(0).padStart(9)} ops/sec)`);
  console.log(`  Promise.all (auto-pipe): ${tAutoPipe.toFixed(1).padStart(8)} ms (${(N / tAutoPipe * 1000).toFixed(0).padStart(9)} ops/sec)`);
  console.log(`  multi (transaction):   ${tMulti.toFixed(1).padStart(8)} ms (${(N / tMulti * 1000).toFixed(0).padStart(9)} ops/sec)`);
  console.log(`  → auto-pipe 이 naive 대비 ${(tNaive / tAutoPipe).toFixed(1)}x 빠름`);

  // 정리
  for await (const k of r.scanIterator({ MATCH: "pipe:*" })) {
    await r.del(k);
  }
});
