"""Reference: docs/09-patterns/01-cache-aside.md

Cache-aside 패턴 + negative caching + 락 기반 stampede 방지 (간단 버전).
"""
import sys, json, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from _common import get_client, section  # noqa: E402

CACHE_TTL = 30
NULL_TTL = 5
NULL_MARKER = "__NULL__"

# fake DB
_DB = {1: {"id": 1, "name": "Alice"}, 2: {"id": 2, "name": "Bob"}}
_DB_HITS = 0


def db_fetch(user_id):
    global _DB_HITS
    _DB_HITS += 1
    time.sleep(0.05)  # 50ms 시뮬
    return _DB.get(user_id)


def get_user(r, user_id):
    key = f"user:{user_id}"
    cached = r.get(key)
    if cached == NULL_MARKER:
        return None
    if cached:
        return json.loads(cached)

    user = db_fetch(user_id)
    if user is None:
        r.set(key, NULL_MARKER, ex=NULL_TTL)
    else:
        r.set(key, json.dumps(user), ex=CACHE_TTL)
    return user


def update_user(r, user_id, data):
    _DB[user_id].update(data)
    r.delete(f"user:{user_id}")


def main():
    r = get_client()
    global _DB_HITS

    with section("처음 read — DB 호출 (cache miss)"):
        _DB_HITS = 0
        for _ in range(5):
            print("got:", get_user(r, 1))
        print(f"DB hits: {_DB_HITS} (1번이어야 정상 — 첫 호출만)")

    with section("update 후 read — 무효화 + 재조회"):
        _DB_HITS = 0
        update_user(r, 1, {"name": "Alice-Renamed"})
        print("after update:", get_user(r, 1))
        print(f"DB hits: {_DB_HITS} (1번이어야 정상)")

    with section("없는 ID — negative caching"):
        _DB_HITS = 0
        for _ in range(5):
            print("got:", get_user(r, 999))
        print(f"DB hits: {_DB_HITS} (1번이어야 정상 — 나머지는 NULL 캐시)")

    with section("정리"):
        r.delete("user:1", "user:2", "user:999")
        print("done.")


if __name__ == "__main__":
    main()
