# 02. Node.js — node-redis 5.12 vs ioredis 5.10

> **학습 목표**: Node.js의 두 주요 Redis 클라이언트의 설계 철학 차이, 8.6 신기능 가용성, 클러스터/Sentinel 구성을 안다.
> **예상 소요**: 25분

---

## 1. 무엇을 골라야 하나?

| 상황 | 추천 |
|---|---|
| 새 프로젝트, Redis 8.6 신기능 적극 사용 | **node-redis 5+** |
| Cluster + Sentinel 위주, 안정성 검증된 패턴 | **ioredis 5+** |
| OpenTelemetry 통합 | **node-redis 5.12+** (내장) |
| 가장 많은 npm 다운로드 | 둘 다 메이저 (둘 다 redis/ org 산하) |
| EventEmitter 스타일 | ioredis |
| Promise/async-await 위주 | node-redis |

> 출처:
> - <https://github.com/redis/node-redis> (5.12 기준)
> - <https://github.com/redis/ioredis> (5.10 기준)

---

## 2. node-redis 5.12

### 설치
```bash
npm i redis@^5.12.0
```

### 기본
```javascript
import { createClient } from "redis";

const r = createClient({ url: "redis://127.0.0.1:6379" });
r.on("error", (err) => console.error("Redis Error", err));
await r.connect();

await r.set("name", "Kim");
console.log(await r.get("name"));   // "Kim"

await r.close();
```

### Pool

```javascript
import { createClientPool } from "redis";
const pool = createClientPool({ url: "redis://127.0.0.1:6379" }, { maximum: 20 });

await pool.set("k", 1);
console.log(await pool.get("k"));
```

### Pub/Sub

```javascript
const sub = r.duplicate();
await sub.connect();
await sub.subscribe("news", (msg) => console.log("got:", msg));

await r.publish("news", "Hello");
```

> `duplicate()` 로 동일 옵션 새 connection.

### Cluster

```javascript
import { createCluster } from "redis";
const cluster = createCluster({
  rootNodes: [
    { url: "redis://127.0.0.1:7001" },
    { url: "redis://127.0.0.1:7002" },
    { url: "redis://127.0.0.1:7003" },
  ],
});
await cluster.connect();
await cluster.set("foo", "bar");
```

### Redis 8.6 신기능 (5.11+)

```javascript
// XADD with IDMPAUTO
const id = await r.xAdd("events", "*", { user: "1", ev: "signup" }, {
  IDMPAUTO: { producer: "p1", iid: "msg-001" }
});

// HOTKEYS
await r.sendCommand(["HOTKEYS", "START", "10000"]);   // 10초간 추적 시작
await r.sendCommand(["HOTKEYS", "GET"]);              // 결과
```

> 출처: <https://github.com/redis/node-redis/releases/tag/redis%405.11.0>

---

## 3. ioredis 5.10

### 설치
```bash
npm i ioredis@^5.10.0
```

### 기본
```javascript
import Redis from "ioredis";

const r = new Redis({ host: "127.0.0.1", port: 6379 });
// connect() 호출 안 해도 됨 (lazy)

await r.set("name", "Kim");
console.log(await r.get("name"));   // "Kim"

await r.quit();
```

### Pipeline

```javascript
const pipe = r.pipeline();
for (let i = 0; i < 1000; i++) pipe.set(`k${i}`, String(i));
const results = await pipe.exec();
```

### Cluster

```javascript
import Redis from "ioredis";
const cluster = new Redis.Cluster([
  { host: "127.0.0.1", port: 7001 },
  { host: "127.0.0.1", port: 7002 },
]);
```

### Sentinel

```javascript
const r = new Redis({
  sentinels: [
    { host: "127.0.0.1", port: 26379 },
    { host: "127.0.0.1", port: 26380 },
    { host: "127.0.0.1", port: 26381 },
  ],
  name: "mymaster",
});
```

ioredis는 **Sentinel 지원이 잘 되어 있어 HA 환경에서 자주 선택**됨.

### Hash field TTL (ioredis 5.10+)

```javascript
await r.hset("user:1", "token", "xyz");
await r.hexpire("user:1", 30, "FIELDS", 1, "token");
```

> 출처: <https://github.com/redis/ioredis/releases/tag/v5.10.0> "add hash field expiration commands"

---

## 4. 두 클라이언트 비교 표

| 항목 | node-redis 5.12 | ioredis 5.10 |
|---|---|---|
| connect 호출 필요 | ✅ | ❌ (lazy) |
| TypeScript 타입 | 강함 (자동 생성) | 강함 |
| Sentinel | 지원 | 지원 (역사적으로 더 견고) |
| Cluster | 지원 | 지원 |
| Pub/Sub | duplicate() 권장 | 자동 처리 |
| Pipelining | Promise.all 또는 multi() | pipeline().exec() |
| Auto-pipelining | 같은 connection 자동 | enableAutoPipelining 옵션 |
| OpenTelemetry | 내장 (5.12+) | 외부 통합 필요 |
| Hash field TTL | hExpire (5.10+) | hexpire (5.10+) |
| Vector Set / IDMP / HOTKEYS | 명시 지원 (5.11+) | 부분 (sendCommand 으로 가능) |

---

## 5. 둘 다 쓸 때

성능 비교 / 마이그레이션 학습용으로 두 클라이언트 동시에 설치 가능 (본 프로젝트 examples/nodejs/package.json 참고).

```javascript
import { createClient } from "redis";
import IoRedis from "ioredis";

const a = createClient(); await a.connect();
const b = new IoRedis();

await Promise.all([a.set("a", 1), b.set("b", 2)]);
```

---

## 6. 흔한 함정

| 함정 | 설명 |
|---|---|
| node-redis: connect 안 함 | 명령이 안 감. v4+에서는 명시적 connect 필요. |
| ioredis: 종료 시 quit() 안 함 | Node 프로세스가 안 죽음. |
| Pub/Sub: 같은 connection으로 publish | node-redis: duplicate(), ioredis: 보통 자동. |
| Promise.all 안 씀 | 명령 직렬 실행. await Promise.all([...]) 으로 자동 pipelining. |
| 에러 핸들러 안 등록 | 'error' 이벤트 → unhandledException. 반드시 r.on("error", ...) |

---

## 7. 직접 해보기

1. node-redis와 ioredis로 같은 SET/GET → 둘 다 동작.
2. Pipeline 1000개 명령 시간 비교.
3. Cluster 띄우고 양쪽 클라이언트로 SET — MOVED 자동 처리.
4. Pub/Sub: subscriber/publisher 각각.
5. node-redis 5.11+ HOTKEYS START → 부하 후 GET → 결과.

---

## 8. 참고 자료

- **[GitHub] redis/node-redis 5.12.0**
  - URL: <https://github.com/redis/node-redis/releases/tag/redis%405.12.0>
  - 참고 부분: OTel 추가, sendCommand on multi — §2 근거

- **[GitHub] redis/node-redis 5.11.0**
  - URL: <https://github.com/redis/node-redis/releases/tag/redis%405.11.0>
  - 참고 부분: Redis 8.6 Support 섹션 — §2 8.6 신기능 근거

- **[GitHub] redis/ioredis 5.10.1**
  - URL: <https://github.com/redis/ioredis/releases/tag/v5.10.1>
  - 참고 부분: 최신 stable 변경 사항 — §3 근거
