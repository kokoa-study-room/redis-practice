# 04. 위험 명령 제한 + 보안 운영 체크리스트

> **학습 목표**: rename-command / 위험 카테고리 제한 / default user 잠금 등 즉시 적용할 수 있는 보안 강화책과 운영 체크리스트를 익힌다.
> **예상 소요**: 20분

---

## 1. rename-command — 명령 자체를 숨기기

`redis.conf`:
```
rename-command FLUSHALL ""              # 사실상 비활성
rename-command FLUSHDB  ""
rename-command CONFIG   ""

rename-command DEBUG    "DBG_xY8q3"     # 추측 어려운 이름으로 변경 (운영자만 알기)
rename-command KEYS     ""              # SCAN 만 사용 강제
```

**언제 쓰나?**
- ACL 모델 도입 전 (Redis 6 이전 환경)
- ACL이 있어도 추가 안전장치
- 우발적 사고 방지 (개발자가 실수로 FLUSHALL)

**한계**:
- 컨피그 변경 = 재시작 필요 (또는 CONFIG SET 자체가 비활성이면 더 어려움)
- 모듈로 같은 일을 하는 우회 가능 (DEBUG 같은 것)
- ACL 의 `-FLUSHALL` 이 더 깔끔하고 동적

> 출처: <https://github.com/redis/redis/blob/8.6/redis.conf>
> 참고 부분: `rename-command` 디렉티브

---

## 2. 즉시 적용 보안 체크리스트 (production)

### 2.1 네트워크
- [ ] **외부 네트워크에 노출 안 함** — `bind` 를 내부 IP만 또는 `127.0.0.1`
- [ ] **방화벽 / Security Group** — 6379 포트는 앱 호스트 / VPC 내부만
- [ ] `protected-mode yes` — 안전망

### 2.2 인증
- [ ] `requirepass` 또는 ACL 사용자 패스워드 설정 (강력한, 충분히 긴 패스워드)
- [ ] **default user 잠금** — `ACL SETUSER default off` 또는 패스워드 부여
- [ ] 앱별로 별도 ACL 사용자, 최소 권한

### 2.3 명령 제한
- [ ] FLUSHALL / FLUSHDB / CONFIG / DEBUG / SHUTDOWN — `-@dangerous` 또는 ACL로 제한
- [ ] KEYS — 운영에서 절대 금지 (`-KEYS`)
- [ ] CLUSTER RESET / CLUSTER FORGET — admin 사용자만

### 2.4 TLS
- [ ] **외부 / VPC 경계 넘는 통신** — TLS 활성화
- [ ] 인증서 만료 모니터링
- [ ] cluster-bus / replication 모두 TLS

### 2.5 운영
- [ ] `aclfile` 사용 + 백업
- [ ] ACL LOG 정기 수집 / 알람
- [ ] 패스워드 rotation 절차 (ACL 다중 패스워드 활용)
- [ ] 정기 보안 패치 (Redis 새 버전 업그레이드)

### 2.6 데이터
- [ ] 민감 정보 평문 저장 금지 (애플리케이션 측 암호화)
- [ ] RDB / AOF 파일 권한 (600), 디스크 암호화
- [ ] 백업 외부 저장 시 암호화

---

## 3. 운영 사례 — 사고 방지 시나리오

### 시나리오 A: "개발자가 실수로 운영에 FLUSHALL"
**해결**:
- 개발자 ACL 사용자 = `-FLUSHALL -FLUSHDB`
- 또는 `rename-command FLUSHALL ""`
- 또는 `enable-debug-command no` (Redis 7+ 의 안전 옵션)

### 시나리오 B: "Cluster 노드 사이 평문 통신 도청"
**해결**:
- `tls-cluster yes` 모든 노드
- `tls-cluster-replication yes`

### 시나리오 C: "옛 ACL이 그대로 남아 있어 퇴직자도 접근 가능"
**해결**:
- `ACL DELUSER <name>` (CONFIG REWRITE 또는 ACL SAVE)
- 정기 audit (LDAP/SSO + Redis ACL 동기화)

### 시나리오 D: "Pub/Sub 채널을 통해 다른 앱의 메시지 도청"
**해결**:
- `acl-pubsub-default resetchannels` (Redis 7.0+ 기본)
- 앱별 ACL: `&app1.*` 만 허용

