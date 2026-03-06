import tkinter as tk
from tkinter import ttk, messagebox
import config
from logic import calc_profits

def set_popup_geo(win, w, h):
    mx = win.winfo_pointerx()
    my = win.winfo_pointery()
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    x = min(mx + 10, sw - w - 10)
    y = min(my + 10, sh - h - 10)
    win.geometry(f"{w}x{h}+{x}+{y}")

class CropEditor:
    def __init__(self, app, crop_name=None):
        self.app = app
        self.is_new = crop_name is None
        self.crop_name = crop_name
        self.win = tk.Toplevel(app)
        self.win.grab_set()
        self.win.title(f"编辑: {crop_name}" if crop_name else "添加新作物")
        set_popup_geo(self.win, 600, 650)
        self.ents = self.create_form(self.win)
        if not self.is_new:
            c = next((x for x in self.app.data["crops"] if str(x["name"]) == str(crop_name)), None)
            if c: self.fill_form(c)
        ttk.Button(self.win, text="💾 保存", command=self.on_save).pack(pady=10)

    def create_form(self, p):
        ents = {}
        tf = ttk.Frame(p); tf.pack(fill='x', padx=10, pady=5)
        ents['is_tree'] = tk.BooleanVar(); ents['verified'] = tk.BooleanVar()
        def tog():
            is_t = ents['is_tree'].get()
            if is_t:
                ents['f_t1'].grid_remove(); ents['f_t3'].grid_remove(); ents['f_hc'].grid_remove()
                ents['lbl_t2'].config(text="复果时间(h)", foreground="red")
            else:
                ents['f_t1'].grid(); ents['f_t3'].grid(); ents['f_hc'].grid()
                ents['lbl_t2'].config(text="二轮时间(h)", foreground="black")
        ttk.Radiobutton(tf, text="普通作物", variable=ents['is_tree'], value=False, command=tog).pack(side='left')
        ttk.Radiobutton(tf, text="果树", variable=ents['is_tree'], value=True, command=tog).pack(side='left', padx=10)
        ttk.Checkbutton(tf, text="✅ 数据已核对无误", variable=ents['verified']).pack(side='right')
        bf = ttk.LabelFrame(p, text="基础数据"); bf.pack(fill='x', padx=10)
        def add_field(k, l, r, c):
            f = ttk.Frame(bf); f.grid(row=r, column=c, padx=5, pady=5, sticky='w')
            if k == 't2': ents['lbl_t2'] = ttk.Label(f, text=l)
            else: ttk.Label(f, text=l).pack(side='left')
            if k == 't2': ents['lbl_t2'].pack(side='left')
            e = ttk.Entry(f, width=8); e.pack(side='left')
            ents[k] = e
            if k == 't1': ents['f_t1'] = f
            if k == 't3': ents['f_t3'] = f
            if k == 'h_count': ents['f_hc'] = f
        add_field("name", "名称", 0, 0); add_field("seed_price", "种子价", 0, 1)
        add_field("h_count", "次数", 0, 2); add_field("h_qty", "产量", 0, 3)
        add_field("t1", "一轮", 1, 0); add_field("t2", "二轮", 1, 1)
        add_field("t3", "三轮", 1, 2); add_field("raw_price", "直售价", 1, 3)
        pf = ttk.LabelFrame(p, text="加工设置"); pf.pack(fill='x', padx=10, pady=5)
        ttk.Label(pf, text="一级产物:").grid(row=0, column=0)
        ents['primary_type'] = ttk.Combobox(pf, values=["无", "面粉", "果肉", "蔬菜汁", "糖"], state="readonly", width=8)
        ents['primary_type'].grid(row=0, column=1); ents['primary_type'].current(0)
        ttk.Label(pf, text="数量:").grid(row=0, column=2)
        ents['primary_qty'] = ttk.Entry(pf, width=5); ents['primary_qty'].grid(row=0, column=3)
        
        # 👇 新增：一级产物下拉框联动逻辑 👇
        def sync_primary(*args):
            if ents['primary_type'].get() == "无":
                ents['primary_qty'].config(state='normal') # 先恢复正常才能清空
                ents['primary_qty'].delete(0, 'end')
                ents['primary_qty'].config(state='disabled')
            else:
                ents['primary_qty'].config(state='normal')
        ents['primary_type'].bind("<<ComboboxSelected>>", sync_primary)
        ents['sync_primary'] = sync_primary # 保存起来供后续回填时调用
        sync_primary() # 初始化调用
        # 👆 新增结束 👆

        # 👇 优化：果酱和腌菜的置灰与清空逻辑 👇
        def mk_chk(r, k_can, k_p, k_t, txt):
            ents[k_can] = tk.BooleanVar()
            def chk(): 
                s = 'normal' if ents[k_can].get() else 'disabled'
                ents[k_p].config(state='normal'); ents[k_t].config(state='normal')
                if s == 'disabled': # 如果取消勾选，清空里面残留的数字
                    ents[k_p].delete(0, 'end'); ents[k_t].delete(0, 'end')
                ents[k_p].config(state=s); ents[k_t].config(state=s)
                
            ttk.Checkbutton(pf, text=txt, variable=ents[k_can], command=chk).grid(row=r, column=0)
            ttk.Label(pf, text="价格:").grid(row=r, column=2); ents[k_p]=ttk.Entry(pf, width=5); ents[k_p].grid(row=r, column=3)
            ttk.Label(pf, text="耗时:").grid(row=r, column=4); ents[k_t]=ttk.Entry(pf, width=5); ents[k_t].grid(row=r, column=5)
            chk()
        mk_chk(1, 'can_jam', 'jam_price', 'jam_time', '果酱')
        mk_chk(2, 'can_pickle', 'pickle_price', 'pickle_time', '腌菜')
        ents['toggle_fn'] = tog; tog()
        return ents

    def fill_form(self, c):
        keys = ['name','seed_price','h_count','h_qty','t1','t2','t3','raw_price','primary_qty','jam_price','jam_time','pickle_price','pickle_time']
        for k in keys:
            if k in self.ents:
                self.ents[k].config(state='normal')
                self.ents[k].delete(0, tk.END)
                self.ents[k].insert(0, str(c.get(k,"")))
        self.ents['is_tree'].set(c.get('is_tree', False))
        self.ents['verified'].set(c.get('verified', False))
        self.ents['can_jam'].set(c.get('can_jam', False))
        self.ents['can_pickle'].set(c.get('can_pickle', False))
        self.ents['primary_type'].set(c.get('primary_type', "无"))
        self.ents['toggle_fn']()
        
        # 触发下拉框联动以更新“数量”框的置灰状态
        self.ents['sync_primary']()
        
        # 修正果酱/腌菜回填时的置灰状态
        def fix_state(chk_val, p_key, t_key):
            if not chk_val:
                self.ents[p_key].config(state='normal'); self.ents[t_key].config(state='normal')
                self.ents[p_key].delete(0, 'end'); self.ents[t_key].delete(0, 'end')
                self.ents[p_key].config(state='disabled'); self.ents[t_key].config(state='disabled')
            else:
                self.ents[p_key].config(state='normal'); self.ents[t_key].config(state='normal')
                
        fix_state(c.get('can_jam'), 'jam_price', 'jam_time')
        fix_state(c.get('can_pickle'), 'pickle_price', 'pickle_time')

    def on_save(self):
        d = {}
        for k, v in self.ents.items():
            if isinstance(v, ttk.Entry): d[k]=v.get()
            elif isinstance(v, tk.BooleanVar): d[k]=v.get()
            elif isinstance(v, ttk.Combobox): d[k]=v.get()
        if not d.get('name'): return
        crops = self.app.data["crops"]
        idx = -1
        if not self.is_new:
            idx = next((i for i,c in enumerate(crops) if c["name"]==self.crop_name), -1)
            old_data = crops[idx]
            diffs = []
            for k, v in d.items():
                if str(v) != str(old_data.get(k, "")):
                    diffs.append(f"{k}: {old_data.get(k)} -> {v}")
            if diffs:
                if not messagebox.askokcancel("确认", "确认变更？\n" + "\n".join(diffs[:8])): return
        else:
            exist = next((c for c in crops if c["name"]==d['name']), None)
            if exist:
                if not messagebox.askyesno("覆盖", "作物已存在，覆盖吗？"): return
                idx = crops.index(exist)
        if idx != -1: crops[idx] = d
        else: crops.append(d)
        self.app.save_data(); self.app.refresh_all(); self.win.destroy()

