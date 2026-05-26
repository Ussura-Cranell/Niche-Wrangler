# src/pipeline_state.py
import logging
import pandas as pd
from pathlib import Path
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

class PipelineState:
    """
    Управляет жизненным циклом данных между шагами пайплайна.
    - Хранит DataFrame в памяти для избежания избыточного I/O.
    - Валидирует наличие артефактов перед запуском шага.
    - Загружает данные из диска только при пропуске предыдущих этапов.
    """

    DEPENDENCY_GRAPH = {
        "archive": [],
        "merge": [],
        "filter": ["merged_folder"],
        "ngram": ["filtered_folder"],
        "niche": ["filtered_folder"]
    }

    def __init__(self, config: dict):
        self.config = config
        self.paths = config.get("paths", {})
        self.df: Optional[pd.DataFrame] = None
        self.completed_steps: List[str] = []

    def artifact_exists(self, folder_key: str) -> bool:
        """Проверяет, содержит ли целевая папка хотя бы один CSV-файл."""
        folder_path = Path(self.paths.get(folder_key, folder_key))
        if not folder_path.exists():
            return False
        return any(folder_path.glob("*.csv"))

    def check_dependencies(self, step: str) -> bool:
        """Возвращает True, если все зависимости для шага выполнены."""
        deps = self.DEPENDENCY_GRAPH.get(step, [])
        for dep in deps:
            if not self.artifact_exists(dep):
                logger.warning(f"[✗] Зависимость не выполнена: '{dep}' (отсутствуют CSV-артефакты)")
                return False
        return True

    def get_latest_artifact(self, folder_key: str) -> Optional[Path]:
        """Возвращает путь к самому свежему CSV в папке (по mtime)."""
        folder_path = Path(self.paths.get(folder_key, folder_key))
        if not folder_path.exists():
            return None
        files = sorted(folder_path.glob("*.csv"), key=lambda f: f.stat().st_mtime, reverse=True)
        return files[0] if files else None

    def load_to_memory(self, folder_key: str) -> pd.DataFrame:
        """Загружает последний артефакт из указанной папки в RAM."""
        path = self.get_latest_artifact(folder_key)
        if path is None:
            raise FileNotFoundError(f"Нет данных для загрузки из '{folder_key}'")
        logger.info(f"[LOD] Загрузка артефакта в память: {path.name}")
        self.df = pd.read_csv(path, sep=';', encoding='utf-8-sig', low_memory=False)
        return self.df

    def mark_completed(self, step: str):
        """Фиксирует успешное завершение шага."""
        self.completed_steps.append(step)
        logger.info(f"[✓] Шаг '{step}' успешно завершён.")