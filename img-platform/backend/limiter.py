from slowapi import Limiter
from slowapi.util import get_remote_address

# Rate limiter — 5 login attempts per minute per IP
limiter = Limiter(key_func=get_remote_address)
