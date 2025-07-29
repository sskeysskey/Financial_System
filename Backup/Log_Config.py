import logging
from logging.handlers import RotatingFileHandler

def setup_logger():
    logger = logging.getLogger(__name__ )
    logger.setLevel(logging.INFO)

    # 创建 RotatingFileHandler
    file_handler = RotatingFileHandler("/Users/yanzhang/Documents/News/today_error.log", maxBytes=1000000, backupCount=5)
    file_handler.setLevel(logging.INFO)

    # 创建 StreamHandler
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)

    # 创建格式器并将其添加到处理器
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)

    # 将处理器添加到 logger
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

    return logger

# 创建并配置 logger
logger = setup_logger()