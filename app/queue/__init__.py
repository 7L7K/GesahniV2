# Minimal stub so imports resolve in TESTING without a live backend.
# If code paths hit real queue ops in tests, raise a clear message.

class _QueueNotConfigured(RuntimeError):
    """Raised when queue operations are attempted without a configured backend."""
    pass

def _not_configured(*args, **kwargs):
    raise _QueueNotConfigured("Queue backend not configured in TESTING")

# Stub implementations that raise clear errors
def get_queue(*args, **kwargs):
    raise _QueueNotConfigured("Queue backend not configured - get_queue() called")

def enqueue_sms(*args, **kwargs):
    raise _QueueNotConfigured("Queue backend not configured - enqueue_sms() called")

# Stub classes
class QueueClient:
    def __init__(self, *args, **kwargs):
        raise _QueueNotConfigured("Queue backend not configured - QueueClient() called")

    async def pop(self, *args, **kwargs):
        raise _QueueNotConfigured("Queue backend not configured - QueueClient.pop() called")

    async def push(self, *args, **kwargs):
        raise _QueueNotConfigured("Queue backend not configured - QueueClient.push() called")
