import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from tksheet import Sheet
import config
from logic import calc_profits
from ui_popups import CropEditor, ColumnManager, FormulaViewer, set_popup_geo

# 将这个函数直接放在 ui_tabs.py 的顶部（类定义的外面）
def analyze_expansion_opportunity(crop_data, fert_name, current_strategy_hourly, current_strategy_key, P_dict, F_dict, fertilizers_list):
    """
    统一复用的核心算法：计算“等价扩种时薪”与“扩种单次纯收益”
    自动判断：如果支持一级加工且有收益，优先用一级加工计算扩种，否则用直售。
    """
    def get_time(formula_dict):
        try:
            safe_expr = formula_dict['val_d'].replace('×', '*').replace('÷', '/')
            return max(float(eval(safe_expr)), 0.1)
        except:
            return 1.0

    # 🌟 智能选择扩种基准：优先找一级加工
    base_exp_key = "一级加工_无肥料"
    if base_exp_key not in P_dict or P_dict[base_exp_key] is None or P_dict[base_exp_key] <= 0:
        base_exp_key = "直接出售_无肥料"
        
    base_exp_hourly = P_dict.get(base_exp_key, 0)
    base_exp_time = get_time(F_dict[base_exp_key]) if base_exp_key in F_dict else 1.0
    base_exp_single_net = base_exp_hourly * base_exp_time # 基准单次纯收益

    # 计算当前所选方案的单次纯收益
    current_time = get_time(F_dict[current_strategy_key]) if current_strategy_key in F_dict else 1.0
    current_single_net = current_strategy_hourly * current_time

    seed_price = float(crop_data.get("seed_price", 0) or 0)
    fert_cost = 0
    if fert_name != "无肥料":
        fert_obj = next((f for f in fertilizers_list if f["name"] == fert_name), None)
        if fert_obj: fert_cost = float(fert_obj.get("cost", 0))

    alt_hourly = 0
    alt_diff = 0
    alt_single_net = 0
    extra_seeds = 0  # 👈 新加这行

    if seed_price > 0 and fert_cost > 0:
        extra_seeds = fert_cost / seed_price
        alt_hourly = base_exp_hourly * (1 + extra_seeds)
        alt_diff = alt_hourly - current_strategy_hourly # 扩种时薪减去当前施肥方案时薪
        alt_single_net = base_exp_single_net * (1 + extra_seeds) # 扩种后的单次总利润

    return alt_hourly, alt_diff, current_single_net, alt_single_net, base_exp_key, extra_seeds


