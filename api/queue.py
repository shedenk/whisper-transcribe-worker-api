import os
from redis import Redis
from rq import Queue

def get_redis():
    return Redis.from_url(os.environ["REDIS_URL"])

def get_queue():
    # queue name: transcribe
    return Queue("transcribe", connection=get_redis())
