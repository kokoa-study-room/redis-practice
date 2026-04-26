# 00. 시작하기 (Getting Started)

> **이 챕터의 목표**: Redis가 무엇이며 왜 빠른지 이해하고, 30분 안에 로컬에서 redis-cli와 RedisInsight로 같은 키를 양쪽에서 확인하기.

---

## 학습 순서

| # | 파일 | 다루는 것 | 소요 |
|---|---|---|---|
| 01 | [01-what-is-redis.md](01-what-is-redis.md) | Redis의 정체 / 왜 빠른가 / 안 쓰면 안되는 이유 | 15분 |
| 02 | [02-install-with-docker.md](02-install-with-docker.md) | docker compose로 환경 띄우기 | 10분 |
| 03 | [03-redis-cli-basics.md](03-redis-cli-basics.md) | redis-cli 연결 / 기본 명령 / `HELP` 활용 | 20분 |
| 04 | [04-redisinsight-tour.md](04-redisinsight-tour.md) | GUI 둘러보기 (Browser, Workbench, Profiler) | 15분 |

---

## 사전 준비

- Docker Desktop (또는 Docker Engine + Compose v2) 설치
- 인터넷 연결 (이미지 풀링용)
- 약 1GB 디스크 여유

검증:

```bash
docker --version              # Docker 버전 확인
docker compose version        # Compose v2 확인 (v1은 'docker-compose' 였음)
```

---

## 이 챕터를 마치면 …

- [ ] Redis가 인메모리 데이터 구조 서버라고 한 줄로 설명할 수 있다
- [ ] 왜 단일 스레드인데도 빠른지 두 가지 이유를 댈 수 있다
- [ ] `docker compose up -d` 후 `redis-cli ping` 이 `PONG` 을 반환하는지 확인한다
- [ ] RedisInsight (http://localhost:5540) 에서 `SET hello "world"` 결과를 본다
- [ ] `OBJECT ENCODING` 명령으로 같은 자료형이 인코딩에 따라 다르게 저장된다는 사실을 한 번이라도 본다

준비됐으면 [01-what-is-redis.md](01-what-is-redis.md) 부터 시작.