class ReportTab:
    def __init__(self, parent, app, dm):
        self.app = app
        self.dm = dm
        self.current_sort_col = None
        self.current_sort_reverse = False
        
        self.sheet = Sheet(parent, align="center", header_align="center", theme="light blue", 
                           font=("微软雅黑", 10, "normal"), header_font=("微软雅黑", 10, "bold"), 
                           row_height=28, header_height=52)
        self.sheet.pack(fill="both", expand=True)
        self.sheet.hide("row_index")
        self.sheet.enable_bindings("move_columns", "column_width_resize", "drag_select", "single_select", 
                                   "row_select", "column_select", "arrowkeys", "copy", "rc_select")
        self.sheet.disable_bindings("zoom")

        self.sheet.CH.bind("<Double-Button-1>", self.on_ch_double_click, add="+")
        self.sheet.CH.bind("<Button-3>", self.safe_right_click, add="+")
        self.sheet.MT.bind("<Button-3>", self.safe_right_click, add="+")
        self.sheet.extra_bindings("move_columns", self.exec_sync_drag)
        self.sheet.extra_bindings("column_width_resize", self.exec_sync_width)

        bf = ttk.Frame(parent); bf.pack(side='bottom', fill='x', pady=8)
        ttk.Button(bf, text="🔄 刷新数据", command=self.app.reload_from_db).pack(side='left', padx=10)
        ttk.Button(bf, text="💾 保存排序到数据库", command=self.sync_sort_to_db).pack(side='left')
        ttk.Button(bf, text="⚙️ 自定义列", command=lambda: ColumnManager(self.app)).pack(side='left', padx=10)
        ttk.Button(bf, text="❌ 删除", command=self.delete_crop).pack(side='right', padx=10)
        ttk.Button(bf, text="✏️ 编辑", command=self.open_edit_win).pack(side='right')
        ttk.Button(bf, text="➕ 新作物", command=lambda: CropEditor(self.app)).pack(side='right', padx=10)
        ttk.Button(bf, text="🐛 Debug", command=self.app.open_debug_window).pack(side='right', padx=20)
        
        self.refresh_list(initial=True)

    def get_col_display_name(self, col_id):
        custom_map = self.dm.data.get("custom_column_names", {})
        if col_id in custom_map: return custom_map[col_id]
        if col_id == "verified": return "数据\n核对"
        if col_id == "name": return "作物名称"
        base = config.ALL_COLS.get(col_id, col_id).replace("↳ ", "").strip()
        for p, kids in config.COLUMN_GROUPS.items():
            if col_id in kids:
                parent_raw = config.ALL_COLS.get(p, p).strip()
                parent_clean = parent_raw.split('(')[0].split('（')[0].strip()
                clean_base = base.lstrip(':').strip()
                return f"{parent_clean}\n{clean_base}"
        return base

    def refresh_list(self, keep_widths=False, initial=False):
        cols = self.dm.data["display_columns"]
        self.sheet.headers([self.get_col_display_name(c) for c in cols])
        rows, red_coords, bold_coords = [], [], []
        
        for r_idx, c in enumerate(self.dm.data["crops"]):
            try:
                P, _ = calc_profits(c, self.dm.data["settings"], self.dm.data["fertilizers"])
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
                            if k in cols and v < 0: red_coords.append((r_idx, cols.index(k)))
                    if best_v > 0:
                        if "best_profit" in cols: bold_coords.append((r_idx, cols.index("best_profit")))
                        if best_k in cols: bold_coords.append((r_idx, cols.index(best_k)))
                else: rm["best_profit"], rm["best_strategy"] = "0.00", "无"
                rows.append([rm.get(cid, "-") for cid in cols])
            except: continue

        self.sheet.set_sheet_data(rows, reset_col_positions=True)
        self.sheet.align(align="center", redraw=False)
        self.sheet.header_align(align="center", redraw=False)
        self.sheet.dehighlight_all()
        for i in range(len(rows)):
            if i % 2 == 1: self.sheet.highlight_rows(rows=[i], bg="#f4f7fb")

        group_colors, color_idx = ["#eef5ff", "#fff8ed", "#f0fff0", "#fff0f5"], 0
        for p, kids in config.COLUMN_GROUPS.items():
            if p in cols:
                bg_color = group_colors[color_idx % len(group_colors)]; color_idx += 1
                for k in kids:
                    if k in cols: self.sheet.highlight_columns(columns=[cols.index(k)], bg=bg_color)

        for r, c in red_coords: self.sheet.highlight_cells(row=r, column=c, fg="#d93025", bg="#fef7f7")
        for r, c in bold_coords:
            self.sheet.highlight_cells(row=r, column=c, fg="#1a73e8", bg="#f1f8fe")
            self.sheet.MT.cell_options[(r, c)]['font'] = ("微软雅黑", 10, "bold")
            
        if self.dm.runtime_col_widths:
            for i, col_id in enumerate(cols):
                w = self.dm.runtime_col_widths.get(col_id, self.dm.runtime_col_widths.get(str(i), 100))
                self.sheet.column_width(i, width=int(w))
        self.sheet.refresh()

    def safe_right_click(self, event):
        c = self.sheet.identify_column(event); r = self.sheet.identify_row(event) if event.widget != self.sheet.CH else None
        if c is None: return
        col_id = self.dm.data["display_columns"][c]
        m = tk.Menu(self.app, tearoff=0, font=("微软雅黑", 9))
        
        if event.widget == self.sheet.CH:
            m.add_command(label="✏️ 修改列显示名称", command=lambda: self.rename_column(col_id))
            if col_id in config.COLUMN_GROUPS:
                is_ex = any(k in self.dm.data["display_columns"] for k in config.COLUMN_GROUPS[col_id])
                m.add_command(label="➖ 收起肥料详情" if is_ex else "➕ 展开肥料详情", command=lambda: self.toggle_column_group(col_id, not is_ex))
        else:
            if r is not None:
                self.sheet.set_currently_selected(r, c)
                if col_id == "verified": m.add_command(label="✅ 切换核对状态", command=lambda: self.toggle_verified(r))
                m.add_command(label="✏️ 编辑作物属性", command=self.open_edit_win)
                if col_id not in list(config.DB_KEY_MAP.keys()) + ["type", "process_status", "verified", "name"] or col_id == "best_profit":
                    n = self.sheet.get_cell_data(r, self.dm.data["display_columns"].index("name")); strat = col_id
                    if col_id in ["best_profit", "best_strategy"]:
                        P, _ = calc_profits(next((x for x in self.dm.data["crops"] if x["name"] == n), None), self.dm.data["settings"], self.dm.data.get("fertilizers", []))
                        strat = max({k:v for k,v in P.items() if v is not None}, key=P.get) if P else None
                    if strat:
                        m.add_separator(); m.add_command(label="📊 全方案分析对比", command=lambda: self.show_details_popup(n))
                        m.add_command(label=f"🔢 查看 [{config.ALL_COLS.get(strat, strat).replace('↳ ', '')}] 计算公式", command=lambda: FormulaViewer.show(self.app, n, strat, self.app))
        m.post(event.x_root, event.y_root)

    def rename_column(self, col_id):
        old_name = self.get_col_display_name(col_id).replace("\n", "\\n")
        new_name = simpledialog.askstring("重命名列", f"请输入列 [{col_id}] 的新显示名称:\n(输入 \\n 代表手动换行，留空恢复默认)", initialvalue=old_name)
        if new_name is not None:
            if new_name.strip() == "": self.dm.data["custom_column_names"].pop(col_id, None)
            else: self.dm.data["custom_column_names"][col_id] = new_name.replace("\\n", "\n").strip()
            self.dm.save_data(self.sheet); self.refresh_list(keep_widths=True)

    def toggle_column_group(self, pc, ex):
        disp = list(self.dm.data["display_columns"])
        kids = config.COLUMN_GROUPS.get(pc, [])
        if ex:
            if pc in disp:
                idx = disp.index(pc)
                for i, k in enumerate(kids):
                    if k not in disp: disp.insert(idx + 1 + i, k)
        else:
            for k in kids:
                if k in disp: disp.remove(k)
        self.dm.data["display_columns"] = disp
        self.refresh_list(keep_widths=True)
        self.dm.save_data(self.sheet)

    def exec_sync_width(self, event):
        try:
            if isinstance(event, dict) and 'resized' in event and event['resized'].get('columns', {}):
                c_idx = list(event['resized']['columns'].keys())[0]
                new_w = max(40, event['resized']['columns'][c_idx].get('new_size', 40))
                self.sheet.column_width(c_idx, width=new_w)
                col_id = self.dm.data["display_columns"][c_idx]
                self.dm.runtime_col_widths[col_id] = new_w
                self.dm.save_data(self.sheet)
        except Exception as e: self.dm.debug_print(f"[DEBUG] ❌ 宽度处理报错: {e}")

    def exec_sync_drag(self, event=None):
        if not isinstance(event, dict) or 'moved' not in event: return
        try:
            move_dict = event['moved'].get('columns', {}).get('data', {})
            if not move_dict: return
            old_idxs = sorted(move_dict.keys()); disp = self.dm.data["display_columns"]
            moved_items = [disp[i] for i in old_idxs]
            target_insert_idx = move_dict[old_idxs[0]]
            remaining_items = [item for i, item in enumerate(disp) if i not in move_dict]
            remaining_items[target_insert_idx:target_insert_idx] = moved_items
            self.dm.data["display_columns"] = remaining_items
            self.dm.save_data(self.sheet)
            self.app.after(50, lambda: self.refresh_list(keep_widths=True))
        except Exception as e: self.dm.debug_print(f"[DEBUG] ❌ 多列拖拽故障: {e}")

    def on_ch_double_click(self, event):
        c_idx = self.sheet.identify_column(event)
        if c_idx is not None:
            col_id = self.dm.data["display_columns"][c_idx]
            self.current_sort_reverse = not self.current_sort_reverse if self.current_sort_col == col_id else True
            self.current_sort_col = col_id
            valid_crops, empty_crops = [], []
            for c in self.dm.data["crops"]:
                P, _ = calc_profits(c, self.dm.data["settings"], self.dm.data["fertilizers"])
                val = c.get(col_id, None)
                if col_id == "type": val = "果树" if c.get("is_tree") else "普通"
                elif col_id == "verified": val = "☑" if c.get('verified') else "☐"
                elif col_id == "process_status": val = f"{'●' if c.get('primary_type', '无') != '无' else '○'}{c.get('primary_type', '无')} {'●' if c.get('can_jam') else '○'}酱 {'●' if c.get('can_pickle') else '○'}菜"
                elif col_id == "best_profit": val = max([v for v in P.values() if v is not None]) if [v for v in P.values() if v is not None] else None
                elif col_id == "best_strategy": valid_p = {k: v for k, v in P.items() if v is not None}; val = max(valid_p, key=valid_p.get) if valid_p else "无"
                elif col_id in P: val = P[col_id]

                if val in (None, "", "-", "无") or (isinstance(val, (int, float)) and val == 0) or str(val) == "0.00": empty_crops.append(c)
                else: valid_crops.append((c, float(val) if str(val).lstrip('-').replace('.', '', 1).isdigit() else str(val)))
            valid_crops.sort(key=lambda x: (0, x[1]) if isinstance(x[1], (int, float)) else (1, x[1]), reverse=self.current_sort_reverse)
            self.dm.data["crops"] = [x[0] for x in valid_crops] + empty_crops
            self.refresh_list(keep_widths=True); self.app.db_tab.refresh_db()
            try: self.sheet.select_column(c_idx, redraw=True)
            except Exception: pass

    def toggle_verified(self, r):
        name = self.sheet.get_cell_data(r, self.dm.data["display_columns"].index("name"))
        c = next((x for x in self.dm.data["crops"] if x["name"] == name), None)
        if c: c['verified'] = not c.get('verified', False); self.dm.save_data(self.sheet); self.refresh_list(keep_widths=True)

    def open_edit_win(self):
        sel = self.sheet.get_currently_selected()
        if sel: CropEditor(self.app, self.sheet.get_cell_data(sel[0], self.dm.data["display_columns"].index("name")))

    def delete_crop(self):
        sel = self.sheet.get_currently_selected()
        if sel:
            n = self.sheet.get_cell_data(sel[0], self.dm.data["display_columns"].index("name"))
            if messagebox.askyesno("确认", f"删除 {n}?"):
                self.dm.data["crops"] = [x for x in self.dm.data["crops"] if x.get("name") != n]
                self.dm.save_data(self.sheet); self.app.refresh_all()

    def sync_sort_to_db(self):
        if messagebox.askyesno("覆盖确认", "确定将当前【报表页】的显示顺序，永久覆盖到【数据库】物理顺序中吗？"):
            for i, c in enumerate(self.dm.data["crops"]): c["_db_index"] = i
            self.dm.save_data(self.sheet); self.app.db_tab.refresh_db(); messagebox.showinfo("成功", "排序已成功永久保存到数据库！")

    def show_details(self, c):
        w = tk.Toplevel(self.app); w.title(f"收益分析: {c['name']}")
        set_popup_geo(w, 1080, 780); w.configure(bg="white")
        
        seed_price = float(c.get("seed_price", 0) or 0)
        
        header_frame = tk.Frame(w, bg="white")
        header_frame.pack(pady=15)
        tk.Label(header_frame, text=f"作物: {c['name']} 方案全景分析", font=("微软雅黑", 14, "bold"), bg="white").pack()
        tk.Label(header_frame, text=f"种子价格: {seed_price} 金币", font=("微软雅黑", 10), fg="#888", bg="white").pack()

        con = tk.Frame(w, bg="white"); con.pack(fill='both', expand=True, padx=20, pady=10)
        
        # 🌟 更新列名，加入单次收益对比
        cols = ("s", "p", "np", "alt", "altd", "alt_net", "plots")
        tv = ttk.Treeview(con, columns=cols, show="headings", height=16)
        tv.pack(side='left', fill='both', expand=True)
        sc = ttk.Scrollbar(con, command=tv.yview); sc.pack(side='right', fill='y'); tv.config(yscrollcommand=sc.set)
        
        tv.heading("s", text="策略组合名称")
        tv.heading("p", text="预计时薪")
        tv.heading("np", text="💰当前单次收益")
        tv.heading("alt", text="🌱扩种等价时薪")
        tv.heading("altd", text="📈扩种时薪增量")
        tv.heading("alt_net", text="🌾扩种单次收益")
        tv.heading("plots", text="🔲 扩种地块数")

        tv.column("s", width=200, anchor="center"); tv.column("p", width=90, anchor="center")
        tv.column("np", width=120, anchor="center"); tv.column("alt", width=130, anchor="center")
        tv.column("altd", width=130, anchor="center"); tv.column("alt_net", width=130, anchor="center")
        tv.column("plots", width=100, anchor="center")
        P, F = calc_profits(c, self.dm.data["settings"], self.dm.data.get("fertilizers", []))
        
        data_list = []
        for k, v in P.items():
            if v is None: continue
            
            fert_name = k.split('_')[1] if '_' in k and len(k.split('_')) > 1 else "无肥料"
            
            
            alt_hourly, alt_diff, curr_net, alt_net, base_exp_key, extra_seeds = analyze_expansion_opportunity(
                c, fert_name, v, k, P, F, self.dm.data.get("fertilizers", [])
            )
                
            data_list.append({
                's': k, 'p': v, 'np': curr_net, 
                'alt': alt_hourly, 'altd': alt_diff, 'alt_net': alt_net, 
                'plots': extra_seeds 
            })

        data_list = sorted(data_list, key=lambda x: x['p'], reverse=True)
        
        if data_list:
            mv = max(d['p'] for d in data_list)
            for item in data_list:
                # 格式化渲染
                alt_str = f"🔹 {item['alt']:.2f}" if item['alt'] > 0 else "-"
                alt_net_str = f"🔹 {item['alt_net']:.2f}" if item['alt_net'] > 0 else "-"
                
                if item['altd'] > 0: altd_str = f"🔹 +{item['altd']:.2f}"
                elif item['altd'] < 0: altd_str = f"🔹 {item['altd']:.2f}"
                else: altd_str = "-"
                
                
                plots_str = f"🔹 +{item['plots']:.2f}" if item['plots'] > 0 else "-"
                
                tags = ('max' if item['p'] == mv else ('min' if item['p'] < 0 else 'norm'),)
                tv.insert("", "end", values=(
                    item['s'], f"{item['p']:.2f}", f"{item['np']:.2f}", 
                    alt_str, altd_str, alt_net_str, plots_str 
                ), tags=tags)
                
        tv.tag_configure('max', foreground='#1a73e8', font=('微软雅黑', 10, 'bold'))
        tv.tag_configure('min', foreground='#d93025')
        
        def dbl_f(e):
            sel = tv.selection()
            if sel and tv.item(sel[0])['values'][0] in F: 
                FormulaViewer.render(w, c['name'], tv.item(sel[0])['values'][0], F[tv.item(sel[0])['values'][0]])
        tv.bind("<Double-1>", dbl_f)

    def show_details_popup(self, n):
        c = next((x for x in self.dm.data["crops"] if x["name"] == n), None); self.show_details(c) if c else None

