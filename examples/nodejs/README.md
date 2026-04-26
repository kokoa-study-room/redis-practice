# Node.js 예제 (node-redis + ioredis)

> **주 클라이언트**: [node-redis 5.12.0](https://github.com/redis/node-redis/releases/tag/redis%405.12.0) (2026-04-14)
> **비교 클라이언트**: [ioredis 5.10.1](https://github.com/redis/ioredis/releases/tag/v5.10.1) (2026-03-19)
> **Node.js 요구**: 20.x LTS 이상
> **참고 문서**: <https://redis.io/docs/latest/develop/clients/nodejs/>

본 디렉토리는 [docs/](../../docs) 하위 챕터의 redis-cli 예제를 Node.js로 재현한 것이다.

---

## 0. 어떤 클라이언트를 써야 하나?

| 항목 | node-redis (`redis`) | ioredis |
|---|---|---|
| 패키지명 | `redis` (npm) | `ioredis` |
| 유지보수 | Redis Inc. 공식 | Redis Inc. 공식 (구 luin/ioredis) |
| Redis 8.6 명시 지원 | ✅ 5.11.0+ (HOTKEYS, XADD IDMP/IDMPAUTO 등) | 부분 (HEXPIRE 등 5.10.0 추가) |
| 설계 철학 | Promise / async-await 우선 | EventEmitter + Promise 혼합 |
| OpenTelemetry | ✅ 5.12.0+ 내장 | 외부 통합 |
| 클러스터 | 지원 | 지원 (역사적으로 더 견고하다는 평가) |
| 추천 사용처 | 신규 프로젝트, Redis 8 신기능 | 기존 코드베이스, 클러스터 중심 |

> 본 학습 프로젝트는 **node-redis를 주 예제**로 쓰고, 같은 기능을 ioredis로 재구성한 비교 예제를 일부 챕터에 둔다.
> 참고: <https://github.com/redis/node-redis/releases/tag/redis%405.11.0> (Redis 8.6 지원 명세)

---

## 1. 환경 준비

```bash
cd examples/nodejs
npm install
# 또는 pnpm install / yarn install
```

Redis가 떠 있는지 확인:

```bash
npm run test:ping
# 기대 결과: PONG
```

---

## 2. 디렉토리 구조 (실제 작성된 파일)

```
examples/nodejs/
├── package.json
├── README.md (본 문서)
├── .env.example
├── .nvmrc
├── _common.mjs                       # withClient() / section() 공통 헬퍼
├── ch00-getting-started/
│   └── 01-ping-and-set.mjs
├── ch01-data-types/
│   ├── 01-string-basics.mjs
│   ├── 02-list-queue.mjs
│   ├── 03-hash-with-field-ttl.mjs
│   ├── 05-sorted-set-leaderboard.mjs
│   └── 06-stream-consumer-group.mjs
├── ch04-pubsub-streams/
│   └── 01-pubsub.mjs
├── ch05-transactions-scripting/
│   └── 01-lua-token-bucket.mjs
├── ch07-performance/
│   └── 01-pipeline-demo.mjs
└── ch09-patterns/
    ├── 01-cache-aside.mjs
    └── 03-distributed-lock.mjs
```

> Python 디렉토리와 1:1 매칭. 핵심 자료형 + 패턴 + Pub/Sub + Lua + Pipeline = 10개 단독 실행 파일.

각 파일은:
1. 첫 줄 JSDoc 주석에 매칭 문서 경로 명시 (`/** Reference: docs/01-data-types/01-string.md */`)
2. `node ch01-data-types/01-string-basics.mjs` 식으로 단독 실행
3. `_common.mjs` 의 `withClient(async (r) => {...})` 사용 (자동 connect/close)
4. `.env` 자동 로딩 (`REDIS_URL` 등)

---

## 3. 실행 예

```bash
# Hello World
node ch00-getting-started/01-ping-and-set.mjs

# String + encoding
node ch01-data-types/01-string-basics.mjs

# Stream + Consumer Group
node ch01-data-types/06-stream-consumer-group.mjs

# Pipeline (Promise.all 자동 파이프라이닝 효과)
node ch07-performance/01-pipeline-demo.mjs

# Cache-aside
node ch09-patterns/01-cache-aside.mjs

# 분산 락
node ch09-patterns/03-distributed-lock.mjs
```

---

## 4. 빠른 예시 (ioredis 비교)

```javascript
// ch08-clients/ioredis-vs-node-redis.mjs (발췌)
import Redis from "ioredis";

const redis = new Redis({ host: "127.0.0.1", port: 6379 });
await redis.set("greeting", "ioredis 사용 예");
console.log(await redis.get("greeting"));
await redis.quit();
```

> ioredis는 connect() 호출 없이 곧바로 사용 가능 (lazy connect 기본).
> `await redis.quit()` 으로 우아하게 종료한다.

---

## 5. Redis 8.6 신기능 사용 예 (node-redis)

```javascript
// XADD with IDMPAUTO (멱등성 보장)
import { createClient } from "redis";

const client = createClient();
await client.connect();

// IDMPAUTO: 같은 producer/iid 조합이 들어오면 중복 추가 없이 기존 ID 반환
const id = await client.xAdd(
  "mystream",
  "*",
  { field: "value" },
  { IDMPAUTO: { producer: "p1", iid: "msg-001" } }
);
console.log("Stream ID:", id);

await client.close();
```

> 출처: <https://github.com/redis/node-redis/releases/tag/redis%405.11.0> "XADD idempotency options" 섹션

---

## 6. ESM only

`package.json`에서 `"type": "module"` 을 쓰므로 모든 예제는 `.mjs` 확장자나 ESM `import` 문법을 사용한다.
CommonJS 예제가 필요하면 별도 `.cjs` 파일로 추가한다.

---

## 7. 참고 자료 (References)

- **[GitHub] redis/node-redis releases** — <https://github.com/redis/node-redis/releases>
  - 참고 부분: `redis@5.11.0` 릴리즈 노트의 "Redis 8.6 Support" 단락 — 본 문서의 8.6 신기능 지원 표 작성 근거
- **[GitHub] redis/ioredis releases** — <https://github.com/redis/ioredis/releases>
  - 참고 부분: `v5.10.0` 릴리즈 노트의 "add hash field expiration commands" 단락 — ioredis Hash TTL 지원 명시
- **[공식 문서] Redis Node.js Client Guide** — <https://redis.io/docs/latest/develop/clients/nodejs/>
  - 참고 부분: "Connect to Redis" 단락 — createClient 사용법
