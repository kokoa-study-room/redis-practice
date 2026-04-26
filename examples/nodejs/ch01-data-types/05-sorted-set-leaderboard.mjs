/**
 * Reference: docs/01-data-types/05-sorted-set.md, docs/09-patterns/04-leaderboard.md
 *
 * ZSET 으로 게임 리더보드. TOP-N, 순위, 주변 ±N명, GT 옵션.
 */
import { withClient, section } from "../_common.mjs";

const KEY = "lb:demo";

await withClient(async (r) => {
  await r.del(KEY);

  section("ZADD — 점수 추가");
  await r.zAdd(KEY, [
    { score: 1500, value: "alice" },
    { score: 2300, value: "bob" },
    { score: 980,  value: "carol" },
    { score: 1875, value: "dave" },
    { score: 2750, value: "eve" },
  ]);
  console.log("ZCARD =", await r.zCard(KEY));

  section("TOP 3 (내림차순)");
  const top = await r.zRangeWithScores(KEY, 0, 2, { REV: true });
  top.forEach((row, i) => {
    console.log(`${i + 1}. ${row.value.padStart(6)} : ${String(row.score).padStart(5)}`);
  });

  section("alice 순위 + 주변 ±2명");
  const rank = await r.zRevRank(KEY, "alice");
  console.log("alice 등수:", rank + 1);
  const neighbors = await r.zRangeWithScores(
    KEY, Math.max(0, rank - 2), rank + 2, { REV: true }
  );
  neighbors.forEach((row, idx) => {
    const r_ = Math.max(0, rank - 2) + idx + 1;
    const arrow = row.value === "alice" ? " ← me" : "";
    console.log(`${r_}. ${row.value.padStart(6)} : ${String(row.score).padStart(5)}${arrow}`);
  });

  section("ZINCRBY — alice 점수 +500");
  await r.zIncrBy(KEY, 500, "alice");
  console.log("alice score:", await r.zScore(KEY, "alice"));
  console.log("새 등수:", (await r.zRevRank(KEY, "alice")) + 1);

  section("ZADD GT — 새 점수가 더 클 때만");
  await r.zAdd(KEY, [{ score: 100, value: "bob" }], { GT: true });
  console.log("bob score (변화 없어야 함):", await r.zScore(KEY, "bob"));

  section("TOP-N 자동 유지 — 상위 3만");
  await r.zRemRangeByRank(KEY, 0, -4);
  console.log("남은 멤버:", await r.zRangeWithScores(KEY, 0, -1, { REV: true }));

  section("정리");
  await r.del(KEY);
  console.log("done.");
});
