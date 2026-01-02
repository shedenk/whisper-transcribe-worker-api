import os
from redis import Redis
from rq import Queue

_redis = None

def get_redis():
    global _redis
    if _redis is None:
        _redis = Redis.from_url(os.environ["REDIS_URL"], decode_responses=False)
    return _redis

def get_queue(name="transcribe"):
    return Queue(name, connection=get_redis())
