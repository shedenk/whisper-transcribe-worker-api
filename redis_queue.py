import os
from redis import Redis
from rq import Queue

_redis = None
_redis_pid = None

def get_redis():
    global _redis, _redis_pid
    current_pid = os.getpid()
    
    if _redis is None or _redis_pid != current_pid:
        # Create new connection for this process
        _redis = Redis.from_url(
            os.environ["REDIS_URL"], 
            decode_responses=False,
            socket_timeout=10,
            socket_keepalive=True,
            retry_on_timeout=True
        )
        _redis_pid = current_pid
    return _redis

def get_queue(name="transcribe"):
    return Queue(name, connection=get_redis())
