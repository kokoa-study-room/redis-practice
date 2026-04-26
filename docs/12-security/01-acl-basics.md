# 01. ACL 기초 — 사용자, 패스워드, 명령 권한

> **학습 목표**: Redis ACL 모델의 DSL을 읽고 쓸 수 있고, default user / requirepass 와 ACL의 관계, 28개 명령 카테고리를 이해해서 최소 권한 사용자를 만들 수 있다.
> **사전 지식**: 기본 redis-cli 사용
> **예상 소요**: 30분

---

## 1. 개념

> **ACL (Access Control List)**: Redis 6+ 기능. 사용자별로 어떤 명령을 어떤 키에 호출할 수 있는지 제한.

기본 사상:
- 모든 연결은 **사용자**에 묶인다 (인증 후).
- 사용자에는 **활성 여부 / 패스워드 / 명령 카테고리 / 키 패턴 / Pub/Sub 채널 패턴** 이 있다.
- 인증 없는 시점부터 어떤 사용자로 동작할지 = **default user** 의 설정.

> 출처: <https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/>

---

## 2. default user — 모든 보안의 출발점

```
> ACL LIST
1) "user default on nopass ~* &* +@all"
```

분해:
- `user default` — 사용자 이름
- `on` — 활성
- `nopass` — 패스워드 없음 (모든 패스워드로 인증 통과)
- `~*` — 모든 키 패턴 접근
- `&*` — 모든 Pub/Sub 채널 접근
- `+@all` — 모든 명령 카테고리 호출 가능

→ **신규 설치 직후의 Redis는 모든 명령에 인증 없이 접근 가능** (loopback 보호 빼고).
→ 첫 보안 작업: default user를 잠그거나 패스워드 부여.

```
ACL SETUSER default on >supersecret resetkeys ~* &* +@all
ACL SETUSER default off                        # 또는 완전 비활성
```

`requirepass <password>` 설정과 ACL 의 관계:
> `requirepass foo` 는 사실상 `ACL SETUSER default on >foo` 와 같다 (호환성을 위한 단축 표현).

---

## 3. 사용자 만들기 — `ACL SETUSER`

```
ACL SETUSER alice
ACL SETUSER alice on >p1pp0 ~cached:* +get
ACL LIST
```

**증분(incremental) 적용 주의**: 같은 사용자에 두 번 SETUSER 하면 누적된다.
```
ACL SETUSER bob +set
ACL SETUSER bob +get
# bob 은 이제 +set, +get 모두 보유
```

reset 하려면:
```
ACL SETUSER bob reset
ACL SETUSER bob on >pwd ~* +@read
```

---

## 4. 명령 카테고리 (28개)

`ACL CAT` 로 목록:
```
> ACL CAT
1) "keyspace"        # DEL, RENAME, EXISTS, KEYS, SCAN, EXPIRE, TTL, FLUSHALL...
2) "read"            # GET 류
3) "write"           # SET 류
4) "set" / "sortedset" / "list" / "hash" / "string" / "stream" / "bitmap" / "hyperloglog" / "geo"  # 자료형별
5) "pubsub"          # PUBLISH/SUBSCRIBE
6) "admin"           # CONFIG/REPLICAOF/DEBUG/SAVE/MONITOR/ACL/SHUTDOWN
7) "fast"            # O(1) 명령
8) "slow"            # 그 외
9) "blocking"        # BLPOP/XREAD BLOCK
10) "dangerous"      # FLUSHALL/MIGRATE/RESTORE/SORT/KEYS/CLIENT/DEBUG/CONFIG/SAVE/REPLICAOF
11) "connection"     # AUTH/SELECT/COMMAND/CLIENT/ECHO/PING
12) "transaction"    # WATCH/MULTI/EXEC
13) "scripting"      # EVAL/FCALL
14) "search" / "json" / "tdigest" / "cms" / "bloom" / "cuckoo" / "topk" / "timeseries"  # 모듈/내장 자료형
```

특정 카테고리의 명령 보기:
```
> ACL CAT geo
1) "geohash"  2) "georadius_ro"  3) "geopos"  4) "geoadd" ...
```

> 출처: <https://redis.io/docs/latest/commands/acl-cat/>
> 참고 부분: 28개 카테고리 목록 — 본 표 근거

---

## 5. 권한 부여 DSL

### 5.1 명령 권한
```
+<command>            # 명령 허용 (예: +get)
-<command>            # 명령 거부
+@<category>          # 카테고리 허용 (예: +@read)
-@<category>          # 카테고리 거부
+<command>|<sub>      # 서브명령 허용 (Redis 7+: +config|get)
-<command>|<sub>      # 서브명령 거부 (7+)
allcommands           # = +@all
nocommands            # = -@all
```

### 5.2 키 패턴
```
~<pattern>            # glob 패턴, 예: ~user:*
allkeys               # = ~*
resetkeys             # 기존 키 패턴 모두 제거
```

