import json, os
import config

class DataManager:
    def __init__(self):
        default_ferts = [
            {"name": "入门催熟", "type": "speed", "effect": 6.0, "cost": 15.0},
            {"name": "普通催熟", "type": "speed", "effect": 15.0, "cost": 60.0},
            {"name": "优质催化", "type": "speed", "effect": 25.0, "cost": 180.0},
            {"name": "入门增产", "type": "yield", "effect": 1.5, "cost": 120.0},
            {"name": "普通增产", "type": "yield", "effect": 2.5, "cost": 780.0}
        ]

        self.data = {
            "settings": config.DEFAULT_SETTINGS.copy(), 
            "crops": [], 
            "display_columns": ["verified", "name", "type", "process_status", "best_strategy", "best_profit", "seed_price"],
            "custom_column_names": {},
            "fertilizers": default_ferts 
        }
        self.runtime_col_widths = {}
        self.debug_logs = []
        self.load_data()

    def rebuild_dynamic_columns(self):
        config.ALL_COLS = {
            "type": "类型", "verified": "✅ 核对", "process_status": "🏭 加工能力",
            "best_strategy": "🔥 最优策略", "best_profit": "💰 最高时薪"
        }
        for k, v in config.DB_KEY_MAP.items():
            if k != "name": config.ALL_COLS[k] = f"{v}"

        config.COLUMN_GROUPS = {}
        config.FERT_COL_MAP = {}
        
        fert_names = ["无肥料"] + [f["name"] for f in self.data["fertilizers"]]
        for f in fert_names:
            if f != "无肥料": config.FERT_COL_MAP[f] = []
            
        for s in config.STRATS:
            parent_key = f"{s}_无肥料"
            config.ALL_COLS[parent_key] = f"{s}(无肥料)"
            children = []
            for f in fert_names:
                if f == "无肥料": continue
                child_key = f"{s}_{f}"
                children.append(child_key)
                config.ALL_COLS[child_key] = f"↳ {f}"
                config.FERT_COL_MAP[f].append(child_key)
            config.COLUMN_GROUPS[parent_key] = children

    def load_data(self):
        if not os.path.exists(config.DATA_FILE): 
            self.rebuild_dynamic_columns()
            return
        try:
            with open(config.DATA_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                # 1. 刷新基础设置
                self.data["settings"].update(loaded.get("settings", {}))
                # 2. 刷新作物与索引
                self.data["crops"] = loaded.get("crops", [])
                for i, c in enumerate(self.data["crops"]): 
                    c.setdefault("_db_index", i)
                # 3. 核心：强制同步报表与对比页的列宽缓存
                self.runtime_col_widths = loaded.get("tksheet_widths", {}) 
                self.data["cmp_tksheet_widths"] = loaded.get("cmp_tksheet_widths", {})
                # 4. 刷新列顺序与自定义名称
                self.data["display_columns"] = loaded.get("display_columns", self.data["display_columns"])
                self.data["custom_column_names"] = loaded.get("custom_column_names", {})
                # 5. 刷新肥料数据
                if "fertilizers" in loaded:
                    self.data["fertilizers"] = loaded["fertilizers"]                
                self.rebuild_dynamic_columns()
                valid_ids = set(config.ALL_COLS.keys()) | set(config.DB_KEY_MAP.keys()) | {"process_status", "best_profit", "best_strategy", "verified", "type"}
                self.data["display_columns"] = [c for c in self.data["display_columns"] if c in valid_ids]
        except Exception as e: 
            self.debug_print(f"[DEBUG] ❌ 加载失败: {e}")

    def save_data(self, report_sheet=None):
        try:
            # 1. 🌟 核心修复：如果内存里有实时宽度，先同步给 data 字典
            # 这样即使不传 report_sheet，保存的也是最新的内存值
            if hasattr(self, 'runtime_col_widths') and self.runtime_col_widths:
                self.data["tksheet_widths"] = self.runtime_col_widths

            # 2. 如果传了 sheet，则抓取最实时的 UI 宽度（覆盖内存值）
            if report_sheet:
                try: 
                    # 这里建议同时更新内存备份，保证两边完全一致
                    new_widths = {c_id: report_sheet.column_width(i) for i, c_id in enumerate(self.data["display_columns"]) if i < report_sheet.total_columns()}
                    self.data["tksheet_widths"] = new_widths
                    self.runtime_col_widths = new_widths # 同步更新内存备份
                except: 
                    raise Exception("报表保存失败,请检查报表是否正确打开")
            
            # 3. 正常存盘逻辑
            save_dict = self.data.copy()
            save_dict["crops"] = sorted(self.data["crops"], key=lambda x: x.get("_db_index", 0))
            
            with open(config.DATA_FILE, 'w', encoding='utf-8') as f: 
                json.dump(save_dict, f, ensure_ascii=False, indent=4)
                
        except Exception as e: 
            self.debug_print(f"[DEBUG] ❌ 保存失败: {e}")

    def debug_print(self, *args):
        msg = " ".join(map(str, args)); print(msg); self.debug_logs.append(msg)
        if len(self.debug_logs) > 500: self.debug_logs.pop(0)

    def fix_custom_db_order(self):
        t_order = ["牧草", "小麦", "甜菜", "空心菜", "卷心菜", "大蒜", "土豆", "山兰稻", "黄瓜", "花生", "大葱", "冬油菜", "大豆", "甘蔗", "辣椒", "青葡萄", "番茄", "西瓜", "樱桃萝卜", "胡萝卜", "红葡萄", "南瓜", "玉米", "蓝莓", "草莓", "樱桃番茄", "苹果树", "橘子树", "雪梨树", "香蕉树", "荔枝树"]
        self.data["crops"].sort(key=lambda c: (0, t_order.index(c.get("name"))) if c.get("name") in t_order else (1, c.get("_db_index", 999)))
        for i, c in enumerate(self.data["crops"]): c["_db_index"] = i
        self.save_data()
        self.debug_print("[DEBUG] 🛠️ 已重排")