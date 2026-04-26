"""Reference: docs/00-getting-started/03-redis-cli-basics.md

Redis 연결 + 가장 기본적인 SET/GET/INCR.
실행:
    cd examples/python && python ch00_getting_started/01_ping_and_set.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from _common import get_client, section  # noqa: E402


def main():
    r = get_client()

    with section("PING"):
        print("PING ->", r.ping())

    with section("SET / GET"):
        r.set("hello", "안녕하세요 Redis!")
        print("GET hello ->", r.get("hello"))

    with section("INCR (원자성)"):
        r.set("counter", 0)
        for _ in range(5):
            r.incr("counter")
        print("counter =", r.get("counter"))

    with section("OBJECT ENCODING"):
        r.set("short", "hi")
        r.set("number", 12345)
        r.set("long", "x" * 50)
        for k in ("short", "number", "long"):
            print(f"{k:>8}  encoding=", r.object("encoding", k))

    with section("정리"):
        r.delete("hello", "counter", "short", "number", "long")
        print("done.")


if __name__ == "__main__":
    main()
