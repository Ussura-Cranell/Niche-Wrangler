# src/ngram_analyzer.py
import re
import pandas as pd
from pathlib import Path
from collections import Counter
from datetime import datetime
import logging
from src.column_normalizer import normalize_columns

logger = logging.getLogger(__name__)

class NgramAnalyzer:
    def __init__(self, merged_folder="merged_data", stopwords_file=None):
        self.merged_folder = Path(merged_folder)
        self.stopwords = self._load_stopwords(stopwords_file)

    def _load_stopwords(self, stopwords_file):
        default_stop = {
            'для', 'и', 'в', 'на', 'с', 'к', 'у', 'о', 'по', 'из', 'под', 'над', 'без', 'до',
            'за', 'перед', 'через', 'при', 'около', 'возле', 'вокруг', 'мимо', 'вне', 'внутри',
            'или', 'а', 'но', 'да', 'же', 'бы', 'не', 'ни', 'то', 'того', 'что', 'как',
            'так', 'это', 'все', 'всё', 'весь', 'очень', 'чуть', 'почти', 'едва'
        }
        if stopwords_file and Path(stopwords_file).exists():
            with open(stopwords_file, 'r', encoding='utf-8') as f:
                custom = set(line.strip().lower() for line in f if line.strip())
                default_stop.update(custom)
        return default_stop

    def _simple_stem(self, word):
        """Упрощённая стеммеризация."""
        if len(word) < 4:
            return word
        for suffix in ['ая', 'ой', 'ую', 'ие', 'ые', 'их', 'ый', 'ий', 'ое', 'ее',
                       'ого', 'ому', 'ым', 'ом', 'ою', 'яя', 'ыми', 'ими',
                       'тся', 'ться']:
            if word.endswith(suffix):
                return word[:-len(suffix)]
        return word

    def _tokenize(self, text):
        """Токенизация, стоп-слова, стемминг."""
        words = re.findall(r'[а-яёa-z]+', text.lower())
        words = [self._simple_stem(w) for w in words
                 if w not in self.stopwords and len(w) > 2]
        return words

    def get_ngrams(self, text, n=2):
        """Генерация n-грамм."""
        tokens = self._tokenize(text)
        if len(tokens) < n:
            return []
        return [' '.join(tokens[i:i+n]) for i in range(len(tokens)-n+1)]

    def load_latest_merged(self):
        csv_files = sorted(self.merged_folder.glob("*.csv"), reverse=True)
        if not csv_files:
            raise FileNotFoundError(f"Нет CSV файлов в {self.merged_folder}")
        latest = csv_files[0]
        logger.info(f"[i] Загрузка {latest}")
        df = pd.read_csv(latest, sep=';', encoding='utf-8-sig')
        df = normalize_columns(df)
        return df

    def analyze_words(self, df, text_column='Name', top_k_words=100, min_revenue=None, extra_filter=None):
        """Частотный анализ отдельных слов (unigrams)."""
        df_filtered = df.copy()
        if min_revenue is not None and 'Revenue' in df_filtered.columns:
            df_filtered = df_filtered[df_filtered['Revenue'] >= min_revenue]
        
        if extra_filter is not None:
            df_filtered = extra_filter(df_filtered)

        if df_filtered.empty:
            return []

        all_words = []
        for text in df_filtered[text_column].dropna():
            all_words.extend(self._tokenize(text))

        counter = Counter(all_words)
        logger.info(f"[i] Найдено {len(counter)} уникальных слов. Топ-{top_k_words} сохранено.")
        return counter.most_common(top_k_words)

    def analyze_ngrams(self, df, text_column='Name', n_range=(2,3), top_k_ngrams=50, min_revenue=None, extra_filter=None):
        """Анализ фразовых n-грамм."""
        df_filtered = df.copy()
        if min_revenue is not None and 'Revenue' in df_filtered.columns:
            df_filtered = df_filtered[df_filtered['Revenue'] >= min_revenue]
            
        if extra_filter is not None:
            df_filtered = extra_filter(df_filtered)

        if df_filtered.empty:
            return {}

        results = {}
        for n in range(n_range[0], n_range[1]+1):
            all_ngrams = []
            for text in df_filtered[text_column].dropna():
                all_ngrams.extend(self.get_ngrams(text, n))
            counter = Counter(all_ngrams)
            results[n] = counter.most_common(top_k_ngrams)
            logger.info(f"[i] Топ-{top_k_ngrams} {n}-грамм: {len(counter)} уникальных")
        return results

    def save_results(self, results_words=None, results_ngrams=None, output_folder="ngram_analysis"):
        out_path = Path(output_folder)
        out_path.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if results_words:
            df_words = pd.DataFrame(results_words, columns=['Word', 'frequency'])
            filename = f"top_words_{timestamp}.csv"
            df_words.to_csv(out_path / filename, index=False, encoding='utf-8-sig')
            logger.info(f"[SAV] Сохранено: {out_path / filename}")

        if results_ngrams:
            for n, grams in results_ngrams.items():
                df_out = pd.DataFrame(grams, columns=[f'{n}-gram', 'frequency'])
                filename = f"top_{n}grams_{timestamp}.csv"
                df_out.to_csv(out_path / filename, index=False, encoding='utf-8-sig')
                logger.info(f"[SAV] Сохранено: {out_path / filename}")

    def print_results(self, results_words=None, results_ngrams=None):
        if results_words:
            print(f"\n=== Топ-{len(results_words)} ЧАСТОТНЫХ СЛОВ ===")
            for i, (word, count) in enumerate(results_words[:25], 1):
                print(f"{i:3d}. {word:40s} – {count}")
            print("="*60)

        if results_ngrams:
            for n, grams in results_ngrams.items():
                print(f"\n=== Топ-{len(grams)} {n}-ГРАММ ===")
                for i, (gram, count) in enumerate(grams[:25], 1):
                    print(f"{i:3d}. {gram:40s} – {count}")
                print("="*60)

    def run_analysis(self, df=None, top_words_k=100, top_ngrams_k=50, n_range=(2, 3), **kwargs):
        """Запуск полного лингвистического анализа."""
        if df is None:
            df = self.load_latest_merged()

        # Извлекаем фильтры из kwargs, если они переданы
        min_rev = kwargs.get('min_revenue')
        extra_filt = kwargs.get('extra_filter')

        logger.info("[N-GR] Запуск частотного анализа слов...")
        words_res = self.analyze_words(
            df, 
            top_k_words=top_words_k, 
            min_revenue=min_rev, 
            extra_filter=extra_filt
        )

        logger.info("[N-GR] Запуск n-грамм анализа...")
        ngrams_res = self.analyze_ngrams(
            df, 
            top_k_ngrams=top_ngrams_k, 
            n_range=n_range, 
            min_revenue=min_rev, 
            extra_filter=extra_filt
        )

        self.print_results(words_res, ngrams_res)
        self.save_results(words_res, ngrams_res)
        return {"words": words_res, "ngrams": ngrams_res}