class DatabaseTab:
    def __init__(self, parent, app, dm):
        self.app = app; self.dm = dm
        self.db_sheet = Sheet(parent, align="center", header_align="center", theme="light blue", font=("微软雅黑", 10, "normal"), header_font=("微软雅黑", 10, "bold"), row_height=28, header_height=32)
        self.db_sheet.pack(fill="both", expand=True, padx=8, pady=8); self.db_sheet.hide("row_index")
        self.db_sheet.enable_bindings(("single_select", "drag_select", "row_select", "arrowkeys", "copy"))
        self.db_sheet.MT.bind("<Button-3>", self.on_db_right_click, add="+")
        bf = ttk.Frame(parent); bf.pack(side='bottom', fill='x', pady=8, padx=8)
        ttk.Button(bf, text="⬆️ 上移该行", command=self.move_db_up).pack(side='left', padx=5)
        ttk.Button(bf, text="⬇️ 下移该行", command=self.move_db_down).pack(side='left', padx=5)
        self.refresh_db()

    def refresh_db(self):
        cols = list(config.DB_KEY_MAP.values()); self.db_sheet.headers(cols)
        db_crops = sorted(self.dm.data["crops"], key=lambda x: x.get("_db_index", 0))
        rows = [[str(c.get(k, "")) for k in config.DB_KEY_MAP] for c in db_crops]
        self.db_sheet.set_sheet_data(rows, reset_col_positions=True); self.db_sheet.dehighlight_all()
        for i in range(len(rows)):
            if i % 2 == 1: self.db_sheet.highlight_rows(rows=[i], bg="#f4f7fb")
        try: self.db_sheet.align("center"); self.db_sheet.header_align("center")
        except: pass
        self.db_sheet.refresh()

    def on_db_right_click(self, event):
        r = self.db_sheet.identify_row(event)
        if r is not None:
            self.db_sheet.set_currently_selected(r, 0)
            m = tk.Menu(self.app, tearoff=0, font=("微软雅黑", 9)); m.add_command(label="✏️ 编辑作物属性", command=self.open_edit_win_db)
            m.post(event.x_root, event.y_root)

    def open_edit_win_db(self):
        sel = self.db_sheet.get_currently_selected()
        if sel: CropEditor(self.app, self.db_sheet.get_cell_data(sel[0], self.db_sheet.headers().index("名称") if "名称" in self.db_sheet.headers() else 0))

    def move_db_up(self):
        sel = self.db_sheet.get_currently_selected()
        if not sel or sel[0] == 0: return
        r = sel[0]; db_crops = sorted(self.dm.data["crops"], key=lambda x: x.get("_db_index", 0))
        db_crops[r]["_db_index"], db_crops[r-1]["_db_index"] = db_crops[r-1]["_db_index"], db_crops[r]["_db_index"]
        self.dm.save_data(); self.refresh_db(); self.db_sheet.set_currently_selected(r-1, 0)

    def move_db_down(self):
        sel = self.db_sheet.get_currently_selected()
        db_crops = sorted(self.dm.data["crops"], key=lambda x: x.get("_db_index", 0))
        if not sel or sel[0] >= len(db_crops) - 1: return
        r = sel[0]; db_crops[r]["_db_index"], db_crops[r+1]["_db_index"] = db_crops[r+1]["_db_index"], db_crops[r]["_db_index"]
        self.dm.save_data(); self.refresh_db(); self.db_sheet.set_currently_selected(r+1, 0)

