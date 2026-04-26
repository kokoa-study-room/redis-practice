"""Redis 학습 예제 공통 모듈.

REDIS_HOST / REDIS_PORT 환경변수 또는 .env 파일에서 연결 정보를 읽어 클라이언트를 만든다.
모든 챕터 예제가 from _common import client 로 사용한다.
"""
import os
from contextlib import contextmanager

import redis

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def get_client(decode_responses: bool = True) -> redis.Redis:
    return redis.Redis(
        host=os.getenv("REDIS_HOST", "127.0.0.1"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        db=int(os.getenv("REDIS_DB", "0")),
        decode_responses=decode_responses,
    )


@contextmanager
def section(title: str):
    line = "=" * 60
    print(f"\n{line}\n {title}\n{line}")
    yield
