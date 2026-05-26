# src/archiver.py
import logging
import hashlib
import zipfile
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__) 

class DataArchiver:
    def __init__(self, data_folder="data", archive_folder="archive", cache_folder="cache"):
        self.data_folder = Path(data_folder)
        self.archive_folder = Path(archive_folder)
        self.cache_folder = Path(cache_folder)
        self.hash_file = self.cache_folder / "last_hash.txt"

        self.data_folder.mkdir(exist_ok=True)
        self.archive_folder.mkdir(exist_ok=True)
        self.cache_folder.mkdir(exist_ok=True)

    def _compute_metadata_hash(self):
        """
        Вычисляет хеш на основе имён, размеров и времени модификации файлов.
        Если нет ни одного файла (даже если есть подпапки) — возвращает None.
        """
        files = [f for f in self.data_folder.iterdir() if f.is_file()]
        if not files:
            return None

        hash_md5 = hashlib.md5()
        for file_path in sorted(files):
            rel_name = str(file_path.relative_to(self.data_folder))
            hash_md5.update(rel_name.encode('utf-8'))
            stat = file_path.stat()
            hash_md5.update(str(stat.st_size).encode('utf-8'))
            hash_md5.update(str(stat.st_mtime).encode('utf-8'))
        return hash_md5.hexdigest()

    def _load_last_hash(self):
        if self.hash_file.exists():
            return self.hash_file.read_text().strip()
        return None

    def _save_hash(self, hash_value):
        # hash_value гарантированно str, т.к. вызываем только после проверки
        self.hash_file.write_text(hash_value)

    def _create_zip_archive(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_name = f"data_{timestamp}.zip"
        archive_path = self.archive_folder / archive_name

        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in self.data_folder.iterdir():
                if file_path.is_file():
                    zipf.write(file_path, arcname=file_path.name)

        # print(f"[✓] Архив создан: {archive_path}")
        logger.info(f"[✓] Архив создан: {archive_path}")
        return archive_path

    def run(self):
        # 1. Проверяем наличие файлов (игнорируем подпапки)
        files = [f for f in self.data_folder.iterdir() if f.is_file()]
        if not files:
            # print("[!] В папке data нет файлов, архивация не требуется.")
            logger.warning("[!] В папке data нет файлов, архивация не требуется.")
            return False

        # 2. Вычисляем текущий хеш (теперь он точно не None, т.к. файлы есть)
        current_hash = self._compute_metadata_hash()
        # Страховка: если вдруг None (например, ошибка доступа), выходим
        if current_hash is None:
            # print("[!] Не удалось вычислить хеш (нет доступных файлов).")
            logger.warning("[!] Не удалось вычислить хеш (нет доступных файлов).")
            return False

        last_hash = self._load_last_hash()

        # 3. Сравниваем хеши
        if current_hash == last_hash:
            # print("[i] Хеш не изменился, архивация не требуется.")
            logger.info("[i] Хеш не изменился, архивация не требуется.")
            return False

        # 4. Архивируем и сохраняем новый хеш
        # print("[i] Обнаружены изменения в data. Архивируем...")
        logger.info("[i] Обнаружены изменения в data. Архивируем...")
        self._create_zip_archive()
        self._save_hash(current_hash)
        # print("[✓] Готово. Хеш сохранён.")
        logger.info("[✓] Готово. Хеш сохранён.")
        return True