class SettingsTab:
    def __init__(self, parent, app, dm):
        self.app = app; self.dm = dm
        f = tk.Frame(parent, bg="#f5f5f7"); f.pack(fill='both', padx=40, pady=40)
        self.s_ents = {}
        for i, (k, l) in enumerate(config.SETTINGS_LANG_MAP.items()):
            tk.Label(f, text=l, bg="#f5f5f7", font=("微软雅黑", 9)).grid(row=i, column=0, sticky='e', pady=6)
            e = ttk.Entry(f, width=28); e.grid(row=i, column=1, padx=12, pady=6)
            e.insert(0, str(self.dm.data["settings"].get(k,""))); self.s_ents[k] = e
        
        # 修改按钮栏，增加“打开路径”按钮
        btn_frame = ttk.Frame(f)
        btn_frame.grid(row=20, column=1, pady=30, sticky='w')
        
        ttk.Button(btn_frame, text=" 💾 保存算法设置 ", command=self.save_settings).pack(side='left')
        ttk.Button(btn_frame, text=" 📂 打开存档路径 ", command=self.open_archive_path).pack(side='left', padx=10)
    
    def refresh_settings_ui(self):
        """刷新设置页面的输入框数值"""
        for k, e in self.s_ents.items():
            e.delete(0, tk.END)
            e.insert(0, str(self.dm.data["settings"].get(k, "")))
    def open_archive_path(self):
        """
        ② 快速打开存档路径：调用系统资源管理器
        """
        import os
        if os.path.exists(config.APP_DIR):
            os.startfile(config.APP_DIR) # Windows 专用
        else:
            messagebox.showerror("错误", "存档文件夹尚未创建！")


    def save_settings(self):
        for k,e in self.s_ents.items(): self.dm.data["settings"][k]=float(e.get())
        self.dm.save_data(); self.app.refresh_all()

class FertilizerTab:
    def __init__(self, parent, app, dm):
        self.app = app; self.dm = dm
        self.fert_sheet = Sheet(parent, align="center", header_align="center", valign="center", header_valign="center", theme="light blue", font=("微软雅黑", 10, "normal"), header_font=("微软雅黑", 10, "bold"), row_height=38, header_height=42)
        self.fert_sheet.set_options(table_font_vertical_alignment="center", header_font_vertical_alignment="center")
        self.fert_sheet.pack(fill="both", expand=True, padx=8, pady=8)
        self.fert_sheet.enable_bindings(("single_select", "row_select", "column_width_resize", "arrowkeys", "copy", "rc_select", "edit_cell"))
        
        bf = ttk.Frame(parent); bf.pack(side='bottom', fill='x', pady=8, padx=8)
        ttk.Label(bf, text="💡 提示: 双击表格直接编辑。类型仅限填 speed(催熟) 或 yield(增产)。", font=("微软雅黑", 9), foreground="#666666").pack(side='left')
        ttk.Button(bf, text="💾 保存并更新计算引擎", command=self.save_fert_changes).pack(side='right', padx=10)
        ttk.Button(bf, text="❌ 删除选中行", command=self.delete_fert).pack(side='right')
        ttk.Button(bf, text="➕ 研发新肥料", command=self.add_fert).pack(side='right', padx=10)
        self.refresh_fert_list()

    def refresh_fert_list(self):
        self.fert_sheet.headers(["肥料名称", "类型 (speed/yield)", "效果数值 (减时/倍率)", "每次消耗成本"])
        data = [[f.get("name", ""), f.get("type", "speed"), f.get("effect", 0.0), f.get("cost", 0.0)] for f in self.dm.data["fertilizers"]]
        self.fert_sheet.set_sheet_data(data)
        self.fert_sheet.column_width(0, 150); self.fert_sheet.column_width(1, 150)
        self.fert_sheet.column_width(2, 180); self.fert_sheet.column_width(3, 150)
        self.fert_sheet.redraw()

    def add_fert(self):
        self.dm.data["fertilizers"].append({"name": "新肥料", "type": "speed", "effect": 1.0, "cost": 10.0})
        self.refresh_fert_list(); self.fert_sheet.see(len(self.dm.data["fertilizers"]) - 1, 0)

    def delete_fert(self):
        sel = self.fert_sheet.get_currently_selected()
        if sel:
            r = sel[0]; fert_name = self.dm.data["fertilizers"][r]["name"]
            if messagebox.askyesno("危险操作", f"确定要删除【{fert_name}】吗？\n所有与其相关的收益计算列都将消失！"):
                del self.dm.data["fertilizers"][r]; self.refresh_fert_list()

    def save_fert_changes(self):
        try:
            raw_data = self.fert_sheet.get_sheet_data(); new_ferts = []
            for row in raw_data:
                name = str(row[0]).strip(); ftype = str(row[1]).strip().lower()
                if ftype not in ["speed", "yield"]: return messagebox.showerror("格式错误", f"【{name}】的类型错误！\n只能填写 'speed' 或 'yield'。")
                effect = float(row[2]); cost = float(row[3])
                new_ferts.append({"name": name, "type": ftype, "effect": effect, "cost": cost})
            self.dm.data["fertilizers"] = new_ferts
            self.dm.save_data()

            # 1. 重新构建动态公式和分组信息
            self.dm.rebuild_dynamic_columns()
            
            # 2. 定义当前合法的 ID 库
            valid_ids = set(config.ALL_COLS.keys()) | set(config.DB_KEY_MAP.keys()) | \
                        {"process_status", "best_profit", "best_strategy", "verified", "type"}
            
            old_disp = list(self.dm.data["display_columns"])
            expanded_parents = set()
            
            # 3. 【核心修复 Step 1】记录哪些父级列当前正处于“展开”状态
            # 逻辑：如果一个父级列后面跟着任何一个属于它的“孩子列”，就视为展开
            for i, col_id in enumerate(old_disp):
                if col_id in config.COLUMN_GROUPS:
                    kids = config.COLUMN_GROUPS[col_id]
                    if i + 1 < len(old_disp) and old_disp[i+1] in kids:
                        expanded_parents.add(col_id)

            # 4. 【核心修复 Step 2】获取当前所有合法的“孩子列”总表（用于彻底清算残留）
            all_kids = set()
            for kids_list in config.COLUMN_GROUPS.values():
                all_kids.update(kids_list)

            # 5. 【核心修复 Step 3】提取骨架：剔除所有孩子列和不再合法的旧列
            skeleton = [c for c in old_disp if c not in all_kids and c in valid_ids]

            # 6. 【核心修复 Step 4】根据骨架重建最终显示列表
            new_disp = []
            for col_id in skeleton:
                new_disp.append(col_id)
                # 如果这个父级列之前是展开的，现在把最新的“孩子们”塞进去
                if col_id in expanded_parents:
                    new_disp.extend(config.COLUMN_GROUPS[col_id])

            # 7. 更新并刷新
            self.dm.data["display_columns"] = new_disp
            self.dm.save_data()
            self.app.report_tab.refresh_list(keep_widths=True)
            
            messagebox.showinfo("成功", "肥料配方已更新！重复列残留已自动清理。")
            
        except Exception as e: 
            messagebox.showerror("系统错误", f"同步失败: {e}")

