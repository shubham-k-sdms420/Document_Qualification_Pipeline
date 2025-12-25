"""
Gunicorn configuration file
"""
import multiprocessing
import os

# Server socket
bind = f"0.0.0.0:{os.getenv('FLASK_PORT', '5000')}"
backlog = 2048

# Worker processes
workers = int(os.getenv('GUNICORN_WORKERS', '4'))
worker_class = 'sync'
worker_connections = 1000
timeout = 300
keepalive = 5

# Logging
accesslog = '-'
errorlog = '-'
loglevel = os.getenv('LOG_LEVEL', 'info').lower()
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = 'doc-verifier-pipeline'

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# SSL (if needed in future)
# keyfile = None
# certfile = None
