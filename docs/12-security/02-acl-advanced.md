# 02. ACL 심화 — Selectors, Key Permissions, Channel ACL, ACL File

> **학습 목표**: Redis 7.0+ 의 selectors / key 단위 read/write 분리, Pub/Sub channel ACL, 외부 ACL file 운용을 익힌다.
> **사전 지식**: 01-acl-basics.md
> **예상 소요**: 25분

---

## 1. Selectors (Redis 7.0+)

> 사용자에 **여러 권한 셋**을 OR 로 결합. 한 셋이라도 매칭하면 명령 허용.

```
ACL SETUSER alice on >pwd +get ~app1:* (+set ~app2:*)
```

분해:
- root 권한: `+get ~app1:*` → `GET app1:foo` 가능
- selector: `+set ~app2:*` → `SET app2:bar v` 가능
- 하지만 `GET app2:foo` 는 둘 다 매칭 안 됨 → 거부.

여러 selector 가능:
```
ACL SETUSER bob on >pwd +get ~r1:* (+set ~w1:*) (+@stream ~stream1:*)
```

수정 / 제거:
- selector 는 한번 만들면 **개별 수정 불가**.
- `clearselectors` 로 모두 삭제 후 재정의.

> 출처: <https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/#selectors>

---

## 2. Key Permissions — Read vs Write 분리 (Redis 7.0+)

기존: `~user:*` → 그 패턴의 키에 read/write 모두 가능.

세분화:
```
%R~<pattern>         # read 만 가능
%W~<pattern>         # write 만 가능
%RW~<pattern>        # = ~<pattern>
```

권한 매핑은 명령의 **key spec flags** 기준:
- read flag → `%R` 권한 필요
- write flag → `%W` 권한 필요
- read + write 둘 다 → 둘 다 필요

### 예: COPY src dst — src 는 read, dst 는 write
```
ACL SETUSER copier on >pwd +copy %R~src:* %W~dst:*
```

### 예: 캐시는 read만, 다른 패턴은 write 허용
```
ACL SETUSER svc on >pwd +@read +@write %R~cached:* %W~queue:*
# cached:* 는 GET 가능, queue:* 는 LPUSH 가능, 그 외는 모두 거부
```

### 주의: 일부 write 명령은 read도 묵시적으로 함
- `LPOP key` — 데이터 반환 (read) + 삭제 (write) → **둘 다 필요**.
- `LPUSH key v` — 길이만 반환 → write 만 필요.
- 명령별 확인: <https://redis.io/docs/latest/develop/reference/key-specs/>

---

## 3. Pub/Sub Channel ACL (Redis 6.2+)

```
&<pattern>            # 채널 패턴 추가
&*                    # 모든 채널
allchannels           # = &*
resetchannels         # 모두 제거
```

```
ACL SETUSER chatuser on >pwd +subscribe +unsubscribe +publish &chat.* &room.*
```

→ chat.lobby / room.123 등 SUBSCRIBE / PUBLISH 가능. system.* 등은 거부.

### 기본 동작 변화 (Redis 7.0)
- 6.2~6.x: 새 사용자는 `allchannels` 기본 (호환).
- 7.0+: 새 사용자는 `resetchannels` 기본 (안전).
- 변경: `acl-pubsub-default allchannels|resetchannels` 옵션.

### PSUBSCRIBE 의 차이
- `SUBSCRIBE foo` / `PUBLISH foo m` — `foo` 가 채널 패턴에 매칭하면 OK.
- `PSUBSCRIBE pat` — **사용자가 가진 채널 패턴이 pat 와 정확히 일치** 해야 함 (literal match).

---

## 4. 외부 ACL File 운용

방법 1: `redis.conf` 안에 직접 user 라인:
```
user default on nopass ~* &* +@all
user alice on >p1pp0 ~cached:* +get
```

방법 2: 별도 파일 + `aclfile` 옵션:
```
aclfile /etc/redis/users.acl
```

`users.acl`:
```
user default off
user alice on >p1pp0 ~cached:* +get
user worker on #2d9c75... ~jobs:* +@list +@stream
```

