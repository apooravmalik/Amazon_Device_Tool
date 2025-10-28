from cache import load_cache, save_cache
from logger import get_logger

logger = get_logger(__name__)

def get_cache_value(key):
    logger.debug(f"Getting value from cache for key: {key}")
    cache = load_cache()
    return cache.get(key)

def set_cache_value(key, value):
    logger.debug(f"Setting value in cache for key: {key}")
    cache = load_cache()
    cache[key] = value
    save_cache(cache)
    logger.info(f"Cache updated for key: {key}")
    return True