# src/logger.py
import logging
import sys
from pathlib import Path

def setup_logger(log_file="logs/app.log", level=logging.INFO):
    """
    Настраивает логгер:
    - в консоль выводится только сообщение (кратко)
    - в файл выводится дата, модуль, уровень, сообщение (подробно)
    """
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Удаляем старые обработчики, чтобы не дублировать
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    # Формат для файла (подробный)
    file_formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Формат для консоли – только сообщение
    console_formatter = logging.Formatter(fmt='%(message)s')

    # Файловый обработчик
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(level)
    file_handler.setFormatter(file_formatter)

    # Консольный обработчик
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(console_formatter)

    # Настройка корневого логгера
    logging.root.setLevel(level)
    logging.root.addHandler(console_handler)
    logging.root.addHandler(file_handler)

    # Подавляем шум от сторонних библиотек
    logging.getLogger("pandas").setLevel(logging.WARNING)

    return logging.getLogger(__name__)