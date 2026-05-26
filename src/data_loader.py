import logging
import pandas as pd
from pathlib import Path
import re
from src.column_normalizer import REQUIRED_COLUMNS, normalize_columns, validate_required_columns
logger = logging.getLogger(__name__)

class DataLoader:
    def __init__(self, data_folder="data", output_folder="merged_data", skip_errors=True):
        self.data_folder = Path(data_folder)
        self.output_folder = Path(output_folder)
        self.skip_errors = skip_errors
        if not self.data_folder.exists():
            raise FileNotFoundError(f"Папка {self.data_folder} не существует")
        self.output_folder.mkdir(parents=True, exist_ok=True)

    def _clean_price_or_revenue(self, value):
        if pd.isna(value) or value in ["", "-"]:
            return None
        if isinstance(value, (int, float)):
            return int(value) if isinstance(value, float) and value.is_integer() else value
        s = re.sub(r"[^\d\-.,]", "", str(value)).replace(",", ".").replace(" ", "")
        if not s: return None
        num = float(s)
        return int(num) if num.is_integer() else num

    def _clean_sales(self, value):
        if pd.isna(value): return None
        if isinstance(value, (int, float)): return int(value)
        s = re.sub(r"[^\d]", "", str(value))
        return int(s) if s else None

    def _apply_cleaning(self, df):
        for col in ["Revenue", "Price"]:
            if col in df.columns:
                df[col] = df[col].apply(self._clean_price_or_revenue)
        if "Sales" in df.columns:
            df["Sales"] = df["Sales"].apply(self._clean_sales)
        return df

    def load_and_merge(self, save=True, save_format="csv"):
        csv_files = list(self.data_folder.glob("*.csv"))
        if not csv_files:
            raise FileNotFoundError(f"Нет CSV файлов в {self.data_folder}")

        dataframes = []
        for file_path in csv_files:
            try:
                df = pd.read_csv(file_path, sep=';', encoding='utf-8-sig', dtype=str, keep_default_na=False)
                df = df.dropna(how='all')
                if df.empty:
                    logger.warning(f"[!] Файл {file_path.name} пуст, пропуск")
                    continue
                
                df = normalize_columns(df)
                validate_required_columns(df, f"Файл {file_path.name}")
                df = self._apply_cleaning(df)
                dataframes.append(df)
                logger.info(f"[✓] Загружен {file_path.name}: {len(df)} строк")
            except Exception as e:
                if self.skip_errors:
                    logger.error(f"[✗] Ошибка в {file_path.name}: {e}. Пропускаем файл.")
                else:
                    raise RuntimeError(f"Ошибка при обработке {file_path.name}: {e}")

        if not dataframes:
            raise ValueError("Не удалось загрузить ни одного корректного CSV файла")

        merged_df = pd.concat(dataframes, ignore_index=True)
        merged_df = merged_df.dropna(subset=["SKU"]).copy()
        merged_df["SKU"] = merged_df["SKU"].astype(str)
        
        before = len(merged_df)
        merged_df = merged_df.drop_duplicates(subset=["SKU"], keep="first")
        if before != len(merged_df):
            logger.info(f"[#] Удалено дубликатов по SKU: {before - len(merged_df)}")

        logger.info(f"[#] Итоговое число уникальных товаров: {len(merged_df)}")
        if save:
            self._save_dataframe(merged_df, save_format)
        return merged_df

    def _save_dataframe(self, df, format="csv"):
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.output_folder / f"merged_data_{ts}.{format}"
        if format.lower() == "csv":
            df.to_csv(path, index=False, sep=';', encoding='utf-8-sig')
        elif format.lower() == "excel":
            df.to_excel(path, index=False, engine='openpyxl')
        logger.info(f"[✓] Сохранено: {path}")