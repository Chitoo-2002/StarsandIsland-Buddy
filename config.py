import os

# --- 路径配置 ---
DOCUMENTS_PATH = os.path.join(os.path.expanduser('~'), 'Documents')
APP_DIR = os.path.join(DOCUMENTS_PATH, 'FarmManagerData')
DATA_FILE = os.path.join(APP_DIR, 'farm_data_pro.json')

if not os.path.exists(APP_DIR):
    os.makedirs(APP_DIR)

# --- 默认参数 ---
DEFAULT_SETTINGS = {
    "sugar_cost": 75.0, "salt_cost": 75.0,
    "price_flour": 10.0, "price_pulp": 15.0, "price_juice": 15.0, "price_sugar": 25.0,
    "f_eg_c": 15.0, "f_eg_t": 6.0, "f_ng_c": 60.0, "f_ng_t": 15.0,
    "f_pg_c": 180.0, "f_pg_t": 25.0,
    "f_ey_c": 120.0, "f_ey_m": 1.5, "f_ny_c": 780.0, "f_ny_m": 2.5
}

# --- 汉化映射 ---
SETTINGS_LANG_MAP = {
    "sugar_cost": "糖成本 (做酱用)", "salt_cost": "盐成本 (做腌菜用)",
    "price_flour": "售价: 面粉 (小麦)", "price_pulp": "售价: 果肉 (水果)",
    "price_juice": "售价: 蔬菜汁", "price_sugar": "售价: 糖 (甘蔗/甜菜)",
    "f_eg_c": "[入门催熟] 成本", "f_eg_t": "[入门催熟] 减时",
    "f_ng_c": "[普通催熟] 成本", "f_ng_t": "[普通催熟] 减时",
    "f_pg_c": "[优质催化] 成本", "f_pg_t": "[优质催化] 减时",
    "f_ey_c": "[入门增产] 成本", "f_ey_m": "[入门增产] 倍率",
    "f_ny_c": "[普通增产] 成本", "f_ny_m": "[普通增产] 倍率"
}

# --- 数据库列定义 ---
DB_KEY_MAP = {
    "name": "作物名称", "verified": "数据核对", "is_tree": "是否果树",
    "primary_type": "一级产物类型", "primary_qty": "一级产出量",
    "can_jam": "可做果酱", "jam_price": "果酱售价", "jam_time": "酿造时间",
    "can_pickle": "可做腌菜", "pickle_price": "腌菜售价", "pickle_time": "腌制时间",
    "seed_price": "种子价", "raw_price": "直售价", "h_count": "次数", "h_qty": "产量",
    "t1": "一轮", "t2": "二轮", "t3": "三轮"
}
DB_DISPLAY_MAP = {v: k for k, v in DB_KEY_MAP.items()}

# --- 列定义与分组 ---
ALL_COLS = {
    "type": "类型", "verified": "✅ 核对", "process_status": "🏭 加工能力",
    "best_strategy": "🔥 最优策略", "best_profit": "💰 最高时薪"
}

for k, v in DB_KEY_MAP.items():
    if k not in ["name"]: ALL_COLS[k] = f"{v}" # 移除 "原:" 前缀，保持清爽

COLUMN_GROUPS = {}
STRATS = ["直接出售", "一级加工", "果酱", "腌菜"]
FERTS = ["无肥料", "入门催熟", "普通催熟", "优质催化", "入门增产", "普通增产"]
FERT_COL_MAP = {f: [] for f in FERTS if f != "无肥料"}

for s in STRATS:
    parent_key = f"{s}_无肥料"
    ALL_COLS[parent_key] = f"{s}(无肥料)"
    
    children = []
    for f in FERTS:
        if f == "无肥料": continue
        child_key = f"{s}_{f}"
        children.append(child_key)
        # 仅显示肥料名，视觉更清爽
        ALL_COLS[child_key] = f"↳ {f}"
        
        if f in FERT_COL_MAP:
            FERT_COL_MAP[f].append(child_key)
            
    COLUMN_GROUPS[parent_key] = children