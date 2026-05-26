# src/column_normalizer.py
import pandas as pd
import logging

logger = logging.getLogger(__name__)

# Обязательные колонки (целевые имена) – добавили Country
REQUIRED_COLUMNS = ["Name", "SKU", "Seller", "Brand", "Revenue", "Sales", "Price"]

# Маппинг возможных названий из исходных файлов в целевые имена
COLUMN_MAPPING = {
    # Name
    "Name": "Name",
    "Название": "Name",
    "Название карточки товара": "Name",
    "Товар": "Name",
    # SKU
    "SKU": "SKU",
    "Артикул": "SKU",
    "Код товара": "SKU",
    # Seller
    "Seller": "Seller",
    "Продавец": "Seller",
    "Магазин": "Seller",
    # Brand
    "Brand": "Brand",
    "Бренд": "Brand",
    # Revenue
    "Revenue": "Revenue",
    "Заказы, ₽": "Revenue",
    "Выручка": "Revenue",
    "Оборот": "Revenue",
    "Заказы, руб": "Revenue",
    # Sales
    "Sales": "Sales",
    "Заказы, шт": "Sales",
    "Заказы, шт.": "Sales",
    "Количество заказов": "Sales",
    # Price
    "Price": "Price",
    "Price with WB wallet": "Price",
    "Цена с WB Кошельком, ₽": "Price",
    "Цена с Ozon картой": "Price",
    "Цена со скидкой WB": "Price",
    "Цена": "Price",
    "Итоговая цена": "Price",
    # Country
    "Country": "Country",
    "Страна": "Country",
    "Страна производства": "Country",
    "Страна производитель": "Country"
}

def normalize_columns(df):
    """
    Приводит имена колонок DataFrame к стандартному виду согласно COLUMN_MAPPING.
    Оставляет только REQUIRED_COLUMNS (и те колонки, которые удалось переименовать).
    """
    rename_dict = {}
    for col in df.columns:
        if col in COLUMN_MAPPING:
            rename_dict[col] = COLUMN_MAPPING[col]
        stripped = col.strip()
        if stripped != col and stripped in COLUMN_MAPPING:
            rename_dict[col] = COLUMN_MAPPING[stripped]
    df_renamed = df.rename(columns=rename_dict)
    valid_columns = [col for col in df_renamed.columns if col in REQUIRED_COLUMNS]
    df_renamed = df_renamed[valid_columns]
    return df_renamed

def validate_required_columns(df, context="DataFrame"):
    missing = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(
            f"{context} не содержит обязательных столбцов: {missing}\n"
            f"Фактические столбцы: {list(df.columns)}"
        )