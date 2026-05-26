#!/usr/bin/env python3
"""ETL & Анализ ниши маркетплейсов. Упрощённый CLI-оркестратор."""
import argparse
import logging
import os
import sys
import re
import shutil
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional

from src.config_manager import load_config
from src.logger import setup_logger
from src.pipeline_state import PipelineState
from src.archiver import DataArchiver
from src.data_loader import DataLoader
from src.rule_engine import RuleEngine
from src.ngram_analyzer import NgramAnalyzer
from src.niche_analyzer import NicheAnalyzer

def compute_data_hash(folder: str) -> Optional[str]:
    """Вычисляет MD5-хеш метаданных папки data (имя, размер, mtime)."""
    p = Path(folder)
    if not p.exists(): return None
    files = sorted([f for f in p.iterdir() if f.is_file()])
    if not files: return None
    
    h = hashlib.md5()
    for f in files:
        h.update(f.name.encode('utf-8'))
        s = f.stat()
        h.update(str(s.st_size).encode('utf-8'))
        h.update(str(s.st_mtime).encode('utf-8'))
    return h.hexdigest()

class PipelineOrchestrator:
    def __init__(self, config: dict):
        self.config = config
        self.paths = config.get("paths", {})
        self.state = PipelineState(config)
        log_cfg = config.get("processing", {})
        setup_logger(
            log_file=log_cfg.get("log_file", "logs/app.log"),
            level=getattr(logging, log_cfg.get("log_level", "INFO"))
        )
        self.logger = logging.getLogger(__name__)

    def run_auto(self):
        """Автоматический режим: кэш -> фильтр(если есть) -> n-gram"""
        curr_hash = compute_data_hash(self.paths["data_folder"])
        cache_file = Path(self.paths["cache_folder"]) / "last_hash.txt"
        merged_exists = any(Path(self.paths["merged_folder"]).glob("*.csv"))

        # 1. Архивация и слияние (только при изменениях или отсутствии кэша)
        if not merged_exists or curr_hash != (cache_file.read_text().strip() if cache_file.exists() else ""):
            self.logger.info("[AUTO] Изменения в data или нет кэша. Запуск архивации и слияния...")
            DataArchiver(
                self.paths["data_folder"], 
                self.paths["archive_folder"], 
                self.paths["cache_folder"]
            ).run()
            
            loader = DataLoader(
                self.paths["data_folder"], 
                self.paths["merged_folder"], 
                skip_errors=True
            )
            self.state.df = loader.load_and_merge(save=True)
            
            Path(self.paths["cache_folder"]).mkdir(parents=True, exist_ok=True)
            cache_file.write_text(curr_hash)
            self.logger.info("[AUTO] Кэш обновлён.")
        else:
            self.logger.info("[AUTO] Данные не изменились. Используем кэш слияния.")
            self.state.load_to_memory("merged_folder")

        # 2. Фильтрация (если rules.yaml существует и не пуст)
        rules_path = Path("rules.yaml")
        if rules_path.exists() and rules_path.stat().st_size > 0:
            self.logger.info("[AUTO] Обнаружены правила фильтрации. Применяю...")
            engine = RuleEngine(str(rules_path))
            subsets = engine.apply_all(self.state.df, name_col="Name")
            
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            fp = Path(self.paths["filtered_folder"])
            fp.mkdir(parents=True, exist_ok=True)
            # Очистка старых результатов для чистоты вывода
            for f in fp.glob("*.csv"): f.unlink()
            
            for name, sub_df in subsets.items():
                if sub_df.empty: continue
                safe_name = re.sub(r'[\\/*?:"<>|]', '_', name)
                out_path = fp / f"{safe_name}_{ts}.csv"
                sub_df.to_csv(out_path, index=False, sep=';', encoding='utf-8-sig')
                
            # Берём первое рабочее подмножество (игнорируя _остаток)
            target_df = next((v for k, v in subsets.items() if not k.startswith("_")), None)
            if target_df is None or target_df.empty:
                self.logger.warning("[AUTO] Фильтр вернул пустой результат. Использую исходные данные.")
                target_df = self.state.df
            self.state.df = target_df
        else:
            self.logger.info("[AUTO] rules.yaml не найден или пуст. Пропускаю фильтрацию.")

        # 3. Анализ n-грамм
        self.logger.info("[AUTO] Запуск лингвистического анализа...")
        analyzer = NgramAnalyzer(merged_folder=self.paths.get("merged_folder", "merged_data"))
        analyzer.run_analysis(df=self.state.df, top_words_k=100, top_ngrams_k=50, n_range=(2, 3))
        self.logger.info("[DONE] Автоматический пайплайн успешно завершён!")

    def run_stats(self):
        """Генерация отчёта по нише и архивация правил"""
        # Приоритет загрузки: отфильтрованные -> слитые -> из памяти
        filtered_path = Path(self.paths["filtered_folder"])
        if filtered_path.exists() and any(filtered_path.glob("*.csv")):
            self.logger.info("[STATS] Загрузка отфильтрованных данных...")
            self.state.load_to_memory("filtered_folder")
        elif self.state.df is None:
            self.logger.info("[STATS] Отфильтрованных нет, загружаю слитые...")
            self.state.load_to_memory("merged_folder")

        if self.state.df is None or self.state.df.empty:
            self.logger.error("[STATS] Нет данных для анализа. Сначала запустите `python main.py`")
            return

        # Временный файл для NicheAnalyzer
        temp_path = Path(self.paths["filtered_folder"]) / "_temp_stats.csv"
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        self.state.df.to_csv(temp_path, index=False, sep=';', encoding='utf-8-sig')

        analyzer = NicheAnalyzer(str(temp_path), output_folder=self.paths["reports_folder"])
        analyzer.print_summary_report()
        analyzer.export_price_intervals_csv(n_bins=15, method='quantile')
        temp_path.unlink(missing_ok=True)

        # Архивация правил (заменяет старые версии)
        rules_src = Path("rules.yaml")
        arch_dir = Path("archive")
        arch_dir.mkdir(exist_ok=True)
        if rules_src.exists():
            for old in arch_dir.glob("rules_*.yaml"):
                old.unlink()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.copy2(rules_src, arch_dir / f"rules_{ts}.yaml")
            self.logger.info("[STATS] Текущая версия rules.yaml сохранена в архив.")
        self.logger.info("[DONE] Отчёт сформирован и сохранён в reports/")

    def run_clear(self):
        """Очистка рабочего пространства, сохранение архивов"""
        dirs_to_clear = [
            "data", "cache", "merged_data", "filtered_subsets",
            "ngram_analysis", "reports", "logs"
        ]
        for d in dirs_to_clear:
            p = Path(d)
            if p.exists():
                shutil.rmtree(p)
                p.mkdir(exist_ok=True)
        self.logger.info("[CLEAR] Рабочее пространство очищено. Папка archive сохранена.")
        print("Готово. Можете загружать новые данные в data/ и начинать работу заново.")

def main():
    parser = argparse.ArgumentParser(description="ETL & Анализ ниши маркетплейсов (Упрощённый режим)")
    parser.add_argument("--config", default="config.json", help="Путь к конфигурации")
    parser.add_argument("--stats", action="store_true", help="Финальный отчёт + архивация rules.yaml")
    parser.add_argument("--clear", action="store_true", help="Очистить всё, кроме папки archive/")
    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except Exception as e:
        print(f"[✗] Ошибка загрузки конфигурации: {e}"); sys.exit(1)

    orchestrator = PipelineOrchestrator(config)

    if args.clear:
        orchestrator.run_clear()
    elif args.stats:
        orchestrator.run_stats()
    else:
        # По умолчанию: автоматический режим
        orchestrator.run_auto()

if __name__ == "__main__":
    main()
