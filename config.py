import os
import ctypes
from ctypes import wintypes

def get_windows_documents_path():
    """调用系统 API 获取 Windows 真实的文档路径"""
    # CSIDL_PERSONAL = 5 代表“我的文档”文件夹
    CSIDL_PERSONAL = 5
    SHGFP_TYPE_CURRENT = 0
    
    buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
    # 调用 SHGetFolderPathW
    ctypes.windll.shell32.SHGetFolderPathW(None, CSIDL_PERSONAL, None, SHGFP_TYPE_CURRENT, buf)
    return buf.value

# --- 路径配置 ---
try:
    # 尝试获取真实的文档路径
    DOCUMENTS_PATH = get_windows_documents_path()
except Exception:
    # 如果是非 Windows 系统或获取失败，再退回到原来的逻辑作为保底
    DOCUMENTS_PATH = os.path.join(os.path.expanduser('~'), 'Documents')

APP_DIR = os.path.join(DOCUMENTS_PATH, 'FarmManagerData')
DATA_FILE = os.path.join(APP_DIR, '存档数据.json')

if not os.path.exists(APP_DIR):
    os.makedirs(APP_DIR)

# --- 默认参数 (移除肥料成本和效果) ---
DEFAULT_SETTINGS = {
    "sugar_cost": 75.0, "salt_cost": 75.0,
    "price_flour": 10.0, "price_pulp": 15.0, "price_juice": 15.0, "price_sugar": 25.0
}

# --- 汉化映射 (移除肥料) ---
SETTINGS_LANG_MAP = {
    "sugar_cost": "糖成本 (做酱用)", "salt_cost": "盐成本 (做腌菜用)",
    "price_flour": "售价: 面粉 (小麦)", "price_pulp": "售价: 果肉 (水果)",
    "price_juice": "售价: 蔬菜汁", "price_sugar": "售价: 糖 (甘蔗/甜菜)"
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

# --- 占位字典 (稍后由 main.py 动态生成) ---
ALL_COLS = {}
COLUMN_GROUPS = {}
FERT_COL_MAP = {}
STRATS = ["直接出售", "一级加工", "果酱", "腌菜"]