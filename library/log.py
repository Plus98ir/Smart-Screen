# Smart-Screen logger (replaces upstream library/log.py)
import logging
import os
from logging.handlers import RotatingFileHandler

_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[RotatingFileHandler(os.path.join(_dir, "smartscreen.log"), maxBytes=1_000_000, backupCount=1,
                                  encoding="utf-8"),
              logging.StreamHandler()],
    datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger("smartscreen")
logger.setLevel(logging.INFO)
