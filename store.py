import json
import threading
from pathlib import Path
from typing import Any, Optional, List, Tuple

class JsonStore:
    def __init__(self, path: Path, autosave: bool = True):
        self.path = path
        self.autosave = autosave
        self._lock = threading.Lock()
        self._data = {}
        self._load()

    def _load(self) -> None:
        """Загрузить данные из файла, если он существует."""
        if self.path.exists():
            try:
                with self.path.open("r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._data = {}
        else:
            self._data = {}

    def _save(self) -> None:
        """Сохранить данные в файл."""
        if not self.autosave:
            return
        with self._lock:
            # Создаём родительскую папку, если её нет
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        """Получить значение по ключу."""
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Установить значение для ключа."""
        with self._lock:
            self._data[key] = value
        self._save()

    def delete(self, key: str) -> None:
        """Удалить запись по ключу."""
        with self._lock:
            if key in self._data:
                del self._data[key]
        self._save()

    def search(self, prefix: str, limit: int = 100) -> List[Tuple[str, Any]]:
        """Найти записи, ключи которых начинаются с prefix."""
        with self._lock:
            result = []
            for k, v in self._data.items():
                if k.startswith(prefix):
                    result.append((k, v))
                    if len(result) >= limit:
                        break
            return result

    def all(self) -> List[Tuple[str, Any]]:
        """Вернуть все записи как список пар (ключ, значение)."""
        with self._lock:
            return list(self._data.items())

    def clear(self) -> None:
        """Удалить все записи."""
        with self._lock:
            self._data.clear()
        self._save()

    def save(self) -> None:
        """Принудительно сохранить данные (если autosave=False)."""
        if not self.autosave:
            self._save()


# === EXAMPLES ===
# # Сохранить
# store.set("user_pref_1", {"speed": 1.5, "loop": True})
# store.set("user_pref_2", "some string")

# # Получить
# pref = store.get("user_pref_1")
# speed = pref.get("speed", 1.0) if pref else 1.0

# # Поиск
# results = store.search("user_")  # список всех записей, начинающихся с "user_"
# for key, value in results:
#     print(key, value)

# # Удалить
# store.delete("user_pref_1")            