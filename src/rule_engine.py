# src/rule_engine.py
import json
import re
import pandas as pd
from pathlib import Path
from typing import Dict, List, Union, Any
import logging

logger = logging.getLogger(__name__)

# Опциональная поддержка YAML
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

class Condition:
    """Базовый класс для всех условий"""
    def evaluate(self, text: str) -> bool: raise NotImplementedError
    def evaluate_series(self, series: pd.Series) -> pd.Series: raise NotImplementedError
    def validate(self) -> List[str]: return []

class ContainsCondition(Condition):
    def __init__(self, value: str, case_sensitive: bool = False):
        self.value = value.lower() if not case_sensitive else value
        self.case_sensitive = case_sensitive

    def evaluate_series(self, series: pd.Series) -> pd.Series:
        return series.str.contains(self.value, case=self.case_sensitive, na=False)

    def evaluate(self, text: str) -> bool:
        if not self.case_sensitive: text = text.lower()
        return self.value in text

    def validate(self) -> List[str]:
        return [] if self.value else ["Пустое значение в contains"]

class AndCondition(Condition):
    def __init__(self, conditions: List[Condition]):
        self.conditions = conditions
    def evaluate_series(self, series: pd.Series) -> pd.Series:
        mask = pd.Series(True, index=series.index)
        for cond in self.conditions:
            mask &= cond.evaluate_series(series)
        return mask
    def evaluate(self, text: str) -> bool: return all(c.evaluate(text) for c in self.conditions)
    def validate(self) -> List[str]: return [e for c in self.conditions for e in c.validate()]

class OrCondition(Condition):
    def __init__(self, conditions: List[Condition]):
        self.conditions = conditions
    def evaluate_series(self, series: pd.Series) -> pd.Series:
        mask = pd.Series(False, index=series.index)
        for cond in self.conditions:
            mask |= cond.evaluate_series(series)
        return mask
    def evaluate(self, text: str) -> bool: return any(c.evaluate(text) for c in self.conditions)
    def validate(self) -> List[str]: return [e for c in self.conditions for e in c.validate()]

class NotCondition(Condition):
    def __init__(self, condition: Condition):
        self.condition = condition
    def evaluate_series(self, series: pd.Series) -> pd.Series:
        return ~self.condition.evaluate_series(series)
    def evaluate(self, text: str) -> bool: return not self.condition.evaluate(text)
    def validate(self) -> List[str]: return self.condition.validate()

class ConditionFactory:
    _registry = {"contains": ContainsCondition}
    
    @classmethod
    def create(cls, config: Dict[str, Any]) -> Condition:
        if "operator" in config:
            op = config["operator"].upper()
            conds = [cls.create(c) for c in config.get("conditions", [])]
            if op == "AND": return AndCondition(conds)
            if op == "OR": return OrCondition(conds)
            if op == "NOT": return NotCondition(conds[0]) if conds else NotCondition(ContainsCondition(""))
            raise ValueError(f"Неизвестный оператор: {op}")
        
        cond_type = config.get("type", "contains")
        if cond_type not in cls._registry:
            raise ValueError(f"Неизвестный тип условия: {cond_type}")
        return cls._registry[cond_type](**{k: v for k, v in config.items() if k != "type"})

class RuleValidator:
    @classmethod
    def validate_rules(cls, rules: Dict) -> List[str]:
        errors = []
        if "subsets" not in rules or not isinstance(rules["subsets"], dict):
            return ["Отсутствует или неверный раздел 'subsets'"]
        for name, cfg in rules["subsets"].items():
            for section in ["include", "exclude"]:
                if section in cfg and isinstance(cfg[section], dict):
                    try:
                        cond = ConditionFactory.create(cfg[section])
                        errors.extend([f"[{name}][{section}] {e}" for e in cond.validate()])
                    except Exception as e:
                        errors.append(f"[{name}][{section}] Ошибка парсинга: {e}")
        return errors

class RuleEngine:
    def __init__(self, rules_file: Union[str, Path] = "rules.json"):
        self.rules = self._load(rules_file)
        errors = RuleValidator.validate_rules(self.rules)
        if errors:
            raise ValueError("Ошибки в правилах:\n" + "\n".join(f"  • {e}" for e in errors))
        self._compiled = {}
        self._compile_all()

    def _load(self, path: Union[str, Path]) -> Dict:
        p = Path(path)
        if not p.exists(): raise FileNotFoundError(f"Файл правил не найден: {p}")
        with open(p, 'r', encoding='utf-8') as f:
            if p.suffix.lower() in ['.yaml', '.yml']:
                if not HAS_YAML: raise ImportError("Установите pyyaml: pip install pyyaml")
                return yaml.safe_load(f)
            return json.load(f)

    def _compile_all(self):
        for name, cfg in self.rules.get("subsets", {}).items():
            if "include" in cfg:
                self._compiled[f"{name}_include"] = ConditionFactory.create(cfg["include"])
            if "exclude" in cfg:
                self._compiled[f"{name}_exclude"] = ConditionFactory.create(cfg["exclude"])

    def apply(self, df: pd.DataFrame, subset_name: str, name_col: str = "Name") -> pd.DataFrame:
        if subset_name not in self.rules.get("subsets", {}):
            raise KeyError(f"Подмножество '{subset_name}' не найдено")
        
        mask = pd.Series(True, index=df.index)
        key_inc = f"{subset_name}_include"
        key_exc = f"{subset_name}_exclude"

        if key_inc in self._compiled:
            mask &= self._compiled[key_inc].evaluate_series(df[name_col])
        if key_exc in self._compiled:
            mask &= ~self._compiled[key_exc].evaluate_series(df[name_col])

        return df[mask].copy()

    def apply_all(self, df: pd.DataFrame, name_col: str = "Name") -> Dict[str, pd.DataFrame]:
        results = {}
        mode = self.rules.get("mode", "multi")
        remaining_idx = set(df.index) if mode == "first" else None

        for name in self.rules["subsets"].keys():
            subset_df = self.apply(df, name, name_col)
            if mode == "first" and remaining_idx is not None:
                unique_idx = subset_df.index.intersection(remaining_idx)
                subset_df = subset_df.loc[unique_idx]
                remaining_idx -= set(unique_idx)
            
            if not subset_df.empty:
                results[name] = subset_df
                logger.info(f"[✓] {name}: {len(subset_df)} товаров")
            else:
                logger.warning(f"[!] {name}: пусто")

        if mode == "first" and remaining_idx:
            results["_остаток"] = df.loc[list(remaining_idx)].copy()
            logger.info(f"[i] Остаток: {len(results['_остаток'])} товаров")

        return results

    def test(self, text: str, subset_name: str, condition_type: str = "include") -> bool:
        key = f"{subset_name}_{condition_type}"
        cond = self._compiled.get(key)
        return cond.evaluate(text) if cond else False