import os
from redis import Redis
from rq import Queue

def get_redis():
    return Redis.from_url(os.environ["REDIS_URL"])

def get_queue(name="transcribe"):
    return Queue(name, connection=get_redis())
