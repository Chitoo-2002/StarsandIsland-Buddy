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
        tv.heading("plots", text="🔲肥料等价种子数")

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
        
        # 原有的双击查看公式功能
        def dbl_f(e):
            sel = tv.selection()
            if sel and tv.item(sel[0])['values'][0] in F: 
                FormulaViewer.render(w, c['name'], tv.item(sel[0])['values'][0], F[tv.item(sel[0])['values'][0]])
        tv.bind("<Double-1>", dbl_f)

        # 🌟 新增的右键菜单功能
        def right_click_menu(e):
            # 获取鼠标点击位置所在的行号
            row_id = tv.identify_row(e.y)
            if not row_id: return
            
            # 强行选中被右键点击的这行（视觉反馈）
            tv.selection_set(row_id)
            
            # 获取当前行的策略名称 (第一列)
            strategy_name = tv.item(row_id)['values'][0]
            
            # 只有当该策略有对应的公式数据时，才弹出菜单
            if strategy_name in F:
                rm = tk.Menu(w, tearoff=0, font=("微软雅黑", 9))
                rm.add_command(
                    label=f"🔢 查看 [{strategy_name}] 计算公式", 
                    command=lambda: FormulaViewer.render(w, c['name'], strategy_name, F[strategy_name])
                )
                rm.post(e.x_root, e.y_root)

        tv.bind("<Button-3>", right_click_menu)

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
        headers = ["排名", "作物名称", "原最优流派", "原最高时薪", "施肥后时薪", "🔥 施肥时薪增量", "💰 施肥单次收益", "🔲 肥料等价种子数", "🌱 扩种等价时薪", "📈 扩种时薪增量", "🌾 扩种单次收益"]
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
        if "recipes" not in self.dm.data: self.dm.data["recipes"] = {}

        self.sort_desc = True 
        self.current_library_names = [] 
        self.var_target_product = tk.StringVar(value="[请从右侧库中选择]") 
        self.history = []     
        self.history_idx = -1 
        self.bom_right_clicked_item = "" 
        
        # 🌟 核心引擎数据：记录用户临时录入的已有库存
        self.temp_inventory = self.dm.data.setdefault("inventory", {})

        self.frame = tk.Frame(parent, bg="white")
        self.frame.pack(fill="both", expand=True)

        # ================= 顶部全局控制区 =================
        f_top = tk.Frame(self.frame, bg="white")
        f_top.pack(fill="x", padx=15, pady=(15, 5))
        
        tk.Label(f_top, text="📊 生产链图纸分析", font=("微软雅黑", 12, "bold"), bg="white").pack(side="left", padx=(0, 20))
        tk.Label(f_top, text="当前目标:", bg="white").pack(side="left")
        ttk.Button(f_top, text="◀", width=3, command=self.history_back).pack(side="left", padx=(5,0), ipadx=2)
        ttk.Button(f_top, text="▶", width=3, command=self.history_forward).pack(side="left", padx=(0,5), ipadx=2)
        tk.Label(f_top, textvariable=self.var_target_product, font=("微软雅黑", 11, "bold"), fg="#1565c0", bg="white").pack(side="left", padx=5)
        
        tk.Label(f_top, text="需求总数:", bg="white").pack(side="left", padx=(15, 2))
        self.ent_target_qty = ttk.Entry(f_top, width=6)
        self.ent_target_qty.insert(0, "1")
        self.ent_target_qty.pack(side="left", padx=5)
        ttk.Button(f_top, text="🚀 重新生成", command=self.generate_bom).pack(side="left", padx=(5, 15))
        
        # 🌟 新增的三个工具按钮
        ttk.Button(f_top, text="🔽展开", width=6, command=lambda: self.toggle_route_tree(True)).pack(side="left", padx=(0,2))
        ttk.Button(f_top, text="🔼收起", width=6, command=lambda: self.toggle_route_tree(False)).pack(side="left", padx=(0,10))
        ttk.Button(f_top, text="🧹清空库存", command=self.clear_inventory).pack(side="left", padx=5)
        
        tk.Label(f_top, text="💡提示: 双击文字编辑配方，右键调出菜单设置库存", fg="#888", bg="white").pack(side="left", padx=10)

        # ================= 三栏自由拖拽面板 =================
        self.paned = ttk.PanedWindow(self.frame, orient=tk.HORIZONTAL)
        self.paned.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        frame_guide = tk.Frame(self.paned, bg="white", width=10)
        frame_route = tk.Frame(self.paned, bg="white", width=10)
        frame_lib = tk.Frame(self.paned, bg="#f5f5f7", width=10)

        frame_guide.pack_propagate(False)
        frame_route.pack_propagate(False)
        frame_lib.pack_propagate(False)

        self.paned.add(frame_guide, weight=7)
        self.paned.add(frame_route, weight=9)
        self.paned.add(frame_lib, weight=3)

        # --- 第一栏：行动指南 ---
        tk.Label(frame_guide, text="🛒 生产行动指南", font=("微软雅黑", 11, "bold"), fg="#1565c0", bg="white").pack(anchor="w", pady=5, padx=5)
        self.tv_guide = ttk.Treeview(frame_guide, show="tree")
        self.tv_guide.pack(fill="both", expand=True)

        # --- 第二栏：路线图 ---
        tk.Label(frame_route, text="🗺️ 生产流程路线图", font=("微软雅黑", 11, "bold"), fg="#1565c0", bg="white").pack(anchor="w", pady=5, padx=5)
        
        route_xscroll = ttk.Scrollbar(frame_route, orient="horizontal")
        route_xscroll.pack(side="bottom", fill="x")
        
        self.tv_route = ttk.Treeview(frame_route, show="tree", xscrollcommand=route_xscroll.set)
        self.tv_route.pack(side="top", fill="both", expand=True)
        route_xscroll.config(command=self.tv_route.xview)
        self.tv_route.column("#0", stretch=False, width=2000)

        for tv in (self.tv_guide, self.tv_route):
            tv.bind("<Button-3>", self.on_right_click_tree)
            tv.bind("<Double-Button-1>", self.on_double_click_tree)
            tv.tag_configure("verified", foreground="#2e7d32", font=("微软雅黑", 11,'bold')) 
            tv.tag_configure("unverified", foreground="#d84315", font=("微软雅黑", 10, "bold")) 
            tv.tag_configure("root_sum", foreground="#1565c0", font=("微软雅黑", 11, "bold"))
            # 🌟 新增库存抵扣的高亮颜色样式
            tv.tag_configure("inventory", foreground="#827717", font=("微软雅黑", 10, "italic"))

        # --- 第三栏：产物库 ---
        tk.Label(frame_lib, text="📦 产物管理库", font=("微软雅黑", 11, "bold"), bg="#f5f5f7").pack(anchor="w", pady=(5, 5), padx=5)
        f_search = tk.Frame(frame_lib, bg="#f5f5f7")
        f_search.pack(fill="x", pady=2, padx=5)
        tk.Label(f_search, text="🔍搜索:", bg="#f5f5f7").pack(side="left")
        ttk.Button(f_search, text="↕等级", command=self.toggle_sort).pack(side="right", padx=(2, 0))
        self.ent_search = ttk.Entry(f_search)
        self.ent_search.pack(side="left", fill="x", expand=True, padx=(2, 0))
        self.ent_search.bind("<KeyRelease>", lambda e: self.refresh_library()) 

        self.lb_library = tk.Listbox(frame_lib, font=("微软雅黑", 10), selectmode="browse")
        self.lb_library.pack(fill="both", expand=True, pady=5, padx=5)
        self.lb_library.bind("<Double-Button-1>", lambda e: self.set_as_target()) 
        self.lb_library.bind("<Button-3>", self.show_library_context_menu)

        self.menu_lib = tk.Menu(self.frame, tearoff=0)
        self.menu_lib.add_command(label="🎯 设为目标并计算", command=self.set_as_target)
        self.menu_lib.add_command(label="✏️ 编辑该配方", command=self.edit_selected_recipe)
        self.menu_lib.add_command(label="🔄 切换核采取状态", command=self.toggle_verify_status)
        self.menu_lib.add_command(label="🔍 查看可合成产物 (用途)", command=self.show_usages_for_library_item)
        self.menu_lib.add_separator()
        self.menu_lib.add_command(label="🗑️ 彻底删除", command=self.delete_selected_recipe)

        self.menu_bom = tk.Menu(self.frame, tearoff=0)
        self.menu_bom.add_command(label="🎯 设为目标并计算", command=lambda: self._set_target_internal(self.bom_right_clicked_item))
        self.menu_bom.add_command(label="✏️ 编辑该配方", command=lambda: self.open_recipe_editor(self.bom_right_clicked_item))
        # 🌟 新增选项：设置该物品当前的已有库存数量！
        self.menu_bom.add_command(label="📦 设置已有库存数量", command=lambda: self.set_inventory_for_item(self.bom_right_clicked_item))
        self.menu_bom.add_command(label="🔄 切换核对状态", command=self._toggle_bom_verify)
        self.menu_bom.add_command(label="🔍 查看可合成产物 (用途)", command=self.show_usages_for_bom_item)
        self.menu_bom.add_separator()
        self.menu_bom.add_command(label="🗑️ 彻底删除", command=self._delete_bom_item)

        f_btns1 = tk.Frame(frame_lib, bg="#f5f5f7")
        f_btns1.pack(fill="x", pady=5, padx=5)
        ttk.Button(f_btns1, text="➕ 新增基础产物", command=lambda: self.open_recipe_editor("")).pack(fill="x")

        self.refresh_library()

        self.tooltip_win = None
        self.tooltip_id = None
        self.hovered_item = None

        for w in (self.tv_guide, self.tv_route, self.lb_library):
            w.bind("<Motion>", self._on_mouse_motion)
            w.bind("<Leave>", self._on_mouse_leave)
