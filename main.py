
import ctypes
import sys
from tkinter import messagebox
import tkinter as tk
import tkinter as tk
from tkinter import ttk
from data_manager import DataManager
from ui_tabs import ReportTab, DatabaseTab, SettingsTab, FertilizerTab, CompareTab, ProductionTab

def check_single_instance():
    """检查程序是否已经运行，防止多开"""
    # 这个名字必须是唯一的，你可以随便起，只要不跟别人的软件重名就行
    mutex_name = "StarSandBuddy_Global_Mutex_Lock_v1"
    
    # 调用 Windows 底层 API 创建一个互斥锁
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
    
    # 183 代表 ERROR_ALREADY_EXISTS，说明这把锁已经被前一个打开的程序占用了
    if ctypes.windll.kernel32.GetLastError() == 183:
        # 弹出一个警告框，告诉玩家已经在运行了
        root = tk.Tk()
        root.withdraw() # 隐藏多余的空白主窗口
        root.attributes("-topmost", True) # 确保弹窗在最顶层
        messagebox.showwarning("提示", "【星砂岛小助手】已经在运行中啦，请在任务栏找找看，不要重复打开哦！")
        root.destroy()
        sys.exit(0) # 强制关闭当前这个多余的进程
        
    return mutex # ⚠️ 极其重要：必须把这个锁 return 出去并保持引用，否则 Python 的垃圾回收机制会把它当垃圾清掉，锁就失效了！


class FarmManagerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("星砂岛小助手 V1.2")
        self.geometry("1400x850")
        
        # 1. 启动数据大脑
        self.data_manager = DataManager()
        
        # 2. 基础 UI 设置
        self.setup_styles()
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill='both', expand=True, padx=8, pady=8)

        # 3. 创建空白的标签页 Frame
        tab_frames = {}
        tabs_info = [
            ("report", " 📊 收益分析报表 "), ("compare", " ⚖️ 施肥效益对比 "),
            ("db", " 💾 核心数据库 "), ("settings", " ⚙️ 参数设置 "), ("fert", " 🧪 肥料实验室 "),
            ("production", " 🏭 生产链与物料规划 ") # 🌟 新增这一行
        ]
        for key, title in tabs_info:
            frame = ttk.Frame(self.notebook)
            self.notebook.add(frame, text=title)
            tab_frames[key] = frame

        # 4. 把具体的 UI 逻辑挂载到空白 Frame 上 (组件实例化)
        self.report_tab = ReportTab(tab_frames["report"], self, self.data_manager)
        self.compare_tab = CompareTab(tab_frames["compare"], self, self.data_manager)
        self.db_tab = DatabaseTab(tab_frames["db"], self, self.data_manager)
        self.settings_tab = SettingsTab(tab_frames["settings"], self, self.data_manager)
        self.fert_tab = FertilizerTab(tab_frames["fert"], self, self.data_manager)

        # 挂载生产链页面
        self.production_tab = ProductionTab(tab_frames["production"], self, self.data_manager)
    def setup_styles(self):
        style = ttk.Style(); style.theme_use("clam")
        style.configure("TNotebook", background="#f5f5f7")
        style.configure("TNotebook.Tab", padding=[18, 6], font=("微软雅黑", 10))
        style.configure("TButton", font=("微软雅黑", 9))
        style.map("TEntry", fieldbackground=[("disabled", "#e0e0e0")])
        style.map("TCombobox", fieldbackground=[("disabled", "#e0e0e0")])
        # 🌟 新增这两行，调整所有树状图的默认字体和行高
        style.configure("Treeview", font=("微软雅黑", 10), rowheight=26, indent=45) 
        style.configure("Treeview.Heading", font=("微软雅黑", 10, "bold")) # 表头字体

    def refresh_all(self):
        """全局刷新枢纽：当某一个子页面改了数据，调用这个通知大家一起刷新"""
        self.report_tab.refresh_list(keep_widths=True)
        self.db_tab.refresh_db()
        self.fert_tab.refresh_fert_list()
        self.compare_tab.refresh_cmp_ferts()
        self.compare_tab.refresh_cmp_crops()
        
        if hasattr(self, 'settings_tab'):
            self.settings_tab.refresh_settings_ui()
    def reload_from_db(self):
        """从硬盘执行全量强制刷新"""
        self.data_manager.debug_print("[DEBUG] 🔄 正在执行系统全量刷新...")
        
        # 直接加载，不再手动备份内存中的列宽，以硬盘存档为准
        self.data_manager.load_data()
        
        # 重置排序状态
        self.report_tab.current_sort_col = None
        self.report_tab.current_sort_reverse = False
        
        # 触发所有 UI 页面的重新绘制
        self.refresh_all()
        

    def open_debug_window(self):
        w = tk.Toplevel(self); w.title("🐛 开发者调试控制台"); w.geometry("700x500")
        top_f = ttk.Frame(w); top_f.pack(fill='x', padx=10, pady=5)
        ttk.Button(top_f, text="🔄 刷新日志", command=lambda: txt.delete(1.0, tk.END) or txt.insert(tk.END, "\n".join(self.data_manager.debug_logs)) or txt.see(tk.END)).pack(side='left', padx=5)
        ttk.Button(top_f, text="🛠️ 按标准预设重排", command=lambda: [self.data_manager.fix_custom_db_order(), self.reload_from_db()]).pack(side='right', padx=5)
        txt = tk.Text(w, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4"); txt.pack(fill='both', expand=True, padx=10, pady=5)
        txt.insert(tk.END, "\n".join(self.data_manager.debug_logs)); txt.see(tk.END)

if __name__ == "__main__":
    app_mutex = check_single_instance()
    app = FarmManagerApp()
    app.mainloop()