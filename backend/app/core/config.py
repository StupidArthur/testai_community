import os
import sys

_SECRET_KEY = os.environ.get("SECRET_KEY")
if not _SECRET_KEY:
    if os.getenv("ENV", "dev") == "production":
        sys.exit("FATAL: SECRET_KEY environment variable must be set in production. Refusing to start.")
    import warnings
    warnings.warn("SECRET_KEY not set, using insecure default — DO NOT use in production!")
    _SECRET_KEY = "dev-only-insecure-key"

SECRET_KEY = _SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./database.sqlite")

MINIMAX_API_KEY = "sk-cp-aXV4X8TlWZeR3E1hpIaPtjEFnafrpbEi_IMlm6NhSY_0-CQHOV5WupxDkg4LV2JXfB3sO_AoGodPCkQ6irIC7PuIoxC29MVKqG70AYz_hQ1VIjNDgSpCvOo"
MINIMAX_API_URL = os.getenv("MINIMAX_API_URL", "https://api.minimaxi.com/v1")
MINIMAX_MODEL = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.7-highspeed")
MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", "1"))

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")