# 🌟 新增：以下这一整块都是配合历史记录和新菜单的功能函数

    def _toggle_bom_verify(self):
        name = self.bom_right_clicked_item
        if name and name in self.dm.data.get("recipes", {}):
            current = self.dm.data["recipes"][name].get("verified", False)
            self.dm.data["recipes"][name]["verified"] = not current
            self.dm.save_data(); self.refresh_library(); self.generate_bom()

    def _delete_bom_item(self):
        name = self.bom_right_clicked_item
        if name and messagebox.askyesno("危险操作", f"确定删除产物【{name}】吗？"):
            del self.dm.data["recipes"][name]
            self.dm.save_data(); self.refresh_library(); self.generate_bom()

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
        
        # ⑤ 弹窗智能定位，增加防溢出屏幕检测
        mouse_x, mouse_y = self.app.winfo_pointerxy()
        win_w, win_h = 360, 480
        
        # 获取屏幕真实宽高
        screen_w = self.app.winfo_screenwidth()
        screen_h = self.app.winfo_screenheight()
        
        # 如果超出右边界，往左靠
        if mouse_x + win_w > screen_w:
            mouse_x = screen_w - win_w - 20
        # 如果超出下边界，往上靠（预留任务栏空间）
        if mouse_y + win_h > screen_h:
            mouse_y = screen_h - win_h - 60
            
        win.geometry(f"{win_w}x{win_h}+{mouse_x}+{mouse_y}")
        win.minsize(win_w, win_h)

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
        # 🌟 1. 彻底解除了 readonly 封印，允许随时修改名称
        # if default_name: ent_name.configure(state="readonly") 

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
            
            recipes = self.dm.data.setdefault("recipes", {})

            # ================= 🌟 2. 核心黑科技：全库连锁更名 =================
            if default_name and final_name != default_name:
                # 防撞车检测
                if final_name in recipes:
                    return messagebox.showwarning("冲突", f"已存在名为【{final_name}】的产物，请换个名字！", parent=win)
                
                # 危险操作确认
                if not messagebox.askyesno("更名确认", f"确定将【{default_name}】更名为【{final_name}】吗？\n\n程序将自动遍历所有配方，将旧材料名安全替换为新名称，防止生产链断裂！", parent=win):
                    return
                
                # 遍历全库所有配方，如果某配方的材料里用了旧名字，就替换成新名字
                for r_name, r_data in recipes.items():
                    mats = r_data.get("materials", {})
                    if default_name in mats:
                        qty = mats.pop(default_name)
                        mats[final_name] = qty # 数量原封不动继承过去
                        
                # 销毁旧字典键
                if default_name in recipes:
                    del recipes[default_name]
                    
                # 修正：如果当前正在显示旧名字的生产链，或者历史记录里有旧名字，一并改掉
                if self.var_target_product.get() == default_name:
                    self.var_target_product.set(final_name)
                self.history = [final_name if x == default_name else x for x in self.history]
            # ===============================================================

            # 保存本配方数据
            recipes[final_name] = {"verified": var_ver.get(), "materials": local_mats.copy()}
            self.dm.save_data()
            self.refresh_library()
            
            # 如果正处在计算分析该产物的状态，自动刷新分析图
            if self.var_target_product.get() == final_name or "未选择" not in self.var_target_product.get():
                self.generate_bom()
            win.destroy()

        ttk.Button(f_main, text="💾 保存配方并关闭", command=save_and_close).pack(fill="x", pady=3)
        refresh_local_list()
    def _calc_totals_and_consumers(self, item_name, qty, path_set, consumer=None):
        """核心算法 1：带有 MRP 净需求扣减的底层推演引擎"""
        if item_name in path_set: return 
        
        # ================= 🌟 MRP 核心：库存扣减 =================
        available = self.working_inv.get(item_name, 0)
        if available > 0:
            deduct = min(available, qty)
            self.working_inv[item_name] -= deduct
            qty -= deduct # 扣除可以直接从仓库拿货的数量
            
        # 如果从仓库里拿完之后，还需要合成的数量为 0，直接停止向下追溯！
        if qty <= 0: return 
        # =========================================================

        self.flat_totals[item_name] = self.flat_totals.get(item_name, 0) + qty
        
        if consumer:
            if item_name not in self.item_consumers:
                self.item_consumers[item_name] = set()
            self.item_consumers[item_name].add(consumer)

        recipes = self.dm.data.get("recipes", {})
        is_known = item_name in recipes
        if not is_known or not recipes[item_name].get("verified", False):
            self.unverified_items.add(item_name)
            
        if is_known:
            new_path = path_set.copy()
            new_path.add(item_name)
            for mat_name, u_qty in recipes[item_name].get("materials", {}).items():
                self._calc_totals_and_consumers(mat_name, qty * u_qty, new_path, consumer=item_name)
    def _get_bottom_up_level(self, item_name, recipes, memo=None, path=None):
        """核心算法 2：自底向上计算绝对阶段。原材=第1步，每往上一层+1步。"""
        if memo is None: memo = {}
        if path is None: path = set()

        if item_name in memo: return memo[item_name]
        if item_name in path: return 1 # 防死循环

        mats = recipes.get(item_name, {}).get("materials", {})
        if not mats:
            memo[item_name] = 1 # 底层原材绝对是第 1 步
            return 1

        path.add(item_name)
        max_child_lvl = 0
        for mat in mats:
            max_child_lvl = max(max_child_lvl, self._get_bottom_up_level(mat, recipes, memo, path))
        path.remove(item_name)

        memo[item_name] = max_child_lvl + 1
        return memo[item_name]

    def generate_bom(self):
        target = self.var_target_product.get().strip()
        qty_str = self.ent_target_qty.get().strip()
        
        if "请从右侧库中选择" in target or not target: return
        try: total_qty = float(qty_str)
        except: return messagebox.showerror("错误", "需求总数必须是纯数字！")

        # ================= 🌟 1. 视角冻结：记录刷新前的树状图状态 =================
        is_same_target = getattr(self, "last_rendered_target", "") == target
        is_update = bool(self.tv_guide.get_children()) and is_same_target
        
        guide_y, route_y, route_x = (0.0, 1.0), (0.0, 1.0), (0.0, 1.0)
        guide_expanded, route_expanded = set(), set()

        def get_node_path(tv, node):
            path = []
            curr = node
            while curr:
                vals = tv.item(curr, "values")
                path.append(vals[0] if vals else tv.item(curr, "text"))
                curr = tv.parent(curr)
            return tuple(reversed(path))

        if is_update:
            guide_y = self.tv_guide.yview()
            route_y = self.tv_route.yview()
            route_x = self.tv_route.xview()

            def capture_expanded(tv):
                expanded = set()
                def traverse(node):
                    if tv.item(node, "open"):
                        expanded.add(get_node_path(tv, node))
                    for child in tv.get_children(node):
                        traverse(child)
                for child in tv.get_children(""):
                    traverse(child)
                return expanded

            guide_expanded = capture_expanded(self.tv_guide)
            route_expanded = capture_expanded(self.tv_route)

        # 暴力清空两个独立的树
        self.tv_guide.delete(*self.tv_guide.get_children()) 
        self.tv_route.delete(*self.tv_route.get_children()) 

        self.flat_totals = {}
        self.item_consumers = {}
        self.unverified_items = set()
        
        # ================= 🌟 极简运算沙箱 =================
        # 移除了所有复杂的制造冲销算法，因为 temp_inventory 现在已经是净值了！
        self.working_inv = self.temp_inventory.copy()
        
        self._calc_totals_and_consumers(target, total_qty, set(), consumer=None)
        recipes = self.dm.data.get("recipes", {})

        self.level_memo = {}
        for item in self.flat_totals.keys():
            self._get_bottom_up_level(item, recipes, self.level_memo)

        max_level = self.level_memo.get(target, 1)

        steps_data = {i: [] for i in range(1, max_level + 1)}
        for item, qty in self.flat_totals.items():
            lvl = self.level_memo[item]
            steps_data[lvl].append((item, qty))

        # ================= 🌟 渲染指南树 =================
        # 恢复使用 temp_inventory 计算消耗
        used_inv = {k: self.temp_inventory[k] - self.working_inv[k] for k in self.temp_inventory if self.temp_inventory[k] > self.working_inv[k]}
        if used_inv:
            inv_node = self.tv_guide.insert("", "end", text="📦 直接调取已有库存 (免加工)", tags=("inventory",))
            for k, v in used_inv.items():
                v_fmt = int(v) if float(v).is_integer() else v
                self.tv_guide.insert(inv_node, "end", text=f" ▪ {k}   从库存拿 {v_fmt} 个", values=(k,), tags=("inventory",))
            if not is_update: self.tv_guide.item(inv_node, open=True)

        for lvl in range(1, max_level + 1):
            if not steps_data[lvl]: continue
            
            items_in_step = steps_data[lvl]
            items_in_step.sort(key=lambda x: x[0])

            if lvl == 1: step_title = "⛏️ 所有基础底层材料"
            elif lvl == max_level: step_title = f"👑 [第 {lvl-1} 步] 冲刺最终目标"
            else: step_title = f"⚙️ [第 {lvl-1} 步] 合成本级产物"

            node_step = self.tv_guide.insert("", "end", text=step_title, tags=("root_sum",))

            for item, qty in items_in_step:
                qty_fmt = int(qty) if qty.is_integer() else qty
                is_veri = item not in self.unverified_items
                status = "" if is_veri else " ❌[缺配方/底料]"
                tag = "verified" if is_veri else "unverified"

                usage_str = ""
                consumers = self.item_consumers.get(item, set())
                if consumers:
                    c_levels = sorted(list(set(self.level_memo[c] for c in consumers)))
                    distant_uses = [c for c in c_levels if c > lvl + 1]
                    if distant_uses:
                        step_numbers = [c - 1 for c in c_levels]
                        levels_fmt = ", ".join(map(str, step_numbers))
                        usage_str = f"   ➡️ 存入仓库 (将于第 {levels_fmt} 步使用)"

                # 应用单数字版的极简库存标签
                inv_mark = self.get_inv_mark(item)
                self.tv_guide.insert(node_step, "end", text=f" ▪ {item}{inv_mark}   加工 x {qty_fmt}   {status}{usage_str}", values=(item,), tags=(tag,))
            
            if not is_update: self.tv_guide.item(node_step, open=True)

        # ================= 🌟 渲染路线树 =================
        # 恢复使用 temp_inventory 传给路线图沙箱
        self.route_working_inv = self.temp_inventory.copy()
        self.insert_bom_node("", target, total_qty, set())

        # ================= 🌟 2. 视角恢复：无缝衔接刚才的视野 =================
        if is_update:
            def restore_expanded(tv, expanded_set):
                def traverse(node):
                    path_sig = get_node_path(tv, node)
                    if path_sig in expanded_set:
                        tv.item(node, open=True)
                    else:
                        tv.item(node, open=False)
                    for child in tv.get_children(node):
                        traverse(child)
                for child in tv.get_children(""):
                    traverse(child)

            restore_expanded(self.tv_guide, guide_expanded)
            restore_expanded(self.tv_route, route_expanded)

            self.app.after(10, lambda: self.tv_guide.yview_moveto(guide_y[0]))
            self.app.after(10, lambda: self.tv_route.yview_moveto(route_y[0]))
            self.app.after(10, lambda: self.tv_route.xview_moveto(route_x[0]))
            
        self.last_rendered_target = target
    def insert_bom_node(self, parent_id, item_name, required_qty, path_set):
        recipes = self.dm.data.get("recipes", {})
        req_fmt = int(required_qty) if required_qty.is_integer() else required_qty
        
        # ================= 🌟 路线图专属库存推演 =================
        available = self.route_working_inv.get(item_name, 0)
        deduct = min(available, required_qty)
        if deduct > 0:
            self.route_working_inv[item_name] -= deduct
        net_qty = required_qty - deduct # 需要实际合成的数量
        # ========================================================
        
        if item_name in path_set:
            self.tv_route.insert(parent_id, "end", text=f"⚠️ {item_name}   x {req_fmt}   (循环嵌套异常)", values=(item_name,), tags=("unverified",))
            return

        is_known = item_name in recipes
        is_verified = is_known and recipes[item_name].get("verified", False)
        
        # 🌟 智能动态文本：应用冲销标签
        if net_qty <= 0:
            status_text = f"  [📦库存直接满足(消耗{int(deduct) if deduct.is_integer() else deduct})]"
            tag = "inventory"
        else:
            status_text = "" if is_verified else "  [❌未核对]"
            if deduct > 0:
                ded_fmt = int(deduct) if deduct.is_integer() else deduct
                status_text += f"  [📦本节点抵扣 {ded_fmt}]"
            tag = "verified" if is_verified else "unverified"
        
        # 应用智能库存标签
        inv_mark = self.get_inv_mark(item_name)
        
        display_text = f"└─ {item_name}{inv_mark}   x {req_fmt}{status_text}"
        node_id = self.tv_route.insert(parent_id, "end", text=display_text, values=(item_name,), tags=(tag,))
        
        # 🌟 只有真实存在净需求（且有配方）时，才往下显示树枝
        if is_known and net_qty > 0:
            new_path = path_set.copy()
            new_path.add(item_name)
            for mat_name, unit_qty in recipes[item_name].get("materials", {}).items():
                self.insert_bom_node(node_id, mat_name, net_qty * unit_qty, new_path)
                
        # 如果这个节点完全被库存满足，那底下的材料都不用看了，自动把它收起！
        self.tv_route.item(node_id, open=(net_qty > 0))
    # =======================================================
    #               🌟 悬浮提示窗 (Tooltip) 引擎 🌟
    # =======================================================
    def _on_mouse_leave(self, event):
        """鼠标离开组件时，立刻销毁提示窗"""
        self._hide_tooltip()
        self.hovered_item = None
        if self.tooltip_id:
            self.frame.after_cancel(self.tooltip_id)
            self.tooltip_id = None

    def _on_mouse_motion(self, event):
        """鼠标移动时，探测下方是哪个物品"""
        widget = event.widget
        item_name = None

        # 探测树状图 (行动指南 & 路线图)
        if isinstance(widget, ttk.Treeview):
            row_id = widget.identify_row(event.y)
            if row_id:
                vals = widget.item(row_id, "values")
                if vals: item_name = vals[0]
                
        # 探测列表框 (产物库)
        elif isinstance(widget, tk.Listbox):
            index = widget.nearest(event.y)
            bbox = widget.bbox(index)
            # 确保鼠标真的在文字上，而不是在列表下方的空白处
            if bbox and bbox[1] <= event.y <= bbox[1] + bbox[3]:
                raw_text = widget.get(index)
                # 剥离可能存在的等级前缀 (如 "③ 铜锭")，精准提取产物名
                clean_text = raw_text.split("  (")[0].strip()
                parts = clean_text.split(maxsplit=1)
                item_name = parts[1].strip() if len(parts) == 2 else clean_text

        # 如果鼠标换了目标，重置计时器
        if item_name != self.hovered_item:
            self.hovered_item = item_name
            self._hide_tooltip()
            if self.tooltip_id:
                self.frame.after_cancel(self.tooltip_id)
            
            if item_name:
                # 停留 400 毫秒后，弹出提示窗
                self.tooltip_id = self.frame.after(400, self._show_tooltip, event.x_root, event.y_root, item_name)

    def _hide_tooltip(self):
        """安全销毁提示窗"""
        if self.tooltip_win:
            self.tooltip_win.destroy()
            self.tooltip_win = None

    def _show_tooltip(self, x, y, item_name):
        """构建并显示精美的黄色悬浮小便签"""
        self._hide_tooltip()
        
        recipes = self.dm.data.get("recipes", {})
        if item_name not in recipes: return # 没录入的直接无视
            
        mats = recipes[item_name].get("materials", {})
        if not mats:
            text = f"📦 【{item_name}】\n底层原材 (无需机器合成)"
        else:
            lines = [f"🛠️ 【{item_name}】的配方:"]
            for m, q in mats.items():
                qty_fmt = int(q) if isinstance(q, float) and q.is_integer() else q
                lines.append(f" ▪ {m}  x {qty_fmt}")
            text = "\n".join(lines)

        # 创建一个无边框的顶层窗口
        self.tooltip_win = tk.Toplevel(self.frame)
        self.tooltip_win.wm_overrideredirect(True)
        # 将窗口定位在鼠标右下方一点点，避免挡住鼠标
        self.tooltip_win.wm_geometry(f"+{x+15}+{y+15}")
        self.tooltip_win.attributes("-topmost", True) # 强制置顶
        
        # 类似便利贴的样式
        tk.Label(
            self.tooltip_win, text=text, justify="left", 
            background="#ffffe0", foreground="#333", relief="solid", borderwidth=1, 
            font=("微软雅黑", 10), padx=8, pady=5
        ).pack()
    
    
    # 🌟 完全重写：分离右键与双击事件
    def on_right_click_tree(self, event):
        tv = event.widget # 获取当前点击的是哪个树 (tv_guide 还是 tv_route)
        item_id = tv.identify_row(event.y)
        if not item_id: return
        vals = tv.item(item_id, "values")
        if not vals: return 
        
        self.bom_right_clicked_item = vals[0]
        tv.selection_set(item_id) 
        self.menu_bom.tk_popup(event.x_root, event.y_root)

    def show_usages_for_library_item(self):
        name = self.get_selected_library_item()
        if name: self._show_usages_dialog(name)

    def show_usages_for_bom_item(self):
        name = self.bom_right_clicked_item
        if name: self._show_usages_dialog(name)
    def _show_usages_dialog(self, material_name):
        """反查引擎：遍历所有配方，找出谁用到了该材料"""
        usages = []
        recipes = self.dm.data.get("recipes", {})
        
        # 1. 扫描数据库
        for prod_name, data in recipes.items():
            mats = data.get("materials", {})
            if material_name in mats:
                usages.append((prod_name, mats[material_name]))
                
        # 2. 如果没找到，温柔提示
        if not usages:
            messagebox.showinfo("用途查询", f"【{material_name}】目前没有被任何产物作为配方材料使用。\n(它可能是一个最终级产物，或者其相关配方尚未录入)")
            return

        # 3. 如果找到了，构建精美的小弹窗
        win = tk.Toplevel(self.app)
        win.title(f"🔍 【{material_name}】的合成用途")
        
        mouse_x, mouse_y = self.app.winfo_pointerxy()
        win.geometry(f"300x350+{mouse_x}+{mouse_y}")
        win.transient(self.app)
        
        tk.Label(win, text=f"以下产物需要用到【{material_name}】:", font=("微软雅黑", 10, "bold")).pack(anchor="w", padx=15, pady=(15, 5))
        
        # 列表展示区
        lb = tk.Listbox(win, font=("微软雅黑", 10), selectmode="browse")
        lb.pack(fill="both", expand=True, padx=15, pady=5)
        
        # 填入数据，并自动附带产物等级
        for prod, qty in usages:
            qty_fmt = int(qty) if qty.is_integer() else qty
            level = self._calc_item_level(prod)
            lvl_str = chr(9311 + level) if 1 <= level <= 20 else f"[{level}]"
            lb.insert(tk.END, f"{lvl_str} {prod}  (单次需 {qty_fmt} 个)")
            
        # 🌟 绝杀交互：双击列表里的产物，直接跳转过去分析！
        def on_double_click(event):
            sel = lb.curselection()
            if sel:
                # 从形如 "③ 蛋糕 (单次需 2 个)" 的文本中精准剥离出名字 "蛋糕"
                raw_text = lb.get(sel[0])
                target_prod = raw_text.split("  (")[0][2:].strip() 
                
                self._set_target_internal(target_prod) # 调用历史记录引擎切换目标
                win.destroy() # 关闭小弹窗
                
        lb.bind("<Double-Button-1>", on_double_click)
        
        tk.Label(win, text="💡 提示: 双击列表中的产物可直接跳转分析", fg="#888", font=("微软雅黑", 9)).pack(pady=(0, 10))

        # ================= 🌟 MRP 辅助功能控制台 =================

    def toggle_route_tree(self, expand=True):
        """一键展开/收起整个路线图的节点"""
        def get_all_children(tree, item=""):
            children = tree.get_children(item)
            for child in children:
                children += get_all_children(tree, child)
            return children
        for item in get_all_children(self.tv_route):
            self.tv_route.item(item, open=expand)

    # ================= 🌟 历史快照辅助函数 (新增) =================
    # (可以把 save_current_state 整个删掉了，已经不再需要它了)

    def history_back(self):
        if self.history_idx > 0:
            self.history_idx -= 1
            self.var_target_product.set(self.history[self.history_idx])
            self.generate_bom()

    def history_forward(self):
        if self.history_idx < len(self.history) - 1:
            self.history_idx += 1
            self.var_target_product.set(self.history[self.history_idx])
            self.generate_bom()

    def _set_target_internal(self, name):
        """核心目标切换：只管导航，绝不清空全局仓库！"""
        if not name or "请从右侧库中选择" in name: return
        
        self.history = self.history[:self.history_idx + 1]
        if not self.history or self.history[-1] != name:
            self.history.append(name)
            self.history_idx += 1
            
        self.var_target_product.set(name)
        # 🌟 此处彻底删除了 self.temp_inventory = {}，保证仓库数据永不丢失
        self.generate_bom()

    def set_as_target(self):
        name = self.get_selected_library_item()
        if name:
            self._set_target_internal(name)

    # ================= 🌟 重构：神出鬼没的双击内联输入框 =================
    def on_double_click_tree(self, event):
        tv = event.widget
        item_id = tv.identify_row(event.y)
        if not item_id: return "break"
        
        vals = tv.item(item_id, "values")
        if not vals: return "break"
        
        # 呼唤精美的双轨库存设置窗
        self.open_inventory_popup(event.x_root, event.y_root, vals[0])
        return "break"
    # ================= 🌟 终极版 MRP 库存管理 =================
    def clear_inventory(self):
        """清空所有库存并保存"""
        if not self.temp_inventory: return
        self.temp_inventory.clear()
        self.dm.save_data() # 🌟 立即持久化存盘
        self.generate_bom()

    def set_inventory_for_item(self, item_name):
        """通过右键菜单调用弹窗"""
        x, y = self.app.winfo_pointerxy()
        self.open_inventory_popup(x, y, item_name)

    def get_inv_mark(self, item_name):
        """生成极简库存标记"""
        if item_name not in self.temp_inventory: return ""
        val = self.temp_inventory[item_name]
        v_fmt = int(val) if float(val).is_integer() else val
        return f" 📦[库存:{v_fmt}]"

    def open_inventory_popup(self, event_x, event_y, item_name):
        """🌟 悬浮双轨输入法：事件结算型"""
        if hasattr(self, "_inv_popup") and self._inv_popup and self._inv_popup.winfo_exists():
            self._inv_popup.destroy()
            
        win_edit = tk.Toplevel(self.app)
        self._inv_popup = win_edit
        win_edit.wm_overrideredirect(True)
        win_edit.geometry(f"+{event_x + 10}+{event_y + 10}")
        win_edit.attributes("-topmost", True)
        win_edit.configure(bg="#f8f9fa", bd=1, relief="solid", padx=8, pady=8)
        
        tk.Label(win_edit, text="当前库存:", bg="#f8f9fa", font=("微软雅黑", 9)).grid(row=0, column=0, sticky="e", pady=2)
        ent_base = ttk.Entry(win_edit, width=8, justify="center")
        ent_base.grid(row=0, column=1, pady=2, padx=5)
        
        tk.Label(win_edit, text="制造/拆解(增减量):", bg="#f8f9fa", font=("微软雅黑", 9)).grid(row=1, column=0, sticky="e", pady=2)
        ent_craft = ttk.Entry(win_edit, width=8, justify="center")
        ent_craft.grid(row=1, column=1, pady=2, padx=5)
        
        recipes = self.dm.data.get("recipes", {})
        is_craftable = item_name in recipes and len(recipes[item_name].get("materials", {})) > 0
        
        if not is_craftable:
            ent_craft.insert(0, "-")
            ent_craft.configure(state="disabled")
        
        # 只回显绝对库存量，增减量永远为空（等待当次输入）
        curr_inv = self.temp_inventory.get(item_name, 0.0)
        if curr_inv > 0: 
            ent_base.insert(0, str(int(curr_inv) if float(curr_inv).is_integer() else curr_inv))
        
        ent_base.focus()
        ent_base.select_range(0, tk.END)
        
        def commit(e=None):
            if getattr(win_edit, "_committed", False): return
            win_edit._committed = True
            
            try:
                b_str = ent_base.get().strip()
                c_str = ent_craft.get().strip()
                
                b_val = float(b_str) if b_str else None
                c_val = float(c_str) if c_str and is_craftable else 0.0
                
                changed = False
                
                # 1. 绝对库存修改覆盖
                if b_val is not None and b_val != curr_inv:
                    self.temp_inventory[item_name] = b_val
                    changed = True
                    
                # 2. 制造/拆解事件结算 (连带扣减底料)
                if c_val != 0.0:
                    current_base = self.temp_inventory.get(item_name, 0.0)
                    # 产物自身增加或减少
                    self.temp_inventory[item_name] = max(0.0, current_base + c_val)
                    
                    # 底料按比例扣除(c_val为正)或退还(c_val为负)
                    mats = recipes[item_name].get("materials", {})
                    for mat, mat_qty in mats.items():
                        mat_curr = self.temp_inventory.get(mat, 0.0)
                        # 如果合成，减去材料；如果输入负数(拆解)，负负得正，增加材料
                        new_mat_val = mat_curr - (c_val * mat_qty)
                        self.temp_inventory[mat] = max(0.0, new_mat_val)
                        
                    changed = True
                
                # 清理掉库存为 0 的垃圾数据
                keys_to_del = [k for k, v in self.temp_inventory.items() if v <= 0]
                for k in keys_to_del: del self.temp_inventory[k]
                
                if changed:
                    self.dm.save_data() # 🌟 库存一变，立刻写进硬盘！
                    self.generate_bom()
            except ValueError: pass
            
            win_edit.destroy()

        def cancel(e=None):
            win_edit._committed = True
            win_edit.destroy()

        win_edit.bind("<Return>", commit)
        win_edit.bind("<Escape>", cancel)
        
        def close_if_lost_focus(e=None):
            if getattr(win_edit, "_committed", False): return
            focused = win_edit.focus_get()
            if focused is None or focused.winfo_toplevel() != win_edit:
                commit()
                
        win_edit.bind("<FocusOut>", lambda e: win_edit.after(100, close_if_lost_focus))