### CONFIG vs ACL FILE 모드
- `aclfile` 미설정: ACL 변경은 `CONFIG REWRITE` 로 redis.conf 에 저장.
- `aclfile` 설정: ACL 변경은 `ACL SAVE` 로 ACL 파일에만 저장. `CONFIG REWRITE` 는 ACL 안 건드림.

```
ACL SAVE                 # 메모리 → 파일
ACL LOAD                 # 파일 → 메모리 (다른 곳에서 직접 수정 후)
```

---

## 5. ACL Logging — 감사

```
ACL LOG                  # 최근 ACL 위반 시도 (NOPERM 등) 로그
ACL LOG RESET            # 로그 비움
```

각 항목:
```
1) "count":      5
2) "reason":     "command|key|channel|auth"
3) "context":    "toplevel|multi|lua|module"
4) "object":     "FLUSHALL"
5) "username":   "alice"
6) "age-seconds": 12.345
7) "client-info": "id=8 addr=...  ..."
```

운영에서 침입 시도 / 잘못 설정된 클라이언트 식별에 유용.

---

## 6. ACL_CAT 외에 명령 메타 확인

```
COMMAND DOCS GET                      # 명령 권한·인자 메타
COMMAND INFO GET                      # 간단 메타
COMMAND LIST FILTERBY ACLCAT @read    # @read 카테고리 명령만
```

---

## 7. Sentinel / Replica 의 ACL

### Sentinel
- Sentinel 자체에도 사용자 / 패스워드 (`sentinel auth-user`, `sentinel auth-pass`).
- Sentinel → master / replica 인증용.

### Replica
- master 가 `requirepass` 또는 ACL 사용자 요구 → replica 에 `masterauth <pwd>` 또는 `masteruser <name>` + `masterauth`.

### Cluster
- 노드 간 통신 (cluster bus)도 인증 필요 시 동일.
- TLS 와 함께 사용 권장 (다음 챕터).

---

## 8. 흔한 함정

| 함정 | 설명 |
|---|---|
| Selector 만들고 root 권한도 거기 옮긴 줄 안다 | root 권한과 selector 는 OR 결합. root 제한 안 하면 selector 무의미. |
| `%R` `%W` 헷갈림 | 명령의 key spec flag 기준. LPOP 같이 둘 다 필요한 명령 주의. |
| `&*` 미설정인데 PSUBSCRIBE 동작 | 7.0+ 에서는 default 가 resetchannels. 명시 채널 추가 필요. |
| ACL file과 CONFIG REWRITE 동시 사용 | aclfile 모드에선 CONFIG REWRITE 가 ACL 안 건드림. ACL SAVE 따로. |
| ACL LOG RESET 안 하면 누적 | 운영에서 정기 reset / 외부 수집. |
| Cluster 노드 간 ACL 자동 동기화 줄 안다 | 자동 동기화 없음. 운영자가 모든 노드에 동일 적용. |

---

## 9. 직접 해보기

1. selector 가진 사용자 만들기 → `ACL GETUSER` 로 구조 확인.
2. `%R` 와 `%W` 분리한 사용자 → COPY / LPOP 등 시도해서 NOPERM 발생 시점.
3. `acl-pubsub-default resetchannels` 설정 후 새 사용자 → SUBSCRIBE 시도.
4. aclfile 만들고 `ACL SAVE` / `ACL LOAD` 사이클.
5. 일부러 NOPERM 발생 → `ACL LOG` 확인.

---

## 10. 참고 자료

- **[공식 문서] ACL — Selectors / Key Permissions** — <https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/#selectors>
  - 참고 부분: 7.0+ selector / `%R`/`%W` 동작 — §1, §2 근거

- **[공식 문서] Key specifications** — <https://redis.io/docs/latest/develop/reference/key-specs/>
  - 참고 부분: read / write / insert / update / delete flag — §2 근거

- **[공식 문서] ACL LOG** — <https://redis.io/docs/latest/commands/acl-log/>
  - 참고 부분: reason / context / object — §5 근거

- **[공식 문서] ACL FILE 옵션** — <https://github.com/redis/redis/blob/8.6/redis.conf>
  - 참고 부분: aclfile 디렉티브 — §4 근거
