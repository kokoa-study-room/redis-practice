# 10. 생태계 (Ecosystem)

> **이 챕터의 목표**: 2024년 라이선스 변경 이후의 Redis vs Valkey 구도, Redis Stack / 모듈(RediSearch / RedisJSON / RedisTimeSeries / RedisBloom) 의 위상을 이해한다.

---

## 학습 순서

| # | 파일 | 핵심 |
|---|---|---|
| 01 | [01-license-and-valkey.md](01-license-and-valkey.md) | RSAL/SSPL 라이선스 변경, Valkey 포크, 호환성 |
| 02 | [02-redis-stack-and-modules.md](02-redis-stack-and-modules.md) | Stack 통합 vs 모듈 / 8.x에서 흡수된 기능 |

---

## 한눈에

- **Redis 8.x (OSS)** : Vector Set, Hash field TTL, RediSearch / RedisJSON / RedisTimeSeries / RedisBloom 흡수
- **Redis Stack** : 위 기능들을 하나의 배포판으로 (호환성 / 마이그레이션용으로 여전히 유용)
- **Valkey** : 2024년 BSD 라이선스 포크, AWS / 구글 / Oracle 후원