class CompareTab:
    def __init__(self, parent, app, dm):
        self.app = app; self.dm = dm
        self.pool_crops = [] # 🌟 核心：记录持久化的作物池名单

        ctrl_frame = ttk.Frame(parent); ctrl_frame.pack(fill='x', padx=10, pady=10)
        ttk.Label(ctrl_frame, text="1. 选择要评估的肥料:", font=("微软雅黑", 10, "bold")).pack(side='left', padx=(0, 5))
        self.cmp_fert_combo = ttk.Combobox(ctrl_frame, state="readonly", width=18, font=("微软雅黑", 10))
        self.cmp_fert_combo.pack(side='left', padx=5)
        ttk.Button(ctrl_frame, text="🔄 刷新肥料列表", command=self.refresh_cmp_ferts).pack(side='left', padx=5)
        ttk.Button(ctrl_frame, text="🚀 开始对比计算", command=self.run_comparison).pack(side='left', padx=30)

        body_frame = ttk.Frame(parent); body_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        # --- 左侧：备选池 ---
        left_frame = ttk.LabelFrame(body_frame, text=" 2. 备选作物池 "); left_frame.pack(side='left', fill='y', padx=(0, 5))
        scroll_left = ttk.Scrollbar(left_frame); scroll_left.pack(side='right', fill='y')
        self.lb_source = tk.Listbox(left_frame, selectmode=tk.EXTENDED, yscrollcommand=scroll_left.set, width=20, font=("微软雅黑", 11))
        self.lb_source.pack(side='top', fill='both', expand=True, padx=5, pady=5); scroll_left.config(command=self.lb_source.yview)
        
        # --- 中间：控制按钮 ---
        mid_frame = ttk.Frame(body_frame); mid_frame.pack(side='left', fill='y', padx=5)
        tk.Label(mid_frame, text="").pack(expand=True) 
        ttk.Button(mid_frame, text="加入对比 >>", command=self.add_to_pool).pack(pady=5)
        ttk.Button(mid_frame, text="<< 移出对比", command=self.remove_from_pool).pack(pady=5)
        ttk.Button(mid_frame, text="清空池子 ×", command=self.clear_pool).pack(pady=20)
        tk.Label(mid_frame, text="").pack(expand=True) 

        # --- 右侧：目标池 ---
        right_pool_frame = ttk.LabelFrame(body_frame, text=" 3. 已选对比池 "); right_pool_frame.pack(side='left', fill='y', padx=(5, 10))
        scroll_right = ttk.Scrollbar(right_pool_frame); scroll_right.pack(side='right', fill='y')
        self.lb_target = tk.Listbox(right_pool_frame, selectmode=tk.EXTENDED, yscrollcommand=scroll_right.set, width=20, font=("微软雅黑", 11), fg="#1a73e8")
        self.lb_target.pack(side='top', fill='both', expand=True, padx=5, pady=5); scroll_right.config(command=self.lb_target.yview)

        # --- 最右侧：结果表格 ---
        result_frame = ttk.LabelFrame(body_frame, text=" 4. 效益分析结果"); result_frame.pack(side='left', fill='both', expand=True)
        self.cmp_sheet = Sheet(result_frame, align="center", header_align="center", valign="center", header_valign="center", theme="light blue", font=("微软雅黑", 10, "normal"), header_font=("微软雅黑", 10, "bold"), row_height=38, header_height=42)
        self.cmp_sheet.set_options(table_font_vertical_alignment="center", header_font_vertical_alignment="center")
        self.cmp_sheet.pack(fill='both', expand=True, padx=8, pady=8)
        self.cmp_sheet.enable_bindings("single_select", "row_select", "column_width_resize", "arrowkeys", "copy")

        # 🌟 丢失的代码找回：绑定拖拽列宽事件
        self.cmp_sheet.extra_bindings("column_width_resize", self.exec_sync_width)

        self.refresh_cmp_ferts(); self.refresh_cmp_crops()

    # 🌟 丢失的代码找回：实时保存列宽的函数
    def exec_sync_width(self, event):
        try:
            if isinstance(event, dict) and 'resized' in event and event['resized'].get('columns', {}):
                c_idx = list(event['resized']['columns'].keys())[0]
                new_w = max(40, event['resized']['columns'][c_idx].get('new_size', 40))
                self.cmp_sheet.column_width(c_idx, width=new_w)
                
                if "cmp_tksheet_widths" not in self.dm.data:
                    self.dm.data["cmp_tksheet_widths"] = {}
                self.dm.data["cmp_tksheet_widths"][str(c_idx)] = new_w
                self.dm.save_data()
        except Exception as e:
            self.dm.debug_print(f"[DEBUG] ❌ 对比页列宽保存报错: {e}")

    # ===== 以下为池子模式及计算逻辑 =====
    def add_to_pool(self):
        sel = self.lb_source.curselection()
        for i in sel:
            crop = self.lb_source.get(i)
            if crop not in self.pool_crops:
                self.pool_crops.append(crop)
        self.refresh_pool_ui()

    def remove_from_pool(self):
        sel = self.lb_target.curselection()
        for i in reversed(sel): 
            del self.pool_crops[i]
        self.refresh_pool_ui()

    def clear_pool(self):
        self.pool_crops.clear()
        self.refresh_pool_ui()

    def refresh_pool_ui(self):
        self.lb_target.delete(0, tk.END)
        for c in self.pool_crops:
            self.lb_target.insert(tk.END, c)

    def refresh_cmp_ferts(self):
        ferts = [f["name"] for f in self.dm.data.get("fertilizers", [])]
        self.cmp_fert_combo['values'] = ferts
        if ferts: self.cmp_fert_combo.current(0)

    def refresh_cmp_crops(self):
        self.lb_source.delete(0, tk.END)
        for c in self.dm.data.get("crops", []): 
            self.lb_source.insert(tk.END, c.get("name", "未知作物"))

    def run_comparison(self):
        target_fert = self.cmp_fert_combo.get()
        if not target_fert: return messagebox.showwarning("提示", "请先选择一种肥料！")
        if not hasattr(self, 'pool_crops') or not self.pool_crops: 
            return messagebox.showwarning("提示", "请先将作物加入【已选对比池】！")

        results = []
        for crop_name in self.pool_crops:
            c = next((x for x in self.dm.data["crops"] if x.get("name") == crop_name), None)
            if not c: continue
            
            P, F = calc_profits(c, self.dm.data["settings"], self.dm.data.get("fertilizers", []))
            
            no_fert_keys = {k: v for k, v in P.items() if "无肥料" in k and v is not None}
            best_no_fert_k = max(no_fert_keys, key=no_fert_keys.get) if no_fert_keys else "无"
            best_no_fert_v = no_fert_keys.get(best_no_fert_k, 0)
            
            tgt_fert_keys = {k: v for k, v in P.items() if target_fert in k and v is not None}
            best_tgt_fert_k = max(tgt_fert_keys, key=tgt_fert_keys.get) if tgt_fert_keys else "无"
            best_tgt_fert_v = tgt_fert_keys.get(best_tgt_fert_k, 0)
            
            diff = best_tgt_fert_v - best_no_fert_v
            
            
            alt_hourly, alt_diff, curr_net, alt_net, base_exp_key, extra_seeds = analyze_expansion_opportunity(
                c, target_fert, best_tgt_fert_v, best_tgt_fert_k, P, F, self.dm.data.get("fertilizers", [])
            )
                
            results.append({
                "name": crop_name, 
                "base_strat": best_no_fert_k.replace("_无肥料", ""), "base_val": best_no_fert_v,
                "fert_val": best_tgt_fert_v, "curr_net": curr_net,
                "diff": diff, "alt_hourly": alt_hourly, "alt_diff": alt_diff, "alt_net": alt_net,
                "plots": extra_seeds 
            })
            
        results.sort(key=lambda x: x["diff"], reverse=True)
        
        # 🌟 移除了“施肥后最优流派”，加入了两列“单次收益”
        headers = ["排名", "作物名称", "原最优流派", "原最高时薪", "施肥后时薪", "🔥 施肥时薪增量", "💰 施肥单次收益", "🔲 扩种地块数", "🌱 扩种等价时薪", "📈 扩种时薪增量", "🌾 扩种单次收益"]
        self.cmp_sheet.headers(headers)
        
        sheet_data = []
        for i, r in enumerate(results):
            rank = f"Top {i+1}" if i < 3 else str(i+1)
            diff_str = f"+{r['diff']:.2f}" if r['diff'] > 0 else f"{r['diff']:.2f}"
            alt_h_str = f"{r['alt_hourly']:.2f}" if r['alt_hourly'] > 0 else "-"
            alt_n_str = f"{r['alt_net']:.2f}" if r['alt_net'] > 0 else "-"
            
            if r['alt_diff'] > 0: alt_d_str = f"+{r['alt_diff']:.2f}"
            elif r['alt_diff'] < 0: alt_d_str = f"{r['alt_diff']:.2f}"
            else: alt_d_str = "-"
            
            plots_str = f"+{r['plots']:.2f}" if r['plots'] > 0 else "-"
            
            sheet_data.append([
                rank, r["name"], r["base_strat"], f"{r['base_val']:.2f}", 
                f"{r['fert_val']:.2f}", diff_str, f"{r['curr_net']:.2f}",
                plots_str, 
                alt_h_str, alt_d_str, alt_n_str
            ])
            
        self.cmp_sheet.set_sheet_data(sheet_data)
        
        # 新增列后的默认宽度调整
        default_widths = [60, 100, 100, 100, 100, 130, 130, 100, 140, 140, 140]
        saved_widths = self.dm.data.get("cmp_tksheet_widths", {})
        for i, default_w in enumerate(default_widths):
            w = saved_widths.get(str(i), default_w) 
            self.cmp_sheet.column_width(i, int(w))
            
        self.cmp_sheet.dehighlight_all()
        for i in range(len(results)):
            # 常规红绿高亮 (diff 现处于索引 5)
            if results[i]["diff"] > 0:
                bg_c = "#e8f5e9" if i < 3 else ""
                self.cmp_sheet.highlight_cells(row=i, column=5, bg=bg_c, fg="#2e7d32")
            elif results[i]["diff"] < 0: 
                self.cmp_sheet.highlight_cells(row=i, column=5, bg="#ffebee", fg="#c62828")
                
            # 设置漂亮的蓝色字 (新加的 plots 在 7，后续顺延到 8, 9, 10)
            if results[i]["plots"] > 0:
                self.cmp_sheet.highlight_cells(row=i, column=7, fg="#1a73e8")
            if results[i]["alt_hourly"] > 0:
                self.cmp_sheet.highlight_cells(row=i, column=8, fg="#1a73e8")
            if results[i]["alt_diff"] != 0:
                self.cmp_sheet.highlight_cells(row=i, column=9, fg="#1a73e8")
            if results[i]["alt_net"] > 0:
                self.cmp_sheet.highlight_cells(row=i, column=10, fg="#1a73e8")
                
            # 🔥 智商税终极预警：扩种 > 当前施肥方案 (索引顺延到 9)
            if results[i]["alt_diff"] > 0:
                self.cmp_sheet.highlight_cells(row=i, column=9, bg="#fff8e1", fg="#f57f17")
                
        self.cmp_sheet.redraw()

