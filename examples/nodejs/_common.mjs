/**
 * Redis 학습 예제 공통 모듈 (node-redis 5.12).
 *
 * 환경변수 또는 .env 의 REDIS_URL 사용.
 * 모든 챕터 예제가 import { getClient } from '../_common.mjs' 형태로 사용.
 */
import "dotenv/config";
import { createClient } from "redis";

export function getClient() {
  const url = process.env.REDIS_URL || "redis://127.0.0.1:6379";
  const client = createClient({ url });
  client.on("error", (err) => console.error("Redis error:", err));
  return client;
}

export function section(title) {
  const line = "=".repeat(60);
  console.log(`\n${line}\n ${title}\n${line}`);
}

export async function withClient(fn) {
  const r = getClient();
  await r.connect();
  try {
    await fn(r);
  } finally {
    await r.close();
  }
}