### 시나리오 E: "DEBUG SLEEP 으로 단일 스레드 정지 → DoS"
**해결**:
- `enable-debug-command no` 또는 ACL `-DEBUG`
- 학습 환경에서만 DEBUG 허용.

---

## 4. enable-debug-command (Redis 7+)

```
enable-debug-command no            # 기본 = no (안전)
# enable-debug-command yes
# enable-debug-command local       # localhost 만
```

DEBUG 명령은 매우 강력 (서버 정지, 크래시 시뮬레이션). 운영에선 비활성 권장.

---

## 5. enable-protected-configs (Redis 7+)

일부 보안 민감 설정 (`dir`, `dbfilename` 등)은 **CONFIG SET 으로 변경 금지**:
```
enable-protected-configs no       # 기본 (안전)
# enable-protected-configs yes    # CONFIG SET 으로 변경 가능
```

악성 클라이언트가 `CONFIG SET dir /tmp; CONFIG SET dbfilename evil.so` 식으로 임의 파일을 작성하지 못하게 막는다.

---

## 6. 패스워드 정책

- **충분한 길이** (32+ 문자, 대소문자 + 숫자 + 특수)
- **rotation** — ACL은 한 사용자에 여러 패스워드 가능 (`>oldpw >newpw` → 둘 다 동작 → 클라이언트 전환 후 `<oldpw` 제거)
- **secret manager** (Vault, AWS Secrets Manager) 와 통합
- **acl.conf 평문 저장 피하기** — `#<sha256-hex>` 사용 또는 secret manager 에서 주입

---

## 7. 인증된 채널 (RESP3 + AUTH)

연결 한 줄로 인증 + 프로토콜 협상:
```
HELLO 3 AUTH alice p1pp0
```

장점:
- AUTH 1회만 (handshake 절약)
- 첫 명령부터 ACL 적용

---

## 8. 보안 모니터링 메트릭

- `redis_connected_clients` — 비정상 증가 → 잠재적 공격
- `ACL LOG` 항목 수 — 인증 실패 / NOPERM 시도
- `INFO server` 의 `uptime_in_seconds` — 갑자기 0 → 강제 재시작
- 외부 도구: `auditd` 로 redis-server 프로세스 감시

---

## 9. 흔한 함정

| 함정 | 설명 |
|---|---|
| `requirepass` 만으로 충분한 줄 | default user 모든 권한 + 평문 저장. 다중 앱이면 ACL 필수. |
| rename-command "" 후 패치 시 잊음 | redis.conf 갱신 시 필수 옵션 누락 위험. 자동화로 강제. |
| ACL 변경 후 CONFIG REWRITE 안 함 (aclfile 미사용 시) | 재시작 시 사라짐. |
| 패스워드 rotation 시 다운타임 | ACL 다중 패스워드 + 점진 전환으로 zero-downtime. |
| 학습/스테이징 환경에 운영 인증서 | 분리. 환경별 별도 PKI. |
| Cluster 모드 `enable-protected-configs yes` | CONFIG SET 으로 노드 전체 노출. 기본값 유지. |

---

## 10. 직접 해보기

1. `ACL SETUSER default off`, `ACL SETUSER admin on >adminpw +@all ~* &*` 후 default 로 PING 시도 → 실패.
2. `rename-command FLUSHALL ""` 후 FLUSHALL 시도 → unknown command.
3. ACL 다중 패스워드 부여 → 둘 다로 인증 → 하나 제거.
4. `enable-debug-command no` 후 DEBUG SLEEP 시도 → 거부.
5. ACL LOG 인증 실패 시도 후 확인.

---

## 11. 참고 자료

- **[공식 문서] Security overview** — <https://redis.io/docs/latest/operate/oss_and_stack/management/security/>
  - 참고 부분: 네트워크 / 인증 / 권한 권고 — §2 근거

- **[공식 문서] Administration — Security 섹션** — <https://redis.io/docs/latest/operate/oss_and_stack/management/admin/#security>
  - 참고 부분: bind / protected-mode 권고 — §2.1 근거

- **[공식 문서] enable-debug-command / enable-protected-configs** — <https://github.com/redis/redis/blob/8.6/redis.conf>
  - 참고 부분: 옵션 정의 — §4, §5 근거

- **[공식 문서] rename-command** — 동일 출처
  - 참고 부분: 명령 alias / 비활성화 — §1 근거

- **[블로그] antirez — Real-world Redis hijacking** — <http://antirez.com/news/96>
  - 참고 부분: 사례 분석 — §3 근거 보강