class ProductionTab:
    def __init__(self, parent, app, data_manager):
        self.app = app
        self.dm = data_manager
        
        if "recipes" not in self.dm.data:
            self.dm.data["recipes"] = {}

        # 状态变量
        self.sort_desc = True # 默认按等级降序
        self.current_library_names = [] # 记录当前列表框中对应的真实产物名称
        self.var_target_product = tk.StringVar(value="[请从右侧库中选择]") # 当前锁定的目标

        # 页面主框架：左右分栏
        self.frame = tk.Frame(parent, bg="white")
        self.frame.pack(fill="both", expand=True)
        
        left_frame = tk.Frame(self.frame, bg="white")
        left_frame.pack(side="left", fill="both", expand=True, padx=15, pady=15)
        
        right_frame = tk.Frame(self.frame, bg="#f5f5f7", width=300)
        right_frame.pack(side="right", fill="y", padx=15, pady=15)
        right_frame.pack_propagate(False)

        # ================= 左侧：BOM 整体可视化 =================
        tk.Label(left_frame, text="📊 生产链图纸分析", font=("微软雅黑", 12, "bold"), bg="white").pack(anchor="w", pady=(0, 10))
        
        f_top = tk.Frame(left_frame, bg="white")
        f_top.pack(fill="x", pady=5)
        
        # ⑥ 移除手动输入框，改为直观的选中显示
        tk.Label(f_top, text="当前目标:", bg="white").pack(side="left")
        tk.Label(f_top, textvariable=self.var_target_product, font=("微软雅黑", 11, "bold"), fg="#1565c0", bg="white").pack(side="left", padx=5)
        
        tk.Label(f_top, text="需求总数:", bg="white").pack(side="left", padx=(15, 2))
        self.ent_target_qty = ttk.Entry(f_top, width=6)
        self.ent_target_qty.insert(0, "1")
        self.ent_target_qty.pack(side="left", padx=5)
        
        ttk.Button(f_top, text="🚀 重新生成物料清单", command=self.generate_bom).pack(side="left", padx=10)
        tk.Label(f_top, text="💡 在树状图中【右键】底料可快速补全配方", fg="#888", bg="white").pack(side="left", padx=10)

        # BOM 树状图
        self.tv = ttk.Treeview(left_frame, show="tree", height=20)
        self.tv.pack(fill="both", expand=True)
        self.tv.bind("<Button-3>", self.on_right_click_tree)
        
        self.tv.tag_configure("verified", foreground="#2e7d32") 
        self.tv.tag_configure("unverified", foreground="#d84315", font=("微软雅黑", 10, "bold")) 
        self.tv.tag_configure("root_sum", foreground="#1565c0", font=("微软雅黑", 11, "bold"))

        # ================= 右侧：产物管理总库 =================
        tk.Label(right_frame, text="📦 产物管理库", font=("微软雅黑", 12, "bold"), bg="#f5f5f7").pack(anchor="w", pady=(0, 10))
        
        f_search = tk.Frame(right_frame, bg="#f5f5f7")
        f_search.pack(fill="x", pady=5)
        tk.Label(f_search, text="🔍 搜索:", bg="#f5f5f7").pack(side="left")
        self.ent_search = ttk.Entry(f_search)
        self.ent_search.pack(side="left", fill="x", expand=True, padx=(5, 5))
        self.ent_search.bind("<KeyRelease>", lambda e: self.refresh_library()) 
        
        # ④ 等级排序切换按钮
        ttk.Button(f_search, text="↕等级", width=5, command=self.toggle_sort).pack(side="right")

        self.lb_library = tk.Listbox(right_frame, font=("微软雅黑", 10), selectmode="browse")
        self.lb_library.pack(fill="both", expand=True, pady=10)
        # ① 双击改为：设为目标并计算
        self.lb_library.bind("<Double-Button-1>", lambda e: self.set_as_target()) 
        # ③ 绑定右键菜单
        self.lb_library.bind("<Button-3>", self.show_library_context_menu)

        # 构建产物库右键菜单
        self.menu_lib = tk.Menu(self.frame, tearoff=0)
        self.menu_lib.add_command(label="🎯 设为目标并计算", command=self.set_as_target)
        self.menu_lib.add_command(label="✏️ 编辑该配方", command=self.edit_selected_recipe)
        self.menu_lib.add_command(label="🔄 切换核对状态", command=self.toggle_verify_status)
        self.menu_lib.add_separator()
        self.menu_lib.add_command(label="🗑️ 彻底删除", command=self.delete_selected_recipe)

        f_btns1 = tk.Frame(right_frame, bg="#f5f5f7")
        f_btns1.pack(fill="x", pady=2)
        ttk.Button(f_btns1, text="➕ 新增基础产物", command=lambda: self.open_recipe_editor("")).pack(side="left", fill="x", expand=True)

        # 初始化加载库
        self.refresh_library()

    # --- ④ 核心逻辑：递归计算产物等级 ---
    def _calc_item_level(self, item_name, path=None):
        """计算最长链路深度。原材=Lv1，需要原材合成=Lv2"""
        if path is None: path = set()
        if item_name in path: return 1 # 防止循环依赖死循环
        
        recipes = self.dm.data.get("recipes", {})
        mats = recipes.get(item_name, {}).get("materials", {})
        if not mats: return 1 # 如果没有下级材料，那就是最底层的原矿/原果
        
        path.add(item_name)
        max_depth = 1
        for mat in mats:
            depth = self._calc_item_level(mat, path.copy())
            if depth > max_depth: max_depth = depth
        return max_depth + 1

    # --- 产物库交互逻辑 ---
    def toggle_sort(self):
        self.sort_desc = not self.sort_desc
        self.refresh_library()

    def refresh_library(self):
        self.lb_library.delete(0, tk.END)
        self.current_library_names.clear()
        
        keyword = self.ent_search.get().strip().lower()
        recipes = self.dm.data.get("recipes", {})
        
        # 收集并计算等级
        items_data = []
        for name, data in recipes.items():
            if keyword in name.lower():
                level = self._calc_item_level(name)
                items_data.append((name, data, level))
                
        # 排序：按等级降/升序，等级相同的按名称排
        items_data.sort(key=lambda x: (x[2], x[0]), reverse=self.sort_desc)
        
        # 填充列表
        for name, data, level in items_data:
            status = "✅" if data.get("verified", False) else "❌"
            display_text = f"[Lv.{level}] {status} {name}"
            self.lb_library.insert(tk.END, display_text)
            self.current_library_names.append(name) # 同步保存真实名字

    def get_selected_library_item(self):
        sel = self.lb_library.curselection()
        if not sel: return None
        return self.current_library_names[sel[0]] # 准确提取对应的真实名字

    def show_library_context_menu(self, event):
        """③ 产物库右键弹出菜单"""
        idx = self.lb_library.nearest(event.y)
        if idx >= 0:
            self.lb_library.selection_clear(0, tk.END)
            self.lb_library.selection_set(idx)
            self.lb_library.activate(idx)
            self.menu_lib.tk_popup(event.x_root, event.y_root)

    def toggle_verify_status(self):
        """③ 右键快捷切换核对状态"""
        name = self.get_selected_library_item()
        if name and name in self.dm.data.get("recipes", {}):
            current_status = self.dm.data["recipes"][name].get("verified", False)
            self.dm.data["recipes"][name]["verified"] = not current_status
            self.dm.save_data()
            self.refresh_library()
            self.generate_bom()

    def set_as_target(self):
        name = self.get_selected_library_item()
        if name:
            self.var_target_product.set(name) # ⑥ 更新锁定的目标
            self.generate_bom() # 自动开始计算

    def edit_selected_recipe(self):
        name = self.get_selected_library_item()
        if name: self.open_recipe_editor(name)

    def delete_selected_recipe(self):
        name = self.get_selected_library_item()
        if not name: return
        if messagebox.askyesno("危险操作", f"确定要从数据库彻底删除产物【{name}】吗？\n删除后包含它的高级配方也会报错！"):
            del self.dm.data["recipes"][name]
            self.dm.save_data()
            self.refresh_library()
            self.generate_bom()

    # --- 核心：配方编辑弹窗 (模态框) ---
    def open_recipe_editor(self, default_name=""):
        win = tk.Toplevel(self.app)
        win.title(f"🛠️ 编辑配方 - {default_name}" if default_name else "🛠️ 新增产物配方")
        
        # ⑤ 弹窗智能定位到鼠标附近
        mouse_x, mouse_y = self.app.winfo_pointerxy()
        win.geometry(f"360x480+{mouse_x}+{mouse_y}")
        win.minsize(360, 480)

        win.transient(self.app)
        win.grab_set() 
        
        recipe = self.dm.data.get("recipes", {}).get(default_name, {})
        local_mats = recipe.get("materials", {}).copy()
        var_ver = tk.BooleanVar(value=recipe.get("verified", False))

        f_main = tk.Frame(win, padx=20, pady=15)
        f_main.pack(fill="both", expand=True)

        tk.Label(f_main, text="产物名称:").pack(anchor="w")
        ent_name = ttk.Entry(f_main, font=("微软雅黑", 10))
        ent_name.pack(fill="x", pady=2)
        ent_name.insert(0, default_name)
        if default_name: ent_name.configure(state="readonly")

        tk.Checkbutton(f_main, text="✅ 标记为【已核对】(底层已无缺失)", variable=var_ver).pack(anchor="w", pady=5)

        tk.Label(f_main, text="所需材料:").pack(anchor="w", pady=(10, 2))
        f_add = tk.Frame(f_main)
        f_add.pack(fill="x")
        ent_m_name = ttk.Entry(f_add, width=15)
        ent_m_name.pack(side="left")
        tk.Label(f_add, text="数量:").pack(side="left", padx=2)
        ent_m_qty = ttk.Entry(f_add, width=6)
        ent_m_qty.pack(side="left")
        
        lb_mats = tk.Listbox(f_main, height=8, font=("微软雅黑", 10))
        
        def refresh_local_list():
            lb_mats.delete(0, tk.END)
            for m_name, m_qty in local_mats.items():
                q_fmt = int(m_qty) if m_qty.is_integer() else m_qty
                lb_mats.insert(tk.END, f"{m_name} x {q_fmt}")
                
        def add_mat():
            n, q_str = ent_m_name.get().strip(), ent_m_qty.get().strip()
            if not n or not q_str: return
            try:
                local_mats[n] = float(q_str)
                refresh_local_list()
                ent_m_name.delete(0, tk.END); ent_m_qty.delete(0, tk.END)
                ent_m_name.focus()
            except: messagebox.showerror("错误", "数量必须是数字", parent=win)

        def del_mat():
            sel = lb_mats.curselection()
            if not sel: return
            n = lb_mats.get(sel[0]).split(" x ")[0]
            if n in local_mats: del local_mats[n]; refresh_local_list()

        ttk.Button(f_add, text="添加", command=add_mat).pack(side="left", padx=5)
        lb_mats.pack(fill="x", pady=5)
        
        # ② 修复弹窗底部的按钮排版，去除异常空白
        f_bottom = tk.Frame(f_main)
        f_bottom.pack(fill="x", pady=(5, 0))
        ttk.Button(f_bottom, text="➖ 移除选中材料", command=del_mat).pack(side="left")
        
        def save_and_close():
            final_name = ent_name.get().strip()
            if not final_name: return messagebox.showwarning("提示", "产物名称不能为空", parent=win)
            self.dm.data["recipes"][final_name] = {"verified": var_ver.get(), "materials": local_mats.copy()}
            self.dm.save_data()
            self.refresh_library()
            
            # 如果正处在计算分析该产物的状态，自动刷新分析图
            if self.var_target_product.get() == final_name or "未选择" not in self.var_target_product.get():
                self.generate_bom()
            win.destroy()

        ttk.Button(f_main, text="💾 保存配方并关闭", command=save_and_close).pack(fill="x", pady=3)
        refresh_local_list()

    # --- BOM 分析引擎逻辑 ---
    def _calc_flat_totals(self, item_name, qty, path_set):
        if item_name in path_set: return 
        self.flat_totals[item_name] = self.flat_totals.get(item_name, 0) + qty
        recipes = self.dm.data.get("recipes", {})
        is_known = item_name in recipes
        if not is_known or not recipes[item_name].get("verified", False):
            self.unverified_items.add(item_name)
        if is_known:
            new_path = path_set.copy()
            new_path.add(item_name)
            for mat_name, u_qty in recipes[item_name].get("materials", {}).items():
                self._calc_flat_totals(mat_name, qty * u_qty, new_path)

    def generate_bom(self):
        target = self.var_target_product.get().strip()
        qty_str = self.ent_target_qty.get().strip()
        self.tv.delete(*self.tv.get_children()) 
        
        if "请从右侧库中选择" in target or not target: return
        
        try: total_qty = float(qty_str)
        except: return messagebox.showerror("错误", "需求总数必须是纯数字！")

        self.flat_totals = {}
        self.unverified_items = set()
        self._calc_flat_totals(target, total_qty, set())

        node_sum = self.tv.insert("", "end", text="🛒 【全局材料总需】 (自动合并汇总)", tags=("root_sum",))
        for item, qty in self.flat_totals.items():
            qty_fmt = int(qty) if qty.is_integer() else qty
            is_veri = item not in self.unverified_items
            status = "✅" if is_veri else "❌[缺底层配方]"
            tag = "verified" if is_veri else "unverified"
            self.tv.insert(node_sum, "end", text=f" ▪ {item}   x {qty_fmt}   {status}", values=(item,), tags=(tag,))
        self.tv.item(node_sum, open=True)

        node_path = self.tv.insert("", "end", text=f"🗺️ 【{target}】 生产流程路线图", tags=("root_sum",))
        self.insert_bom_node(node_path, target, total_qty, set())
        self.tv.item(node_path, open=True)

    def insert_bom_node(self, parent_id, item_name, required_qty, path_set):
        recipes = self.dm.data.get("recipes", {})
        qty_fmt = int(required_qty) if required_qty.is_integer() else required_qty
        
        if item_name in path_set:
            self.tv.insert(parent_id, "end", text=f"⚠️ {item_name}   x {qty_fmt}   (循环嵌套异常)", values=(item_name,), tags=("unverified",))
            return

        is_known = item_name in recipes
        is_verified = is_known and recipes[item_name].get("verified", False)
        status_text = "[✅已核对]" if is_verified else "[❌未核对]"
        tag = "verified" if is_verified else "unverified"
        display_text = f" └─ {item_name}   x {qty_fmt}   {status_text}"
        
        node_id = self.tv.insert(parent_id, "end", text=display_text, values=(item_name,), tags=(tag,))
        
        if is_known:
            new_path = path_set.copy()
            new_path.add(item_name)
            for mat_name, unit_qty in recipes[item_name].get("materials", {}).items():
                self.insert_bom_node(node_id, mat_name, required_qty * unit_qty, new_path)
        self.tv.item(node_id, open=True)

    def on_right_click_tree(self, event):
        item_id = self.tv.identify_row(event.y)
        if not item_id: return
        vals = self.tv.item(item_id, "values")
        if not vals: return 
        item_name = vals[0]
        
        # 顺藤摸瓜：直接打开智能跟随弹窗
        self.open_recipe_editor(item_name)