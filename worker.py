"""
RQ worker entry point — run this in a separate terminal:

    .venv/bin/python worker.py

The worker consumes from the "email" queue and calls sender.send_email
for each job. Keep this process running alongside the FastAPI server.
"""

from redis import Redis
from rq import Worker

from app.core.config import settings

if __name__ == "__main__":
    conn = Redis.from_url(settings.redis_url)
    worker = Worker(queues=["email"], connection=conn)
    worker.work(with_scheduler=True)
