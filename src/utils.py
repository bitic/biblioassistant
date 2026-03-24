import time
import functools
from src.logger import logger

def retry(exceptions, tries=3, delay=1, backoff=2, logger_obj=logger):
    """
    Retry decorator with exponential backoff.
    
    :param exceptions: Exception or tuple of exceptions to catch.
    :param tries: Maximum number of attempts.
    :param delay: Initial delay between retries in seconds.
    :param backoff: Multiplier for delay after each retry.
    :param logger_obj: Logger instance to use for reporting retries.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            mtries, mdelay = tries, delay
            while mtries > 1:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    # Specific check for HTTP errors (requests.exceptions.HTTPError)
                    # to only retry on 5xx or specific 429
                    status_code = getattr(getattr(e, 'response', None), 'status_code', None)
                    
                    # If it's an HTTP error, only retry on 5xx or 429
                    if status_code and not (500 <= status_code < 600 or status_code == 429):
                        raise e

                    msg = f"Retrying in {mdelay} seconds... (Error: {e})"
                    if logger_obj:
                        logger_obj.warning(msg)
                    else:
                        print(msg)
                        
                    time.sleep(mdelay)
                    mtries -= 1
                    mdelay *= backoff
            return func(*args, **kwargs)
        return wrapper
    return decorator
