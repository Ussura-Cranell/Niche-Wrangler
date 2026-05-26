# src/rule_builder.py
import json
import sys
import re
import os
from pathlib import Path
from typing import List, Dict, Any

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

def clear_console():
    """Кроссплатформенная очистка терминала."""
    os.system('cls' if os.name == 'nt' else 'clear')

def safe_input(prompt: str = "") -> str:
    try:
        return input(prompt).strip()
    except UnicodeDecodeError:
        print("\n[!] Терминал передал битые символы. Повторите ввод.")
        return ""

def print_breadcrumbs(path_stack: List[Dict], op_name: str, count: int):
    crumbs = []
    for step in path_stack:
        name = step.get("name", step.get("type", "").upper())
        c = step.get("count", 0)
        crumbs.append(f"{name}[{c}]")
    crumbs.append(f"{op_name}[{count}]")
    print(f"\n[NAV] ПУТЬ: {' ➜ '.join(crumbs)}")

def validate_and_get_condition(choice: str) -> Dict | None:
    if choice == '1':
        val = safe_input("  [TXT] Слово/фраза: ")
        if not val: return print("  [✗] Значение не может быть пустым.") or None
        return {"type": "contains", "value": val}
    elif choice == '2':
        words_str = safe_input("  [TXT] Слова через запятую (мин. 2): ")
        words = [w.strip() for w in words_str.split(",") if w.strip()]
        if len(words) < 2: return print("  [✗] Для proximity нужно минимум 2 слова.") or None
        dist_str = safe_input("  [D] Макс. расстояние между словами [3]: ") or "3"
        if not dist_str.isdigit() or int(dist_str) < 1: return print("  [✗] Расстояние должно быть ≥ 1.") or None
        return {"type": "proximity", "words": words, "max_distance": int(dist_str)}
    elif choice == '3':
        pat = safe_input("  [SCAN] Регулярное выражение: ")
        try:
            re.compile(pat)
            return {"type": "regex", "pattern": pat}
        except re.error as e:
            return print(f"  [✗] Ошибка в регулярном выражении: {e}") or None
    return None

def build_conditions_block(path_stack: List[Dict], operator_type: str) -> List[Dict]:
    conditions = []
    while True:
        print_breadcrumbs(path_stack, operator_type, len(conditions))
        print("  ┌──────────────────────────────────────")
        print("  │ 1) contains")
        print("  │ 2) proximity")
        print("  │ 3) regex")
        print("  │ 4) Вложенный оператор (AND/OR/NOT)") 
        print("  │ 0) Завершить блок")
        print("  │ u) Отменить последнее")
        print("  │ c) Отменить всё")
        print("  └──────────────────────────────────────")
        
        choice = safe_input("  Ваш выбор: ").lower()
        if choice == '0':
            if operator_type == 'NOT' and len(conditions) != 1:
                print("  [!] NOT требует ровно одно условие.")
                continue
            if not conditions and operator_type in ('AND', 'OR'):
                print("  [!] Блок пуст. Добавьте условие или используйте 'c'.")
                continue
            return conditions
        if choice == 'c': raise Exception("Cancelled")
        if choice == 'u':
            if conditions:
                conditions.pop()
                print("  [✓] Последнее условие удалено.")
            else: print("  [!] Нечего отменять.")
            continue
        if choice == '4':
            print("  Выберите вложенный оператор: 1) AND | 2) OR | 3) NOT")
            op_choice = safe_input("  Оператор: ").strip()
            op_map = {"1": "AND", "2": "OR", "3": "NOT"}
            if op_choice not in op_map: print("  [✗] Введите 1, 2 или 3."); continue
            
            sub_op = op_map[op_choice]
            new_path = path_stack + [{"type": operator_type, "count": len(conditions)}]
            try:
                nested = build_conditions_block(new_path, sub_op)
                conditions.append({"operator": "NOT", "condition": nested[0]} if sub_op == "NOT" else {"operator": sub_op, "conditions": nested})
                print(f"  [✓] Добавлен блок {sub_op} #{len(conditions)}")
            except Exception as e:
                if str(e) == "Cancelled": raise
            continue
        if choice in ('1', '2', '3'):
            cond = validate_and_get_condition(choice)
            if cond:
                conditions.append(cond)
                print(f"  [✓] Добавлено условие #{len(conditions)}")
            continue
        print("  [✗] Неверный ввод.")

