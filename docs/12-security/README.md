# 12. 보안 (Security)

> **이 챕터의 목표**: Redis가 외부에 노출되거나 다중 사용자 환경에서 운영될 때 필요한 ACL, TLS, 위험 명령 제한, 인증·권한 모델을 모두 다룬다. Redis 침해 사고는 대부분 이 챕터의 내용을 모르거나 무시해서 발생한다.

---

## 학습 순서

| # | 파일 | 핵심 |
|---|---|---|
| 01 | [01-acl-basics.md](01-acl-basics.md) | ACL 모델, 28개 명령 카테고리, 사용자 / 패스워드 / 키 패턴 |
| 02 | [02-acl-advanced.md](02-acl-advanced.md) | Selectors (7+), key permissions (%R/%W), Pub/Sub channel ACL, ACL file |
| 03 | [03-tls.md](03-tls.md) | mutual TLS, replication / cluster bus / sentinel TLS, perf 영향 |
| 04 | [04-dangerous-commands.md](04-dangerous-commands.md) | rename-command, default user, requirepass vs ACL, audit |

---

## 보안 사고 시나리오 (왜 이 챕터인가?)

| 사고 | 원인 | 본 챕터의 해결 |
|---|---|---|
| Redis가 인터넷 공개 + 인증 없음 → 데이터 유출 / 채굴기 설치 | bind 0.0.0.0 + protected-mode off + 패스워드 없음 | 01, 04 |
| 한 클라이언트가 실수로 FLUSHALL → 운영 데이터 전부 삭제 | 모든 클라이언트가 default user (모든 권한) | 01, 04 |
| ACL 추가했는데 Pub/Sub 채널은 그대로 노출 | channel 권한 누락 (acl-pubsub-default) | 02 |
| Cluster bus 가 평문 → 노드 간 데이터 도청 | tls-cluster yes 누락 | 03 |
| GitHub에 redis URL 포함 패스워드 노출 | requirepass 만 사용 + 평문 저장 | 04 |

---

## 먼저 알아야 할 것

- **Redis 6 부터 ACL이 표준**. 7.0 부터는 selectors / key permissions / 더 세밀한 모델.
- **TLS는 Redis 6 부터** 컴파일 옵션으로 지원. 8.0 부터는 I/O threading + TLS 호환.
- **default user**의 동작 방식이 모든 보안 모델의 출발점.

> 출처: <https://redis.io/docs/latest/operate/oss_and_stack/management/security/>