class ColumnManager:
    def __init__(self, app):
        self.app = app
        self.win = tk.Toplevel(app)
        self.win.title("列管理")
        set_popup_geo(self.win, 500, 400)
        lb1 = tk.Listbox(self.win); lb1.pack(side='left', fill='both', expand=True)
        lb2 = tk.Listbox(self.win); lb2.pack(side='right', fill='both', expand=True)
        all_children = set()
        for kids in config.COLUMN_GROUPS.values():
            all_children.update(kids)
        curr = [c for c in app.data["display_columns"] if c in config.ALL_COLS]
        for c in curr:
            if c not in all_children: lb2.insert(tk.END, config.ALL_COLS[c])
        for c in config.ALL_COLS:
            if c not in curr and c != "name":
                if c not in all_children: lb1.insert(tk.END, config.ALL_COLS[c])
        def mv(s, d):
            i = s.curselection()
            if i: v=s.get(i); s.delete(i); d.insert(tk.END, v)
        btn = ttk.Frame(self.win); btn.pack(side='left')
        ttk.Button(btn, text=">>", command=lambda:mv(lb1,lb2)).pack()
        ttk.Button(btn, text="<<", command=lambda:mv(lb2,lb1)).pack()
        def save():
            rev = {v:k for k,v in config.ALL_COLS.items()}
            res = [rev[lb2.get(i)] for i in range(lb2.size())]
            if "name" not in res: res.insert(0, "name")
            app.data["display_columns"] = res
            app.save_data(); app.refresh_all(); self.win.destroy()
        ttk.Button(btn, text="保存", command=save).pack()

