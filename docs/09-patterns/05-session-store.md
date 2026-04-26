# 05. Session Store

> **학습 목표**: Hash + TTL로 세션 저장, 슬라이딩 만료 (활동 시 TTL 갱신), CSRF 토큰 / 액세스 토큰 분리 패턴.
> **예상 소요**: 20분

---

## 1. 왜 Redis가 세션 저장에 적합

| 요구 | Redis가 만족? |
|---|---|
| 빠른 read/write (μs) | ✅ |
| TTL (자동 만료) | ✅ |
| 여러 웹 서버 공유 | ✅ |
| 영속성 (선택) | ✅ (RDB/AOF) |
| 부분 갱신 (슬라이딩 만료) | ✅ (EXPIRE / HEXPIRE) |

---

## 2. 단순 Session — String (JSON)

```python
import json, secrets

def create_session(user_id):
    sid = secrets.token_urlsafe(32)
    data = {"user_id": user_id, "created_at": time.time()}
    r.set(f"session:{sid}", json.dumps(data), ex=86400)   # 24시간
    return sid

def get_session(sid):
    raw = r.get(f"session:{sid}")
    if raw:
        r.expire(f"session:{sid}", 86400)               # 슬라이딩 만료
        return json.loads(raw)
    return None

def destroy(sid):
    r.delete(f"session:{sid}")
```

---

## 3. Hash 버전 (필드 부분 갱신 가능)

```python
def create_session(user_id):
    sid = secrets.token_urlsafe(32)
    r.hset(f"session:{sid}", mapping={
        "user_id": user_id,
        "created_at": int(time.time()),
        "last_active": int(time.time()),
        "csrf_token": secrets.token_urlsafe(32),
    })
    r.expire(f"session:{sid}", 86400)
    return sid

def touch(sid):
    """활동 시 last_active 갱신 + TTL 슬라이딩"""
    if r.exists(f"session:{sid}"):
        pipe = r.pipeline()
        pipe.hset(f"session:{sid}", "last_active", int(time.time()))
        pipe.expire(f"session:{sid}", 86400)
        pipe.execute()
        return True
    return False

def get_field(sid, field):
    return r.hget(f"session:{sid}", field)
```

장점:
- 필드 단위 부분 갱신
- 작은 세션은 listpack 인코딩 → 메모리 효율

---

## 4. Field-level TTL (Redis 7.4+) — 토큰 자동 만료

```python
# 액세스 토큰: 30분 후 만료
# 리프레시 토큰: 7일 후 만료
# 세션 메타: 30일 (가장 긴 거)

def create_session(user_id):
    sid = secrets.token_urlsafe(32)
    pipe = r.pipeline()
    pipe.hset(f"session:{sid}", mapping={
        "user_id": user_id,
        "access_token": "...",
        "refresh_token": "...",
    })
    pipe.hexpire(f"session:{sid}", 1800, "access_token")     # 30분
    pipe.hexpire(f"session:{sid}", 604800, "refresh_token")  # 7일
    pipe.expire(f"session:{sid}", 2592000)                   # 30일
    pipe.execute()
    return sid
```

→ access_token만 자동 사라지고 다른 필드는 유지.

> 출처: <https://redis.io/docs/latest/commands/hexpire/>

---

## 5. CSRF / 다중 디바이스

같은 사용자의 여러 세션 추적:
```python
def create_session(user_id):
    sid = secrets.token_urlsafe(32)
    r.hset(f"session:{sid}", mapping={"user_id": user_id})
    r.sadd(f"user_sessions:{user_id}", sid)
    r.expire(f"session:{sid}", 86400)
    return sid

def list_sessions(user_id):
    return r.smembers(f"user_sessions:{user_id}")

def destroy_all(user_id):
    sids = r.smembers(f"user_sessions:{user_id}")
    for sid in sids:
        r.delete(f"session:{sid}")
    r.delete(f"user_sessions:{user_id}")
```

---

## 6. 보안 권고

| 항목 | 권고 |
|---|---|
| Session ID | `secrets.token_urlsafe(32)` 정도. 추측 불가능. |
| 쿠키 | `HttpOnly`, `Secure`, `SameSite=Lax/Strict` |
| HTTPS | 프로덕션 필수 |
| Redis 자체 | TLS / AUTH / ACL / 외부 네트워크 차단 |
| 비밀 정보 저장 | 평문이면 Redis 메모리 dump 시 노출. 암호화 또는 별도 저장. |
| Session fixation | 로그인 시 새 SID 발급 |

---

## 7. 흔한 함정

| 함정 | 설명 |
|---|---|
| TTL 안 줌 | 영원히 누적. 반드시 EXPIRE. |
| 슬라이딩 만료를 SET 마다 | 연결 부담. 활동 단위로만 (15초마다 등). |
| Cluster에서 user_sessions:userid 와 session:sid 다른 슬롯 | hashtag로 묶거나 단일 키 모델로. |
| 세션 데이터에 거대 객체 | 매 요청에 GET → 네트워크 부담. 필요한 필드만 HGET. |
| 로그아웃 시 한 sid만 삭제 | 다른 디바이스 그대로 남음. 정책에 따라 destroy_all. |

---

## 8. 직접 해보기

1. session create → HGET 확인.
2. touch 로 슬라이딩 만료 → TTL 변화.
3. HEXPIRE access_token 5초 → 6초 후 HGET 결과.
4. user_sessions Set으로 다중 디바이스 시뮬레이션.
5. destroy_all 동작 확인.

---

## 9. 참고 자료

- **[공식 문서] HEXPIRE**
  - URL: <https://redis.io/docs/latest/commands/hexpire/>
  - 참고 부분: 7.4+ field TTL — §4 근거

- **[OWASP Session Management Cheat Sheet]**
  - URL: <https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html>
  - 참고 부분: ID 엔트로피, 쿠키 옵션, fixation — §6 근거