def build_root_condition(section_name: str) -> Dict:
    print(f"\n[•] Настройка раздела: {section_name.upper()}")
    print("1) Одиночное условие (contains/proximity/regex)")
    print("2) Группировка оператором (AND/OR/NOT)")
    choice = safe_input("Ваш выбор: ").strip()
    
    if choice == "1":
        print("  Выберите тип: 1) contains | 2) proximity | 3) regex")
        sub = safe_input("  Тип: ").strip()
        cond = validate_and_get_condition(sub)
        return cond if cond else build_root_condition(section_name)
    elif choice == "2":
        print("  Выберите оператор: 1) AND | 2) OR | 3) NOT")
        op = safe_input("  Оператор: ").strip()
        op_map = {"1": "AND", "2": "OR", "3": "NOT"}
        if op not in op_map: return build_root_condition(section_name)
        
        op_type = op_map[op]
        try:
            conds = build_conditions_block([{"type": section_name.upper(), "count": 0}], op_type)
            return {"operator": "NOT", "condition": conds[0]} if op_type == "NOT" else {"operator": op_type, "conditions": conds}
        except Exception as e:
            if str(e) == "Cancelled": raise
    return build_root_condition(section_name)

def format_tree(node, indent=0, is_last=True):
    prefix = "    " * indent + ("└── " if is_last else "├── ")
    lines = []
    if isinstance(node, dict):
        if "operator" in node:
            lines.append(f"{prefix}Оператор: {node['operator']}")
            if node["operator"] == "NOT":
                lines.extend(format_tree(node["condition"], indent + 1, True))
            else:
                for i, cond in enumerate(node["conditions"]):
                    lines.extend(format_tree(cond, indent + 1, i == len(node["conditions"]) - 1))
        elif "type" in node:
            t = node["type"]
            val = node.get("value") or node.get("pattern") or ", ".join(node.get("words", []))
            lines.append(f"{prefix}Тип: {t} | Значение: {val}")
    return lines

def preview_rules(rules: Dict):
    print("\n" + "="*50)
    print("[PRE] ПРЕДВАРИТЕЛЬНЫЙ ПРОСМОТР ПРАВИЛ")
    print("="*50)
    for name, cfg in rules["subsets"].items():
        print(f"\n[SUB] {name}")
        for section in ["include", "exclude"]:
            if section in cfg:
                print(f"  [•] {section.upper()}:")
                for line in format_tree(cfg[section]): print(f"    {line}")
    print("="*50)

def create_rules_interactive():
    clear_console()
    print("[CFG] Конструктор правил фильтрации (v2.1 + YAML)")
    print("[HLP] Подсказки: 'u' = отменить последнее, 'c' = отменить всё")
    print("=" * 50)
    
    rules = {"version": "2.0", "mode": "multi", "subsets": {}}
    
    while True:
        name = safe_input("\n[SUB] Название подмножества (Enter — завершить): ")
        if not name: break
        
        subset_cfg = {}
        try:
            subset_cfg["include"] = build_root_condition("include")
            if safe_input("\n  [ADD] Добавить EXCLUDE? (y/n): ").lower() == 'y':
                subset_cfg["exclude"] = build_root_condition("exclude")
            rules["subsets"][name] = subset_cfg
            print(f"\n[✓] Правило '{name}' добавлено.")
        except Exception as e:
            if str(e) == "Cancelled":
                clear_console()
                print("\n[RST] Создание отменено.")
            continue

    print("\n[RST] Режим применения: 1) multi | 2) first")
    mode = safe_input("Выбор [multi]: ").strip().lower() or "multi"
    rules["mode"] = mode if mode in ("multi", "first") else "multi"

    from rule_engine import RuleValidator
    print("\n[SCAN] Финальная валидация...")
    errors = RuleValidator.validate_rules(rules)
    if errors:
        print("[✗] Найдены ошибки:")
        for e in errors: print(f"  • {e}")
        if safe_input("Продолжить сохранение? (y/n): ").lower() != 'y': 
            clear_console()
            return

    preview_rules(rules)
    
    print("\n[SAV] Формат сохранения: YAML")
    # print("1) JSON (стандартный)")
    # print("2) YAML (по-умолчанию)")
    fmt = "2" #safe_input("Ваш выбор [2]: ").strip() or "2"
    
    ext = "yaml" if (fmt == "2" and HAS_YAML) else "json"
    if fmt == "2" and not HAS_YAML:
        print("[!] PyYAML не установлен. Сохраняю в JSON.")
        ext = "json"

    output = Path(f"rules.{ext}")
    with open(output, "w", encoding="utf-8") as f:
        if ext == "yaml":
            yaml.dump(rules, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        else:
            json.dump(rules, f, ensure_ascii=False, indent=2)
            
    # clear_console()
    print(f"\n[DON] Сохранено: {output}")
    print("[RUN] Запустите: python main.py")

if __name__ == "__main__":
    create_rules_interactive()
