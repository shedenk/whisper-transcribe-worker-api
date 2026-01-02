import os
from redis import Redis

def get_redis():
    return Redis.from_url(os.environ["REDIS_URL"])
