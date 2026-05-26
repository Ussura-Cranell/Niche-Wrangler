import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import logging
from src.column_normalizer import normalize_columns, validate_required_columns
logger = logging.getLogger(__name__)

class NicheAnalyzer:
    def __init__(self, file_path: str, output_folder="reports", sep=';', encoding='utf-8-sig'):
        self.output_folder = Path(output_folder)
        self.output_folder.mkdir(parents=True, exist_ok=True)
        self.df = pd.read_csv(file_path, sep=sep, encoding=encoding)
        self.df = normalize_columns(self.df)
        validate_required_columns(self.df, f"Файл {file_path}")
        for col in ['Revenue', 'Sales', 'Price']:
            if col in self.df.columns:
                self.df[col] = pd.to_numeric(self.df[col], errors='coerce')
        
        self.total_revenue = self.df['Revenue'].sum()
        self.total_sales = self.df['Sales'].sum()
        self.total_products = len(self.df)
        self.seller_agg = self.brand_agg = self.country_stats = self._price_intervals = None

    def _aggregate(self, group_col, name_map):
        res = self.df.groupby(group_col).agg(
            Выручка=('Revenue', 'sum'), Продажи=('Sales', 'sum'), Товары=('SKU', 'count')
        ).sort_values('Выручка', ascending=False)
        res['Доля_%'] = (res['Выручка'] / self.total_revenue * 100) if self.total_revenue else 0
        setattr(self, name_map, res)
        return res

    def aggregate_by_seller(self): return self._aggregate('Seller', 'seller_agg')
    def aggregate_by_brand(self): return self._aggregate('Brand', 'brand_agg')
    def aggregate_by_country(self, col='Country'):
        df = self.df.copy()
        if col not in df.columns:
            logger.warning(f"Колонка '{col}' отсутствует")
            self.country_stats = pd.DataFrame()
            return self.country_stats
        df[col] = df[col].fillna('Не указано')
        self.country_stats = df.groupby(col).agg(
            Выручка=('Revenue', 'sum'), Продажи=('Sales', 'sum'), Товары=('SKU', 'count')
        ).sort_values('Выручка', ascending=False)
        self.country_stats['Доля_%'] = (self.country_stats['Выручка'] / self.total_revenue * 100) if self.total_revenue else 0
        return self.country_stats

    def hhi_index(self, agg_df):
        if agg_df is None or agg_df.empty: return 0
        return ((agg_df['Доля_%'] / 100) ** 2).sum() * 10000

    def _format_top_list(self, agg_df, col_name, threshold=1.0, limit=15):
        top = agg_df[agg_df['Доля_%'] >= threshold].head(limit)
        if top.empty: return f"   Нет {col_name.lower()} с долей > {threshold}%"
        
        lines = []
        max_len = max(len(str(idx)) for idx in top.index)
        for i, (idx, row) in enumerate(top.iterrows(), 1):
            lines.append(f"{i:2d}. {str(idx).ljust(max_len)}   {row['Доля_%']:>5.1f}%")
        
        if len(agg_df[agg_df['Доля_%'] >= threshold]) > limit:
            rest = agg_df.iloc[limit:]
            lines.append(f"... и ещё {len(rest)} {col_name.lower()} (суммарно {rest['Выручка'].sum():.0f} ₽, {rest['Доля_%'].sum():.1f}%)")
        return "\n".join(lines)

    def print_summary_report(self):
        if self.seller_agg is None: self.aggregate_by_seller()
        if self.brand_agg is None: self.aggregate_by_brand()
        if self.country_stats is None: self.aggregate_by_country()

        report = f"""
┌──────────────────────────────────────────────────┐
│      АВТОМАТИЧЕСКИЙ ОТЧЁТ ПО НИШЕ (90 дней)      │
└──────────────────────────────────────────────────┘
ОБЩАЯ СТАТИСТИКА
Выручка:            {self.total_revenue:.0f} ₽
Продажи:            {self.total_sales:.0f} шт.
Товаров:            {self.total_products}
Продавцов:          {len(self.seller_agg)}
Брендов:            {len(self.brand_agg)}
ПРОДАВЦЫ (доля >1%)
{self._format_top_list(self.seller_agg, 'Продавцов')}
Топ-1: {self.seller_agg.index[0] if not self.seller_agg.empty else '—'} ({self.seller_agg.iloc[0]['Доля_%']:.1f}%) | HHI: {self.hhi_index(self.seller_agg):.1f}

БРЕНДЫ (доля >1%)
{self._format_top_list(self.brand_agg, 'Брендов')}
Топ-1: {self.brand_agg.index[0] if not self.brand_agg.empty else '—'} ({self.brand_agg.iloc[0]['Доля_%']:.1f}%) | HHI: {self.hhi_index(self.brand_agg):.1f}
"""
        print(report)

    def export_price_intervals_csv(self, price_col='Price', n_bins=15,
                                 price_min=None, price_max=None,
                                 custom_bins=None, method='quantile'):
        """
        Экспорт ценовых интервалов в CSV.
        
        Параметры:
        - method: 'quantile' (равное число товаров в бине) или 'equal_width' (равная ширина интервала)
        - Интервалы имеют формат [от; до) — левая граница включена, правая исключена
        - Все цены округляются до целых рублей
        """
        df = self.df.copy()
        
        # Фильтрация по цене
        if price_min is not None:
            df = df[df[price_col] >= price_min]
        if price_max is not None:
            df = df[df[price_col] <= price_max]
        
        # Очистка данных
        prices = df[price_col].dropna()
        prices = prices[prices > 0]
        if len(prices) == 0:
            logger.warning("Нет данных с положительной ценой для построения интервалов")
            return
        
        # Построение бинов
        if custom_bins is not None:
            bins = np.array(custom_bins)
        elif method == 'quantile':
            try:
                bins = prices.quantile(np.linspace(0, 1, n_bins + 1)).values
                bins = np.unique(bins)
                if len(bins) < 2:
                    raise ValueError("Недостаточно уникальных значений для квантилей")
            except Exception:
                logger.warning("Не удалось построить квантили, переключение на равные интервалы")
                method = 'equal_width'
        
        if method == 'equal_width' or custom_bins is None and method != 'quantile':
            min_p, max_p = prices.min(), prices.max()
            bins = np.linspace(min_p, max_p, n_bins + 1)
            bins = np.unique(bins)
        
        # Округление границ до целых рублей
        bins = np.round(bins).astype(int)
        bins = np.unique(bins)
        
        # Создаём интервалы с [left, right)
        labels = [f"[{bins[i]}; {bins[i+1]})" for i in range(len(bins)-1)]
        
        # Применяем бининг
        df['price_bin'] = pd.cut(df[price_col], bins=bins, labels=labels,
                                include_lowest=False, right=False, duplicates='drop')
        
        # Агрегация
        grouped = df.groupby('price_bin', observed=True).agg(
            Products=('SKU', 'nunique'),
            Sales=('Sales', 'sum'),
            Revenue=('Revenue', 'sum'),
            Total_sellers=('Seller', 'nunique')
        ).reset_index()
        
        # [✓] ИСПРАВЛЕНИЕ: используем str.extract вместо apply с pd.Series
        extracted = grouped['price_bin'].astype(str).str.extract(r'\[(-?\d+);\s*(-?\d+)\)')
        grouped['Price from'] = extracted[0].astype(int)
        grouped['Price to'] = extracted[1].astype(int)
        
        # Сортировка и расчёт долей
        grouped = grouped.dropna(subset=['Price from']).sort_values('Price from')
        total_rev = grouped['Revenue'].sum()
        grouped['Revenue share, %'] = (grouped['Revenue'] / total_rev * 100).round(1) if total_rev > 0 else 0
        
        # Дополнительные метрики
        if 'Sales' in df.columns:
            sellers_with_sales = df[df['Sales'] > 0].groupby('price_bin', observed=True)['Seller'].nunique()
            grouped['Sellers with sales'] = grouped['price_bin'].map(sellers_with_sales).fillna(0).astype(int)
        else:
            grouped['Sellers with sales'] = 0
        
        # Порядок колонок
        columns_order = ['Price from', 'Price to', 'Products', 'Sales', 'Revenue',
                        'Total_sellers', 'Sellers with sales', 'Revenue share, %']
        grouped = grouped[[c for c in columns_order if c in grouped.columns]]
        
        # Сохранение
        file_path = self.output_folder / "price_intervals.csv"
        grouped.to_csv(file_path, sep=';', encoding='utf-8-sig',
                      float_format='%.0f', decimal=',', index=False)
        logger.info(f"Сохранён {file_path}")
        
        return grouped