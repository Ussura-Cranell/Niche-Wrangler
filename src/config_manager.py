import json
from pathlib import Path

def load_config(config_path="config.json"):
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Файл конфигурации {path} не найден")
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)