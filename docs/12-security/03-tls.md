# 03. TLS — 통신 암호화

> **학습 목표**: Redis TLS 활성화, 클라이언트 / replication / cluster bus / sentinel 의 TLS 옵션, mutual TLS, 성능 영향을 이해한다.
> **예상 소요**: 25분

---

## 1. 개념

> Redis 6+ 부터 **OpenSSL 기반 TLS** 를 옵션으로 지원. Redis 8.0+ 부터는 **I/O threading + TLS 호환**.

- 컴파일 시 활성화 필요: `make BUILD_TLS=yes`
- 기본 Docker 이미지 (`redis:8.6-alpine`)는 TLS 빌드 포함. 옵션만 켜면 됨.
- 기본 모드: **mutual TLS** (서버 + 클라이언트 모두 인증서 검증).

> 출처: <https://redis.io/docs/latest/operate/oss_and_stack/management/security/encryption/>

---

## 2. 인증서 준비 (학습용 self-signed)

`redis/utils/gen-test-certs.sh` 가 redis 소스에 포함되어 학습용 인증서를 생성한다.
간단히 수동으로:

```bash
# CA
openssl req -x509 -newkey rsa:4096 -keyout ca.key -out ca.crt \
    -days 3650 -nodes -subj "/CN=Test-CA"

# Server cert
openssl req -newkey rsa:4096 -keyout redis.key -out redis.csr \
    -nodes -subj "/CN=redis-server"
openssl x509 -req -in redis.csr -CA ca.crt -CAkey ca.key \
    -CAcreateserial -out redis.crt -days 365

# Client cert
openssl req -newkey rsa:4096 -keyout client.key -out client.csr \
    -nodes -subj "/CN=client"
openssl x509 -req -in client.csr -CA ca.crt -CAkey ca.key \
    -CAcreateserial -out client.crt -days 365
```

---

## 3. 서버 측 — redis.conf

```
# TLS만 사용 (평문 포트 끄기)
port 0
tls-port 6379

tls-cert-file /etc/redis/tls/redis.crt
tls-key-file  /etc/redis/tls/redis.key
tls-ca-cert-file /etc/redis/tls/ca.crt

# 또는 여러 CA 디렉토리
# tls-ca-cert-dir /etc/redis/tls/cas

# (선택) DH 파라미터
# tls-dh-params-file /etc/redis/tls/redis.dh

# 클라이언트 인증서 요구 (mutual TLS, 기본 yes)
tls-auth-clients yes
# tls-auth-clients no       # 클라이언트 인증서 안 받음 (서버 인증서만 검증)
# tls-auth-clients optional # 있으면 검증, 없어도 OK

# 프로토콜 / 사이퍼 (필요 시)
tls-protocols "TLSv1.2 TLSv1.3"
# tls-ciphers DEFAULT
# tls-ciphersuites TLS_CHACHA20_POLY1305_SHA256
```

---

## 4. 클라이언트 — redis-cli

```bash
redis-cli --tls \
    --cert client.crt \
    --key client.key \
    --cacert ca.crt \
    -h 127.0.0.1 -p 6379

# tls-auth-clients no 인 경우:
redis-cli --tls --cacert ca.crt -h 127.0.0.1 -p 6379
```

---

## 5. 클라이언트 라이브러리

### Python (redis-py)
```python
import redis
import ssl

r = redis.Redis(
    host="127.0.0.1", port=6379,
    ssl=True,
    ssl_ca_certs="ca.crt",
    ssl_certfile="client.crt",
    ssl_keyfile="client.key",
    ssl_cert_reqs=ssl.CERT_REQUIRED,
    decode_responses=True,
)
print(r.ping())
```

### Node.js (node-redis 5+)
```javascript
import { createClient } from "redis";
import fs from "node:fs";

const r = createClient({
  socket: {
    host: "127.0.0.1",
    port: 6379,
    tls: true,
    ca: fs.readFileSync("ca.crt"),
    cert: fs.readFileSync("client.crt"),
    key: fs.readFileSync("client.key"),
  },
});
await r.connect();
```