class FormulaViewer:
    @staticmethod
    def show(parent, crop_name, strategy, app):
        c = next((x for x in app.data["crops"] if str(x["name"])==crop_name), None)
        if not c: return
        _, F = calc_profits(c, app.data["settings"])
        if strategy in F: FormulaViewer.render(parent, crop_name, strategy, F[strategy])

    @staticmethod
    def render(parent, n, s, d):
        w = tk.Toplevel(parent); w.title(f"计算详情: {n}")
        set_popup_geo(w, 800, 550); w.configure(bg="#f5f5f7")
        main_frame = tk.Frame(w, bg="#ffffff", padx=20, pady=20)
        main_frame.pack(expand=True, fill="both", padx=15, pady=15)
        tk.Label(main_frame, text=f"{n} - {s}", font=("微软雅黑", 16, "bold"), bg="white", fg="#333").pack(pady=(0, 20))
        def create_section(parent, title, logic_text, val_text, color_logic="#666", color_val="#0055aa"):
            f = tk.Frame(parent, bg="white"); f.pack(fill="x", pady=5)
            tk.Label(f, text=title, font=("微软雅黑", 10, "bold"), bg="white", fg="#888", anchor="w").pack(fill="x")
            tk.Label(f, text=logic_text, font=("微软雅黑", 11), bg="white", fg=color_logic, anchor="w", wraplength=700, justify="left").pack(fill="x", pady=2)
            tk.Label(f, text=val_text, font=("Consolas", 12, "bold"), bg="#f0f8ff", fg=color_val, anchor="w", padx=5, pady=3).pack(fill="x")
        create_section(main_frame, f"【分子】 {d['title_n']}", d['str_n'], d['val_n'], "#e67e22", "#d35400")
        div_frame = tk.Frame(main_frame, height=2, bg="#333"); div_frame.pack(fill="x", pady=15)
        create_section(main_frame, f"【分母】 {d['title_d']}", d['str_d'], d['val_d'], "#27ae60", "#2ecc71")
        res_frame = tk.Frame(main_frame, bg="white", pady=20); res_frame.pack(fill="x")
        tk.Label(res_frame, text="=", font=("Arial", 24), bg="white", fg="#999").pack(side="left", padx=10)
        tk.Label(res_frame, text=f"{d['res']:.2f}", font=("Arial", 28, "bold"), bg="white", fg="#e74c3c").pack(side="left")
        tk.Label(res_frame, text="金币/小时", font=("微软雅黑", 14, "bold"), bg="white", fg="#555").pack(side="left", padx=10)