### 5.3 Pub/Sub 채널 패턴 (Redis 6.2+)
```
&<pattern>            # 예: &news.*
allchannels           # = &*
resetchannels         # 모두 제거
```

### 5.4 패스워드
```
><password>           # 평문 추가 (Redis 가 SHA256 해시로 저장)
<<password>           # 제거
#<sha256-hex>         # 미리 해시한 값 추가 (acl.conf 에 평문 저장 안 함)
nopass                # 패스워드 무용지물 — 누구나 인증
resetpass             # 모든 패스워드 + nopass 제거
```

### 5.5 활성 / reset
```
on / off              # 활성 여부
reset                 # 위의 resetpass + resetkeys + resetchannels + off + -@all
```

---

## 6. 실전 예 — 캐시 read-only 사용자

```
ACL SETUSER cache_reader on >cachepw ~cached:* +@read
```

- 활성 / 패스워드 cachepw / cached:* 패턴 키만 / read 카테고리 (+ 그에 속한 GET, MGET, EXISTS, TYPE, ...)

검증:
```
AUTH cache_reader cachepw
+OK

GET cached:user:1                  # OK
GET other:foo                      # (error) NOPERM ... access ... keys
SET cached:user:1 v                # (error) NOPERM ... no permissions to run 'set'
```

---

## 7. 실전 예 — 워커 (지정 큐만 처리)

```
ACL SETUSER worker on >workpw ~jobs:* +@list +@stream +@string
```

- jobs:* 키만, List/Stream/String 명령만.
- DANGEROUS 카테고리 (FLUSHALL 등)는 자동으로 제외 (포함 안 했으니).

---

## 8. 패스워드 저장 방식

Redis는 패스워드를 **SHA-256 해시**로만 저장.

```
> ACL GETUSER alice
...
"passwords"
1) "2d9c75273d72b32df726fb545c8a4edc719f0a95a6fd993950b10c474ad9c927"
...
```

해시만 직접 등록 가능 (acl.conf 에 평문 안 적기):
```
ACL SETUSER bob #2d9c75273d72b32df726fb545c8a4edc719f0a95a6fd993950b10c474ad9c927
```

---

## 9. AUTH 명령

```
AUTH <password>                   # default user로 인증 (구 방식, 호환)
AUTH <username> <password>        # 명시적 (Redis 6+)
HELLO 3 AUTH <user> <pwd>         # RESP3 + 인증 (한 번에)
```

응답:
- `+OK` — 성공
- `(error) WRONGPASS` — 패스워드 틀림
- `(error) WRONGTYPE Operation ...` — 다른 에러

---

## 10. 흔한 함정

| 함정 | 설명 |
|---|---|
| default user 그대로 두고 새 사용자 추가 | default 가 모든 권한이므로 보안 효과 없음. **default 도 제한 / off / 강한 패스워드** 필요. |
| `requirepass foo` 만 쓰고 ACL 무시 | 모든 클라이언트가 사실상 default user. 다중 앱이면 분리 필요. |
| `+@all -@dangerous` 후 모듈 명령 호출 | `+@all` 은 모든 카테고리 + 모듈. `-@dangerous` 는 모듈 명령은 안 막음. 모듈 사용 시 검토 필요. |
| `ACL SETUSER` 두 번 호출하면 reset 되는 줄 안다 | 누적된다. 명시적 reset 필요. |
| Cluster에서 ACL이 노드별 다름 | 각 노드에 동일 ACL을 적용해야 함. Cluster ACL 동기화는 자체 기능 없음 (operator/automation 필요). |

---

## 11. 직접 해보기

1. `ACL LIST` 출력 분해해 default 의 권한 확인.
2. cache_reader 사용자 만들고 권한 밖 명령 시도 → NOPERM 확인.
3. `ACL CAT dangerous` 출력 — 어떤 명령이 위험으로 분류되는지.
4. `ACL WHOAMI` 로 현재 사용자.
5. `ACL DELUSER cache_reader` → 삭제 후 다시 AUTH 시도.

---

## 12. 참고 자료

- **[공식 문서] ACL** — <https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/>
  - 참고 부분: ACL DSL, default user, requirepass 호환성 — §2~§5 근거

- **[공식 문서] ACL 명령군** — <https://redis.io/docs/latest/commands/acl-list/>, `/acl-setuser/`, `/acl-cat/`, `/acl-getuser/`, `/acl-whoami/`, `/acl-deluser/`
  - 참고 부분: 명령 정의 — §3, §6 근거

- **[공식 문서] AUTH (확장)** — <https://redis.io/docs/latest/commands/auth/>
  - 참고 부분: 두 인자 형식 — §9 근거

- **[블로그] antirez — Redis security incidents** — <http://antirez.com/news/96>
  - 참고 부분: 인터넷 노출 Redis 침해 사례 — README §보안 사고 시나리오 근거