URL 형식 (rediss://):
```javascript
createClient({ url: "rediss://127.0.0.1:6379", socket: { tls: true, ... } });
```

---

## 6. Replication TLS

마스터의 `tls-port` 를 켰으면, 레플리카에서 마스터와 통신 시 TLS 사용 명시:

```
# replica 측
tls-replication yes

# replica → master 인증서 (서버 검증)
tls-cert-file ...
tls-key-file ...
tls-ca-cert-file ...
masterauth <password>     # ACL/패스워드 있으면
```

---

## 7. Cluster Bus TLS

각 노드 간 cluster bus (포트 + 10000) 도 TLS 강제:

```
tls-cluster yes
```

→ 클러스터 간 데이터 동기화 / gossip 메시지가 모두 암호화.

**중요**: 모든 노드가 동시에 활성. 일부만 켜면 통신 깨짐.

---

## 8. Sentinel TLS

Sentinel 은 Redis와 같은 옵션 상속:
- `tls-port` 켜면 Sentinel 자체가 TLS 포트로.
- `tls-replication yes` 면 master 와의 통신이 TLS.
- Sentinel 간 통신도 자동.

---

## 9. 성능 영향

TLS는 다음 비용 발생:
- TLS handshake (연결 시 1회, ~수 RTT)
- 암호화 / 복호화 (매 명령)
- 무결성 검사

대략적 영향:
- **단일 연결 throughput**: 30~50% 감소 가능 (워크로드에 따라)
- **연결 비용**: 매 connect 마다 +수 ms
- **CPU**: 평문 대비 1.5~2x 사용

완화책:
- **Connection pool / keep-alive** — TLS handshake 비용을 분산
- **Pipelining** — 같은 connection 으로 batch
- **Redis 8.0+ I/O threading + TLS** — multi-core 활용
- **하드웨어 가속** (AES-NI 같은 CPU 명령어셋 사용)

> 출처: <https://github.com/redis/redis/issues/7595>
> 참고 부분: TLS 성능 영향에 대한 공식 discussion

---

## 10. Docker compose 예 (TLS 활성화)

```yaml
services:
  redis-tls:
    image: redis:8.6-alpine
    command: >
      redis-server
        --port 0
        --tls-port 6379
        --tls-cert-file /tls/redis.crt
        --tls-key-file /tls/redis.key
        --tls-ca-cert-file /tls/ca.crt
        --tls-auth-clients yes
    volumes:
      - ./tls:/tls:ro
    ports: ["127.0.0.1:6379:6379"]
```

연결:
```bash
docker exec redis-tls redis-cli --tls \
  --cert /tls/client.crt --key /tls/client.key --cacert /tls/ca.crt PING
```

---

## 11. 흔한 함정

| 함정 | 설명 |
|---|---|
| 빌드에 BUILD_TLS=yes 안 함 | 옵션 자체가 인식 안 됨. 공식 docker 이미지는 포함. |
| 평문 포트 안 끄고 TLS만 추가 | 평문 6379도 살아있어 보안 효과 없음. `port 0` 명시. |
| `tls-auth-clients no` + 패스워드 없음 | 서버 신원만 확인. 클라이언트는 누구나. → ACL 필수. |
| 인증서 만료 | 자동 갱신 / 모니터링 필요. expire 후 갑자기 통신 끊김. |
| Cluster bus TLS 일부만 적용 | 노드 간 통신 깨짐 → split-brain. 동시 적용. |
| 성능 저하를 모르고 TLS 켬 | benchmark 로 비교 후 capacity 재산정. |
| `rediss://` 와 `redis://` 헷갈림 | rediss = TLS, redis = 평문. URL 표준. |

---

## 12. 직접 해보기

1. self-signed 인증서 만들고 단일 Redis TLS 활성화 → redis-cli 로 PING.
2. Python에서 TLS 연결 + ping.
3. `tls-auth-clients no` 모드로도 시도 → 클라이언트 cert 없이 연결되는지.
4. `redis-benchmark --tls` vs 평문 → throughput 비교.
5. (도전) 두 노드 + replication TLS 켜고 master/replica 동기화 확인.

---

## 13. 참고 자료

- **[공식 문서] TLS** — <https://redis.io/docs/latest/operate/oss_and_stack/management/security/encryption/>
  - 참고 부분: tls-port / tls-cert-file / tls-replication / tls-cluster — §3, §6, §7 근거

- **[GitHub Issue] TLS performance impact** — <https://github.com/redis/redis/issues/7595>
  - 참고 부분: throughput 감소 측정치 — §9 근거

- **[공식 문서] Sentinel TLS 설정** — 공식 sentinel docs (위 페이지에서 inherited 명시)
  - 참고 부분: replication 옵션 상속 — §8 근거

- **[redis-py docs] SSL/TLS connections** — <https://redis.readthedocs.io/en/stable/connections.html#ssl-tls-connections>
  - 참고 부분: ssl_certfile / ssl_keyfile / ssl_ca_certs — §5 Python 근거

- **[node-redis] TLS connection** — <https://github.com/redis/node-redis>
  - 참고 부분: socket.tls / ca / cert / key 옵션 — §5 Node 근거
