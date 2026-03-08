import tkinter as tk
from tkinter import ttk, messagebox
import json, os, config
from logic import calc_profits
from ui_popups import CropEditor, ColumnManager, FormulaViewer, set_popup_geo
from tksheet import Sheet
import tkinter.font as tkfont

class FarmManagerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("星砂岛作物收益计算 V1.0 (动态肥料版)")
        self.geometry("1400x850")
        self.setup_styles()
        
        # 默认肥料 (当 json 中没有时加载)
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
            "fertilizers": default_ferts # ⚡ 新增：肥料列表总线
        }
        
        self.current_sort_col, self.current_sort_reverse = None, False
        self.runtime_col_widths = {}
        self.press_x = 0
        self.debug_logs = []

        self.load_data()
        
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill='both', expand=True, padx=8, pady=8)
        self.tab_report = ttk.Frame(self.notebook)
        self.tab_db = ttk.Frame(self.notebook)
        self.tab_settings = ttk.Frame(self.notebook)
        self.tab_fert = ttk.Frame(self.notebook) # ⚡ 新增：肥料实验室 Frame
        self.tab_compare = ttk.Frame(self.notebook) # ⚡ 新增：对比页面 Frame

        self.notebook.add(self.tab_report, text=' 📊 收益分析报表 ')
        self.notebook.add(self.tab_compare, text=' ⚖️ 施肥效益对比 ') # ⚡ 新增：建议放在报表旁边
        self.notebook.add(self.tab_db, text=' 💾 核心数据库 ')
        self.notebook.add(self.tab_settings, text=' ⚙️ 参数设置 ')
        self.notebook.add(self.tab_fert, text=' 🧪 肥料实验室 ') # ⚡ 新增：标签页
        
        # ⚡ 注意：肥料管理 UI 将在这里添加，但由于你只让我提供关键代码，
        # UI 部分我会在你确认这三层逻辑没问题后再发给你，避免代码太长你粘错。
        
        self.build_report_tab(); self.build_compare_tab(); self.build_db_tab(); self.build_settings_tab()
        self.build_fert_tab()

    def rebuild_dynamic_columns(self):
        """⚡ 核心！根据当前的 self.data['fertilizers'] 动态生成 config 配置"""
        # 1. 重置 ALL_COLS
        config.ALL_COLS = {
            "type": "类型", "verified": "✅ 核对", "process_status": "🏭 加工能力",
            "best_strategy": "🔥 最优策略", "best_profit": "💰 最高时薪"
        }
        for k, v in config.DB_KEY_MAP.items():
            if k != "name": config.ALL_COLS[k] = f"{v}"

        # 2. 动态构建 COLUMN_GROUPS
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
            
        # 3. 同步全局顺序
        self.global_fert_order = [f["name"] for f in self.data["fertilizers"]]

    def load_data(self):
        if not os.path.exists(config.DATA_FILE): 
            self.rebuild_dynamic_columns() # 哪怕没有存档，也要初始化列配置
            return
        try:
            with open(config.DATA_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                self.data["settings"].update(loaded.get("settings", {}))
                self.data["crops"] = loaded.get("crops", [])
                for i, c in enumerate(self.data["crops"]): c.setdefault("_db_index", i)
                self.runtime_col_widths = loaded.get("tksheet_widths", {}) 
                self.data["display_columns"] = loaded.get("display_columns", self.data["display_columns"])
                self.data["custom_column_names"] = loaded.get("custom_column_names", {})
                # ⚡ 读取肥料
                if "fertilizers" in loaded:
                    self.data["fertilizers"] = loaded["fertilizers"]
                
                # ⚡ 读取完毕后，必须立刻重构动态列！
                self.rebuild_dynamic_columns()
        except Exception as e: 
            print(f"[DEBUG] ❌ 加载失败: {e}")
            self.rebuild_dynamic_columns() # 失败也要保底重构

    def save_data(self):
        try:
            if hasattr(self, 'sheet'):
                try: self.data["tksheet_widths"] = {c_id: self.sheet.column_width(i) for i, c_id in enumerate(self.data["display_columns"]) if i < self.sheet.total_columns()}
                except: pass
            save_dict = self.data.copy()
            save_dict["crops"] = sorted(self.data["crops"], key=lambda x: x.get("_db_index", 0))
            with open(config.DATA_FILE, 'w', encoding='utf-8') as f: json.dump(save_dict, f, ensure_ascii=False, indent=4)
        except Exception as e: self.debug_print(f"[DEBUG] ❌ 保存失败: {e}")

    def setup_styles(self):
        style = ttk.Style(); style.theme_use("clam")
        style.configure("TNotebook", background="#f5f5f7"); style.configure("TNotebook.Tab", padding=[18, 6], font=("微软雅黑", 10))
        style.configure("TButton", font=("微软雅黑", 9))
        style.map("TEntry", fieldbackground=[("disabled", "#e0e0e0")]); style.map("TCombobox", fieldbackground=[("disabled", "#e0e0e0")])

    def debug_print(self, *args):
        msg = " ".join(map(str, args)); print(msg); self.debug_logs.append(msg)
        if len(self.debug_logs) > 500: self.debug_logs.pop(0)

    def open_debug_window(self):
        w = tk.Toplevel(self); w.title("🐛 开发者调试控制台"); w.geometry("700x500")
        top_f = ttk.Frame(w); top_f.pack(fill='x', padx=10, pady=5)
        ttk.Button(top_f, text="🔄 刷新日志", command=lambda: txt.delete(1.0, tk.END) or txt.insert(tk.END, "\n".join(self.debug_logs)) or txt.see(tk.END)).pack(side='left', padx=5)
        ttk.Button(top_f, text="🛠️ 按标准预设重排", command=self.fix_custom_db_order).pack(side='right', padx=5)
        txt = tk.Text(w, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4"); txt.pack(fill='both', expand=True, padx=10, pady=5)
        txt.insert(tk.END, "\n".join(self.debug_logs)); txt.see(tk.END)

    def fix_custom_db_order(self):
        if not messagebox.askyesno("确认", "重置为标准预设顺序？"): return
        
        t_order = ["牧草", "小麦", "甜菜", "空心菜", "卷心菜", "大蒜", "土豆", "山兰稻", "黄瓜", "花生", "大葱", "冬油菜", "大豆", "甘蔗", "辣椒", "青葡萄", "番茄", "西瓜", "樱桃萝卜", "胡萝卜", "红葡萄", "南瓜", "玉米", "蓝莓", "草莓", "樱桃番茄", "苹果树", "橘子树", "雪梨树", "香蕉树", "荔枝树"]
        self.data["crops"].sort(key=lambda c: (0, t_order.index(c.get("name"))) if c.get("name") in t_order else (1, c.get("_db_index", 999)))
        for i, c in enumerate(self.data["crops"]): c["_db_index"] = i
        self.save_data(); self.reload_from_db(); self.debug_print("[DEBUG] 🛠️ 已重排")


    def safe_right_click(self, event):
        c = self.sheet.identify_column(event); r = self.sheet.identify_row(event) if event.widget != self.sheet.CH else None
        if c is None: return
        col_id = self.data["display_columns"][c]
        m = tk.Menu(self, tearoff=0, font=("微软雅黑", 9))
        
        if event.widget == self.sheet.CH:
            m.add_command(label="✏️ 修改列显示名称", command=lambda: self.rename_column(col_id))
            if col_id in config.COLUMN_GROUPS:
                is_ex = any(k in self.data["display_columns"] for k in config.COLUMN_GROUPS[col_id])
                m.add_command(label="➖ 收起肥料详情" if is_ex else "➕ 展开肥料详情", command=lambda: self.toggle_column_group(col_id, not is_ex))
        else:
            if r is not None:
                self.sheet.set_currently_selected(r, c)
                if col_id == "verified": m.add_command(label="✅ 切换核对状态", command=lambda: self.toggle_verified(r))
                m.add_command(label="✏️ 编辑作物属性", command=self.open_edit_win)
                if col_id not in list(config.DB_KEY_MAP.keys()) + ["type", "process_status", "verified", "name"] or col_id == "best_profit":
                    n = self.sheet.get_cell_data(r, self.data["display_columns"].index("name")); strat = col_id
                    if col_id in ["best_profit", "best_strategy"]:
                        # ⚡ 修复：在这里补上了第三个参数 self.data.get("fertilizers", [])
                        P, _ = calc_profits(next((x for x in self.data["crops"] if x["name"] == n), None), self.data["settings"], self.data.get("fertilizers", []))
                        strat = max({k:v for k,v in P.items() if v is not None}, key=P.get) if P else None
                    if strat:
                        m.add_separator(); m.add_command(label="📊 全方案分析对比", command=lambda: self.show_details_popup(n))
                        m.add_command(label=f"🔢 查看 [{config.ALL_COLS.get(strat, strat).replace('↳ ', '')}] 计算公式", command=lambda: FormulaViewer.show(self, n, strat, self))
        m.post(event.x_root, event.y_root)
        
    def rename_column(self, col_id):
        from tkinter import simpledialog
        # 获取当前名称，并将真实的换行符转回成 "\n" 字符方便用户编辑
        old_name = self.get_col_display_name(col_id).replace("\n", "\\n")
        
        new_name = simpledialog.askstring("重命名列", 
            f"请输入列 [{col_id}] 的新显示名称:\n(输入 \\n 代表手动换行，留空恢复默认)", 
            initialvalue=old_name)
        
        if new_name is not None:
            if new_name.strip() == "":
                self.data["custom_column_names"].pop(col_id, None)
            else:
                # ⚡ 核心修复：将用户输入的文本 "\n" 转换为代码识别的换行符
                final_name = new_name.replace("\\n", "\n").strip()
                self.data["custom_column_names"][col_id] = final_name
            
            self.save_data()
            self.refresh_list(keep_widths=True)

    
    
    def exec_sync_width(self, event):
        try:
            if isinstance(event, dict) and 'resized' in event and event['resized'].get('columns', {}):
                c_idx = list(event['resized']['columns'].keys())[0]
                new_w = max(40, event['resized']['columns'][c_idx].get('new_size', 40))
                self.sheet.column_width(c_idx, width=new_w)
                
                col_id = self.data["display_columns"][c_idx]
                self.runtime_col_widths[col_id] = new_w
                self.save_data()
        except Exception as e: 
            self.debug_print(f"[DEBUG] ❌ 宽度处理报错: {e}")

    def get_col_display_name(self, col_id):
        custom_map = self.data.get("custom_column_names", {})
        if col_id in custom_map: return custom_map[col_id]
        if col_id == "verified": return "数据\n核对"
        if col_id == "name": return "作物名称"
        
        base = config.ALL_COLS.get(col_id, col_id).replace("↳ ", "").strip()
        
        for p, kids in config.COLUMN_GROUPS.items():
            if col_id in kids:
                parent_raw = config.ALL_COLS.get(p, p).strip()
                # 剔除父级名称中的 "(无肥料)" 后缀
                parent_clean = parent_raw.split('(')[0].split('（')[0].strip()
                # 移除子列名前导的冒号
                clean_base = base.lstrip(':').strip()
                return f"{parent_clean}\n{clean_base}"
        return base

    def refresh_list(self, keep_widths=False, initial=False):
        cols = self.data["display_columns"]
        self.sheet.headers([self.get_col_display_name(c) for c in cols])
        
        rows, red_coords, bold_coords = [], [], []
        for r_idx, c in enumerate(self.data["crops"]):
            try:
                P, _ = calc_profits(c, self.data["settings"], self.data["fertilizers"])
                rm = {"name": c.get("name"), "type": "果树" if c.get("is_tree") else "普通", "verified": "☑" if c.get('verified') else "☐"}
                rm["process_status"] = f"{'●' if c.get('primary_type', '无') != '无' else '○'}{c.get('primary_type', '无')} {'●' if c.get('can_jam') else '○'}酱 {'●' if c.get('can_pickle') else '○'}菜"
                for k in config.DB_KEY_MAP: 
                    if k not in ["name", "verified", "is_tree"]: rm[k] = str(c.get(k, "-"))
                
                if P and any(v is not None for v in P.values()):
                    valid = {k:v for k,v in P.items() if v is not None}
                    best_k = max(valid, key=valid.get); best_v = valid[best_k]
                    rm["best_profit"], rm["best_strategy"] = f"{best_v:.2f}", best_k
                    for k, v in P.items():
                        if v is not None:
                            rm[k] = f"{v:.2f}"
                            # 记录红字坐标
                            if k in cols and v < 0: red_coords.append((r_idx, cols.index(k)))
                    # 记录蓝字坐标
                    if best_v > 0:
                        if "best_profit" in cols: bold_coords.append((r_idx, cols.index("best_profit")))
                        if best_k in cols: bold_coords.append((r_idx, cols.index(best_k)))
                else: rm["best_profit"], rm["best_strategy"] = "0.00", "无"
                rows.append([rm.get(cid, "-") for cid in cols])
            except: continue

        # 1. 设置数据与基础对齐
        self.sheet.set_sheet_data(rows, reset_col_positions=True)
        self.sheet.align(align="center", redraw=False)
        self.sheet.header_align(align="center", redraw=False)
        try: self.sheet.CH.align("center")
        except: pass

        # 2. 清除并重新设置背景色
        self.sheet.dehighlight_all()
        # 斑马线底色
        for i in range(len(rows)):
            if i % 2 == 1: self.sheet.highlight_rows(rows=[i], bg="#f4f7fb")

        # 肥料子列颜色分组
        group_colors, color_idx = ["#eef5ff", "#fff8ed", "#f0fff0", "#fff0f5"], 0
        for p, kids in config.COLUMN_GROUPS.items():
            if p in cols:
                bg_color = group_colors[color_idx % len(group_colors)]; color_idx += 1
                for k in kids:
                    if k in cols: self.sheet.highlight_columns(columns=[cols.index(k)], bg=bg_color)

        # 3. 核心回归：设置带背景色的文字样式
        # 负值：红字淡红底 (使用 highlight_cells 最稳)
        for r, c in red_coords:
            self.sheet.highlight_cells(row=r, column=c, fg="#d93025", bg="#fef7f7")

        # 最优值：蓝字淡蓝底
        for r, c in bold_coords:
            self.sheet.highlight_cells(row=r, column=c, fg="#1a73e8", bg="#f1f8fe")
            # 尝试通过底层 MT 加粗，不强求，如果失败也不崩
            self.sheet.MT.cell_options[(r, c)]['font'] = ("微软雅黑", 10, "bold")
            

        # 4. 恢复列宽
        if self.runtime_col_widths:
            for i, col_id in enumerate(cols):
                w = self.runtime_col_widths.get(col_id)
                if w is None: w = self.runtime_col_widths.get(str(i), 100)
                self.sheet.column_width(i, width=int(w))
        
        self.sheet.refresh()

    def show_details(self, c):
        w = tk.Toplevel(self); w.title(f"收益分析: {c['name']}"); set_popup_geo(w, 720, 780); w.configure(bg="white")
        tk.Label(w, text=f"作物: {c['name']} 方案时薪对比", font=("微软雅黑", 14, "bold"), bg="white", pady=18).pack()
        con = tk.Frame(w, bg="white"); con.pack(fill='both', expand=True, padx=25, pady=10)
        tv = ttk.Treeview(con, columns=("s", "p"), show="headings", height=16); tv.pack(side='left', fill='both', expand=True)
        sc = ttk.Scrollbar(con, command=tv.yview); sc.pack(side='right', fill='y'); tv.config(yscrollcommand=sc.set)
        tv.heading("s", text=" 策略组合名称 "); tv.heading("p", text=" 预计时薪 ")
        tv.column("s", width=380, anchor="center"); tv.column("p", width=160, anchor="center")
        
        P, F = calc_profits(c, self.data["settings"], self.data["fertilizers"])
        data_list = sorted([{'s': k, 'p': v} for k, v in P.items() if v is not None], key=lambda x: x['p'], reverse=True)
        if data_list:
            mv = max(d['p'] for d in data_list)
            for item in data_list:
                tv.insert("", "end", values=(item['s'], f"{item['p']:.2f}"), tags=('max' if item['p'] == mv else ('min' if item['p'] < 0 else 'norm'),))
        tv.tag_configure('max', foreground='#1a73e8', font=('微软雅黑', 10, 'bold')); tv.tag_configure('min', foreground='#d93025')
        def dbl_f(e):
            sel = tv.selection()
            if sel and tv.item(sel[0])['values'][0] in F: FormulaViewer.render(w, c['name'], tv.item(sel[0])['values'][0], F[tv.item(sel[0])['values'][0]])
        tv.bind("<Double-1>", dbl_f)

    def reload_from_db(self):
        self.debug_print("[DEBUG] 🔄 接收到刷新数据指令...")
        order = list(self.data["display_columns"]); self.load_data(); self.data["display_columns"] = order 
        self.current_sort_col, self.current_sort_reverse = None, False
        self.data["crops"].sort(key=lambda x: x.get("_db_index", 0))
        self.refresh_list(keep_widths=True); self.refresh_db()

    def show_details_popup(self, n):
        c = next((x for x in self.data["crops"] if x["name"] == n), None); self.show_details(c) if c else None

    def build_report_tab(self):
        self.sheet = Sheet(self.tab_report, align="center", header_align="center", theme="light blue", 
                           font=("微软雅黑", 10, "normal"), header_font=("微软雅黑", 10, "bold"), 
                           row_height=28, header_height=52)
        # ⚡ 诊断代码：运行后在控制台看看输出
        #print("\n" + "="*50 + "\nSheet 对象的所有方法预览：\n", [m for m in dir(self.sheet) if not m.startswith("_")], "\n" + "="*50)
        self.sheet.pack(fill="both", expand=True)
        self.sheet.hide("row_index")
        
        self.sheet.enable_bindings("move_columns", "column_width_resize", "drag_select", "single_select", 
                                   "row_select", "column_select", "arrowkeys", "copy", "rc_select")
        self.sheet.disable_bindings("zoom") # 禁用 Ctrl+滚轮缩放

        self.sheet.CH.bind("<Double-Button-1>", self.on_ch_double_click, add="+")
        self.sheet.CH.bind("<Button-3>", self.safe_right_click, add="+")
        self.sheet.MT.bind("<Button-3>", self.safe_right_click, add="+")
        
        self.sheet.extra_bindings("move_columns", self.exec_sync_drag)
        self.sheet.extra_bindings("column_width_resize", self.exec_sync_width)

        bf = ttk.Frame(self.tab_report); bf.pack(side='bottom', fill='x', pady=8)
        # ⚡ 删除了紧凑模式按钮
        ttk.Button(bf, text="🔄 刷新数据", command=self.reload_from_db).pack(side='left', padx=10)
        ttk.Button(bf, text="💾 保存排序到数据库", command=self.sync_sort_to_db).pack(side='left')
        ttk.Button(bf, text="⚙️ 自定义列", command=lambda: ColumnManager(self)).pack(side='left', padx=10)
        ttk.Button(bf, text="❌ 删除", command=self.delete_crop).pack(side='right', padx=10)
        ttk.Button(bf, text="✏️ 编辑", command=self.open_edit_win).pack(side='right')
        ttk.Button(bf, text="➕ 新作物", command=lambda: CropEditor(self)).pack(side='right', padx=10)
        ttk.Button(bf, text="🐛 Debug", command=self.open_debug_window).pack(side='right', padx=20)
        self.refresh_list(initial=True)

    def on_ch_double_click(self, event):
        c_idx = self.sheet.identify_column(event)
        if c_idx is not None:
            col_id = self.data["display_columns"][c_idx]
            self.current_sort_reverse = not self.current_sort_reverse if self.current_sort_col == col_id else True
            self.current_sort_col = col_id
            
            valid_crops, empty_crops = [], []
            for c in self.data["crops"]:
                P, _ = calc_profits(c, self.data["settings"], self.data["fertilizers"])
                val = c.get(col_id, None)
                if col_id == "type": val = "果树" if c.get("is_tree") else "普通"
                elif col_id == "verified": val = "☑" if c.get('verified') else "☐"
                elif col_id == "process_status": val = f"{'●' if c.get('primary_type', '无') != '无' else '○'}{c.get('primary_type', '无')} {'●' if c.get('can_jam') else '○'}酱 {'●' if c.get('can_pickle') else '○'}菜"
                elif col_id == "best_profit": val = max([v for v in P.values() if v is not None]) if [v for v in P.values() if v is not None] else None
                elif col_id == "best_strategy": valid_p = {k: v for k, v in P.items() if v is not None}; val = max(valid_p, key=valid_p.get) if valid_p else "无"
                elif col_id in P: val = P[col_id]

                if val in (None, "", "-", "无") or (isinstance(val, (int, float)) and val == 0) or str(val) == "0.00": empty_crops.append(c)
                # ⚡ 核心修复：在 replace 和 isdigit 之前，加入 lstrip('-') 忽略负号干扰
                else: valid_crops.append((c, float(val) if str(val).lstrip('-').replace('.', '', 1).isdigit() else str(val)))
            
            valid_crops.sort(key=lambda x: (0, x[1]) if isinstance(x[1], (int, float)) else (1, x[1]), reverse=self.current_sort_reverse)
            self.data["crops"] = [x[0] for x in valid_crops] + empty_crops
            
            self.refresh_list(keep_widths=True); self.refresh_db()
            try: self.sheet.select_column(c_idx, redraw=True)
            except Exception: pass

    def exec_sync_drag(self, event=None):
        if not isinstance(event, dict) or 'moved' not in event: 
            return
            
        try:
            # 1. 提取列移动映射字典 (例如: {4: 8, 5: 9, 6: 10})
            move_dict = event['moved'].get('columns', {}).get('data', {})
            if not move_dict: 
                return
            
            # 2. 获取所有被移动列的原始索引（排序以确保顺序提取）
            old_idxs = sorted(move_dict.keys())
            
            # 3. 找出这些索引对应的列 ID
            disp = self.data["display_columns"]
            moved_items = [disp[i] for i in old_idxs]
            
            # 4. 确定这组列块在“最终状态”下的起始插入位置
            # tksheet 的映射字典中，第一个 key 对应的值就是块的起始落点
            target_insert_idx = move_dict[old_idxs[0]]

            # 5. 【关键逻辑】原地重建数组
            # 先过滤掉所有处于移动状态的旧列
            remaining_items = [item for i, item in enumerate(disp) if i not in move_dict]
            
            # 再将整个 moved_items 块插入到计算出的目标位置
            # 注意：这里的 target_insert_idx 是 tksheet 告知的绝对最终位置
            remaining_items[target_insert_idx:target_insert_idx] = moved_items
            
            # 6. 更新并保存
            self.data["display_columns"] = remaining_items
            self.save_data()
            
            # 延迟刷新以确保 UI 动画完成
            self.after(50, lambda: self.refresh_list(keep_widths=True))
            
            self.debug_print(f"[DEBUG] 多列拖拽成功：移动了 {len(moved_items)} 列到索引 {target_insert_idx}")
            
        except Exception as e:
            self.debug_print(f"[DEBUG] ❌ 多列拖拽逻辑故障: {e}")
    

    def toggle_verified(self, r):
        name = self.sheet.get_cell_data(r, self.data["display_columns"].index("name"))
        c = next((x for x in self.data["crops"] if x["name"] == name), None)
        if c: c['verified'] = not c.get('verified', False); self.save_data(); self.refresh_list(keep_widths=True)

    def open_edit_win(self):
        sel = self.sheet.get_currently_selected()
        if sel: CropEditor(self, self.sheet.get_cell_data(sel[0], self.data["display_columns"].index("name")))

    def delete_crop(self):
        sel = self.sheet.get_currently_selected()
        if sel:
            n = self.sheet.get_cell_data(sel[0], self.data["display_columns"].index("name"))
            if messagebox.askyesno("确认", f"删除 {n}?"):
                self.data["crops"] = [x for x in self.data["crops"] if x.get("name") != n]
                self.save_data(); self.refresh_all()

    def refresh_all(self): 
        self.refresh_list(keep_widths=True)
        self.refresh_db()
        self.refresh_fert_list() # 如果你有这个函数的话
        # ⚡ 加上这两句，保证对比页面的选项始终是最新的
        if hasattr(self, 'refresh_cmp_ferts'):
            self.refresh_cmp_ferts()
            self.refresh_cmp_crops()

    def build_db_tab(self):
        self.db_sheet = Sheet(self.tab_db, align="center", header_align="center", theme="light blue", font=("微软雅黑", 10, "normal"), header_font=("微软雅黑", 10, "bold"), row_height=28, header_height=32)
        self.db_sheet.pack(fill="both", expand=True, padx=8, pady=8); self.db_sheet.hide("row_index")
        self.db_sheet.enable_bindings(("single_select", "drag_select", "row_select", "arrowkeys", "copy"))
        self.db_sheet.MT.bind("<Button-3>", self.on_db_right_click, add="+")
        bf = ttk.Frame(self.tab_db); bf.pack(side='bottom', fill='x', pady=8, padx=8)
        ttk.Button(bf, text="⬆️ 上移该行", command=self.move_db_up).pack(side='left', padx=5)
        ttk.Button(bf, text="⬇️ 下移该行", command=self.move_db_down).pack(side='left', padx=5)
        self.refresh_db()

    def on_db_right_click(self, event):
        r = self.db_sheet.identify_row(event)
        if r is not None:
            self.db_sheet.set_currently_selected(r, 0)
            m = tk.Menu(self, tearoff=0, font=("微软雅黑", 9)); m.add_command(label="✏️ 编辑作物属性", command=self.open_edit_win_db)
            m.post(event.x_root, event.y_root)

    def open_edit_win_db(self):
        sel = self.db_sheet.get_currently_selected()
        if sel: CropEditor(self, self.db_sheet.get_cell_data(sel[0], self.db_sheet.headers().index("名称") if "名称" in self.db_sheet.headers() else 0))

    def refresh_db(self):
        cols = list(config.DB_KEY_MAP.values()); self.db_sheet.headers(cols)
        db_crops = sorted(self.data["crops"], key=lambda x: x.get("_db_index", 0))
        rows = [[str(c.get(k, "")) for k in config.DB_KEY_MAP] for c in db_crops]
        self.db_sheet.set_sheet_data(rows, reset_col_positions=True); self.db_sheet.dehighlight_all()
        for i in range(len(rows)):
            if i % 2 == 1: self.db_sheet.highlight_rows(rows=[i], bg="#f4f7fb")
        try: self.db_sheet.align("center"); self.db_sheet.header_align("center")
        except: pass
        self.db_sheet.refresh()

    def sync_sort_to_db(self):
        if messagebox.askyesno("覆盖确认", "确定将当前【报表页】的显示顺序，永久覆盖到【数据库】物理顺序中吗？"):
            for i, c in enumerate(self.data["crops"]): c["_db_index"] = i
            self.save_data(); self.refresh_db(); messagebox.showinfo("成功", "排序已成功永久保存到数据库！")

    def move_db_up(self):
        sel = self.db_sheet.get_currently_selected()
        if not sel or sel[0] == 0: return
        r = sel[0]; db_crops = sorted(self.data["crops"], key=lambda x: x.get("_db_index", 0))
        db_crops[r]["_db_index"], db_crops[r-1]["_db_index"] = db_crops[r-1]["_db_index"], db_crops[r]["_db_index"]
        self.save_data(); self.refresh_db(); self.db_sheet.set_currently_selected(r-1, 0)

    def move_db_down(self):
        sel = self.db_sheet.get_currently_selected()
        db_crops = sorted(self.data["crops"], key=lambda x: x.get("_db_index", 0))
        if not sel or sel[0] >= len(db_crops) - 1: return
        r = sel[0]; db_crops[r]["_db_index"], db_crops[r+1]["_db_index"] = db_crops[r+1]["_db_index"], db_crops[r]["_db_index"]
        self.save_data(); self.refresh_db(); self.db_sheet.set_currently_selected(r+1, 0)

    def build_settings_tab(self):
        f = tk.Frame(self.tab_settings, bg="#f5f5f7"); f.pack(fill='both', padx=40, pady=40)
        self.s_ents = {}
        for i, (k, l) in enumerate(config.SETTINGS_LANG_MAP.items()):
            tk.Label(f, text=l, bg="#f5f5f7", font=("微软雅黑", 9)).grid(row=i, column=0, sticky='e', pady=6)
            e = ttk.Entry(f, width=28); e.grid(row=i, column=1, padx=12, pady=6)
            e.insert(0, str(self.data["settings"].get(k,""))); self.s_ents[k] = e
        ttk.Button(f, text=" 💾 保存算法设置 ", command=self.save_settings).grid(row=20, column=1, pady=30, sticky='w')
        
    def save_settings(self):
        for k,e in self.s_ents.items(): self.data["settings"][k]=float(e.get())
        self.save_data(); self.refresh_all()

    def toggle_column_group(self, pc, ex):
        disp = list(self.data["display_columns"])
        kids = config.COLUMN_GROUPS.get(pc, [])
        
        if ex: # 展开
            if pc in disp:
                idx = disp.index(pc)
                # 直接按 config 里设定的原生顺序插入，不再做复杂的全表状态同步重排
                for i, k in enumerate(kids):
                    if k not in disp: 
                        disp.insert(idx + 1 + i, k)
        else: # 收起
            for k in kids:
                if k in disp: 
                    disp.remove(k)
                    
        self.data["display_columns"] = disp
        self.refresh_list(keep_widths=True)
        self.save_data()
        
        # 去掉了原先在这里读取 fert_widths 并强行覆盖界面宽度的逻辑
        self.sheet.refresh()

    # ================= 🧪 第四页：肥料实验室 =================

    def build_fert_tab(self):
        # 创建可编辑的表格
        self.fert_sheet = Sheet(self.tab_fert, 
                                align="center", header_align="center",
                                valign="center", header_valign="center",
                                theme="light blue",
                                font=("微软雅黑", 10, "normal"),
                                header_font=("微软雅黑", 10, "bold"),
                                row_height=38, header_height=42)
        
        self.fert_sheet.set_options(table_font_vertical_alignment="center", header_font_vertical_alignment="center")
        self.fert_sheet.pack(fill="both", expand=True, padx=8, pady=8)
        
        # ⚡ 启用双击编辑 (edit_cell) 和常规选择
        self.fert_sheet.enable_bindings((
            "single_select", "row_select", "column_width_resize",
            "arrowkeys", "copy", "rc_select", "edit_cell" 
        ))
        
        # 底部控制面板
        bf = ttk.Frame(self.tab_fert); bf.pack(side='bottom', fill='x', pady=8, padx=8)
        
        ttk.Label(bf, text="💡 提示: 双击表格直接编辑。类型仅限填 speed(催熟) 或 yield(增产)。", 
                  font=("微软雅黑", 9), foreground="#666666").pack(side='left')
        
        ttk.Button(bf, text="💾 保存并更新计算引擎", command=self.save_fert_changes).pack(side='right', padx=10)
        ttk.Button(bf, text="❌ 删除选中行", command=self.delete_fert).pack(side='right')
        ttk.Button(bf, text="➕ 研发新肥料", command=self.add_fert).pack(side='right', padx=10)
        
        self.refresh_fert_list()

    # ================= ⚖️ 第五页：施肥效益对比 =================

    def build_compare_tab(self):
        # 顶部控制栏
        ctrl_frame = ttk.Frame(self.tab_compare)
        ctrl_frame.pack(fill='x', padx=10, pady=10)

        ttk.Label(ctrl_frame, text="1. 选择要评估的肥料:", font=("微软雅黑", 10, "bold")).pack(side='left', padx=(0, 5))
        self.cmp_fert_combo = ttk.Combobox(ctrl_frame, state="readonly", width=18, font=("微软雅黑", 10))
        self.cmp_fert_combo.pack(side='left', padx=5)
        
        ttk.Button(ctrl_frame, text="🔄 刷新肥料列表", command=self.refresh_cmp_ferts).pack(side='left', padx=5)
        ttk.Button(ctrl_frame, text="🚀 开始对比计算", command=self.run_comparison).pack(side='left', padx=30)

        # 主体分栏：左侧选作物，右侧看结果
        body_frame = ttk.Frame(self.tab_compare)
        body_frame.pack(fill='both', expand=True, padx=10, pady=5)

        # 左侧：作物选择区
        left_frame = ttk.LabelFrame(body_frame, text=" 2. 选择参选作物 (支持拖拽多选) ")
        left_frame.pack(side='left', fill='y', padx=(0, 10))

        scroll_y = ttk.Scrollbar(left_frame)
        scroll_y.pack(side='right', fill='y')

        self.cmp_crop_listbox = tk.Listbox(left_frame, selectmode=tk.EXTENDED, yscrollcommand=scroll_y.set, width=22, font=("微软雅黑", 11))
        self.cmp_crop_listbox.pack(side='top', fill='both', expand=True, padx=8, pady=8)
        scroll_y.config(command=self.cmp_crop_listbox.yview)

        btn_frame = ttk.Frame(left_frame)
        btn_frame.pack(fill='x', padx=8, pady=(0, 8))
        ttk.Button(btn_frame, text="全选", command=lambda: self.cmp_crop_listbox.selection_set(0, tk.END)).pack(side='left', expand=True, fill='x', padx=2)
        ttk.Button(btn_frame, text="反选", command=self.toggle_cmp_crops).pack(side='left', expand=True, fill='x', padx=2)

        # 右侧：分析结果表格
        right_frame = ttk.LabelFrame(body_frame, text=" 3. 效益分析结果 (已自动按【时薪增量】降序排列) ")
        right_frame.pack(side='left', fill='both', expand=True)

        self.cmp_sheet = Sheet(right_frame, align="center", header_align="center", valign="center", header_valign="center",
                               theme="light blue", font=("微软雅黑", 10, "normal"), header_font=("微软雅黑", 10, "bold"),
                               row_height=38, header_height=42)
        self.cmp_sheet.set_options(table_font_vertical_alignment="center", header_font_vertical_alignment="center")
        self.cmp_sheet.pack(fill='both', expand=True, padx=8, pady=8)
        self.cmp_sheet.enable_bindings(("single_select", "row_select", "column_width_resize", "arrowkeys", "copy"))

        # 初始化数据
        self.refresh_cmp_ferts()
        self.refresh_cmp_crops()

    def refresh_cmp_ferts(self):
        ferts = [f["name"] for f in self.data.get("fertilizers", [])]
        self.cmp_fert_combo['values'] = ferts
        if ferts: self.cmp_fert_combo.current(0)

    def refresh_cmp_crops(self):
        self.cmp_crop_listbox.delete(0, tk.END)
        for c in self.data.get("crops", []):
            self.cmp_crop_listbox.insert(tk.END, c.get("name", "未知作物"))

    def toggle_cmp_crops(self):
        for i in range(self.cmp_crop_listbox.size()):
            if self.cmp_crop_listbox.selection_includes(i): self.cmp_crop_listbox.selection_clear(i)
            else: self.cmp_crop_listbox.selection_set(i)

    def run_comparison(self):
        target_fert = self.cmp_fert_combo.get()
        if not target_fert: return messagebox.showwarning("提示", "请先选择一种肥料！")
        
        selected_indices = self.cmp_crop_listbox.curselection()
        if not selected_indices: return messagebox.showwarning("提示", "请至少在左侧选择一种作物！")

        results = []
        for idx in selected_indices:
            crop_name = self.cmp_crop_listbox.get(idx)
            c = next((x for x in self.data["crops"] if x.get("name") == crop_name), None)
            if not c: continue

            # 调用引擎：同时计算该作物的所有可能情况
            P, _ = calc_profits(c, self.data["settings"], self.data.get("fertilizers", []))

            # 1. 找出【无肥料】状态下的最强策略和时薪
            no_fert_keys = {k: v for k, v in P.items() if "无肥料" in k and v is not None}
            best_no_fert_k = max(no_fert_keys, key=no_fert_keys.get) if no_fert_keys else "无"
            best_no_fert_v = no_fert_keys.get(best_no_fert_k, 0)

            # 2. 找出施加【目标肥料】状态下的最强策略和时薪
            tgt_fert_keys = {k: v for k, v in P.items() if target_fert in k and v is not None}
            best_tgt_fert_k = max(tgt_fert_keys, key=tgt_fert_keys.get) if tgt_fert_keys else "无"
            best_tgt_fert_v = tgt_fert_keys.get(best_tgt_fert_k, 0)

            # 3. 计算边际时薪增量
            diff = best_tgt_fert_v - best_no_fert_v

            results.append({
                "name": crop_name,
                "base_strat": best_no_fert_k.replace("_无肥料", ""),
                "base_val": best_no_fert_v,
                "fert_strat": best_tgt_fert_k.replace(f"_{target_fert}", ""),
                "fert_val": best_tgt_fert_v,
                "diff": diff
            })

        # 按时薪增量从高到低排序 (核心逻辑)
        results.sort(key=lambda x: x["diff"], reverse=True)

        # 渲染表格
        headers = ["排名", "作物名称", "原最优流派", "原最高时薪", f"施肥后最优流派", "施肥后时薪", "🔥 绝对时薪增量"]
        self.cmp_sheet.headers(headers)

        sheet_data = []
        for i, r in enumerate(results):
            rank = f"Top {i+1}" if i < 3 else str(i+1)
            diff_str = f"+{r['diff']:.2f}" if r['diff'] > 0 else f"{r['diff']:.2f}"
            sheet_data.append([
                rank, r["name"], r["base_strat"], f"{r['base_val']:.2f}", 
                r["fert_strat"], f"{r['fert_val']:.2f}", diff_str
            ])

        self.cmp_sheet.set_sheet_data(sheet_data)
        
        # 美化列宽
        widths = [60, 120, 120, 120, 140, 120, 160]
        for i, w in enumerate(widths): self.cmp_sheet.column_width(i, w)

        # 颜色高亮：前三名且赚钱的标绿，亏钱的标红警示
        self.cmp_sheet.dehighlight_all()
        for i in range(len(results)):
            if results[i]["diff"] > 0:
                if i < 3: self.cmp_sheet.highlight_cells(row=i, column=6, bg="#e8f5e9", fg="#2e7d32") # 绿色 (大赚)
                else: self.cmp_sheet.highlight_cells(row=i, column=6, fg="#2e7d32")
            elif results[i]["diff"] < 0:
                self.cmp_sheet.highlight_cells(row=i, column=6, bg="#ffebee", fg="#c62828") # 红色 (亏本)

        self.cmp_sheet.redraw()


    def refresh_fert_list(self):
        """刷新肥料实验室的表格数据"""
        self.fert_sheet.headers(["肥料名称", "类型 (speed/yield)", "效果数值 (减时/倍率)", "每次消耗成本"])
        data = []
        for f in self.data["fertilizers"]:
            data.append([f.get("name", ""), f.get("type", "speed"), f.get("effect", 0.0), f.get("cost", 0.0)])
        self.fert_sheet.set_sheet_data(data)
        self.fert_sheet.column_width(0, 150)
        self.fert_sheet.column_width(1, 150)
        self.fert_sheet.column_width(2, 180)
        self.fert_sheet.column_width(3, 150)
        self.fert_sheet.redraw()

    def add_fert(self):
        """添加一行新肥料"""
        self.data["fertilizers"].append({"name": "新肥料", "type": "speed", "effect": 1.0, "cost": 10.0})
        self.refresh_fert_list()
        self.fert_sheet.see(len(self.data["fertilizers"]) - 1, 0) # 滚动到最底部

    def delete_fert(self):
        """删除选中的肥料"""
        sel = self.fert_sheet.get_currently_selected()
        if sel:
            r = sel[0]
            fert_name = self.data["fertilizers"][r]["name"]
            if messagebox.askyesno("危险操作", f"确定要删除【{fert_name}】吗？\n所有与其相关的收益计算列都将消失！"):
                del self.data["fertilizers"][r]
                self.refresh_fert_list()

    def save_fert_changes(self):
        """提取表格里的最新数据，保存并重构整个系统"""
        try:
            raw_data = self.fert_sheet.get_sheet_data()
            new_ferts = []
            
            for row in raw_data:
                name = str(row[0]).strip()
                ftype = str(row[1]).strip().lower()
                if ftype not in ["speed", "yield"]:
                    messagebox.showerror("格式错误", f"【{name}】的类型错误！\n只能填写 'speed' 或 'yield'。")
                    return
                effect = float(row[2])
                cost = float(row[3])
                new_ferts.append({"name": name, "type": ftype, "effect": effect, "cost": cost})
            
            # 1. 保存到数据总线
            self.data["fertilizers"] = new_ferts
            self.save_data()
            
            # 2. 核心：重新动态生成列配置字典
            self.rebuild_dynamic_columns()
            
            # 3. 清理已经不存在的列 (防止删除了肥料，但报表里还留着死掉的列ID)
            valid_cols = list(config.ALL_COLS.keys()) + list(config.DB_KEY_MAP.keys())
            self.data["display_columns"] = [c for c in self.data["display_columns"] if c in valid_cols]
            
            # 4. 强制刷新收益报表 (让新的列和计算结果立即显示)
            self.refresh_list(keep_widths=False)
            
            messagebox.showinfo("保存成功", "肥料配方已更新！\n收益分析报表中的算法公式已经全部自动重写。")
        except ValueError:
            messagebox.showerror("格式错误", "效果数值和成本必须是纯数字！")
        except Exception as e:
            messagebox.showerror("系统错误", f"保存失败: {e}")

if __name__ == "__main__":
    app = FarmManagerApp()
    app.mainloop()