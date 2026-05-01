from config import settings
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

DB_URL = settings.db.url
ECHO = False
ECHO_POOL = False
POOL_SIZE = 50
MAX_OVERFLOW = 10


engine = create_async_engine(
    url=DB_URL,
    echo=ECHO,
    echo_pool=ECHO_POOL,
    pool_size=POOL_SIZE,
    max_overflow=MAX_OVERFLOW,
)

session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
