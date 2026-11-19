# customtkinter 完全手册

## 1. 初始化

```python
import customtkinter as ctk

# === 主题（必须放在最前面）===
ctk.set_appearance_mode(mode)     # "dark" 暗色 | "light" 亮色 | "system" 跟随系统
ctk.set_default_color_theme(t)    # "blue" | "green" | "dark-blue"

# === 创建窗口 ===
app = ctk.CTk()
app.title(str)                    # 窗口标题
app.geometry("宽x高")            # 如 "800x600"
app.minsize(w, h)                # 最小尺寸
app.resizable(bool, bool)        # 宽可否拖, 高可否拖

app.mainloop()                   # 进入消息循环（阻塞）
```

### 窗口属性

```python
app.withdraw()                    # 隐藏窗口（缩到托盘）
app.deiconify()                   # 恢复显示
app.lift()                        # 置顶
app.destroy()                     # 销毁窗口
app.iconbitmap("icon.ico")        # 设置图标(.ico文件)
app.protocol("WM_DELETE_WINDOW", fn)  # 点X时调用fn
app.after(ms, fn)                # 延迟ms毫秒调用fn
app.attributes("-topmost", True)  # 窗口置顶
app.winfo_children()             # 获取所有子控件列表
```

---

## 2. 颜色规则

```python
# 主题色自适应：用元组 (浅色值, 暗色值)
fg_color=("gray90", "gray17")    # 浅色=亮 暗色=深
text_color=("gray10", "gray90")  # 浅色=黑 暗色=白
hover_color=("gray70", "gray30") # hover效果
border_color=("gray50", "gray50")

# 固定颜色（不跟主题变）
fg_color="blue"
fg_color="#ff0000"
fg_color="transparent"           # 透明
```

---

## 3. CTkButton 按钮

```python
btn = ctk.CTkButton(master, **kw)

# === 参数 ===
text=str                          # 按钮文字（支持\n换行）
command=fn                        # 点击回调（无参数）
width=int                         # 宽度(px)
height=int                        # 高度(px)
corner_radius=int                 # 圆角半径
fg_color=str|tuple               # 背景色
hover_color=str|tuple            # 悬浮色
text_color=str|tuple             # 文字颜色
font=ctk.CTkFont(...)            # 字体
state="normal"|"disabled"        # 状态
anchor="w"|"center"|"e"          # 文字对齐
image=ctk.CTkImage(...)          # 图标
compound="left"|"right"|"top"    # 图标位置
border_width=int                  # 边框宽度
border_color=str|tuple           # 边框颜色

# === 方法 ===
btn.pack(...)                     # 布局
btn.configure(**kw)               # 修改属性
btn.cget("text")                  # 读取属性
btn.invoke()                      # 模拟点击
```

---

## 4. CTkLabel 标签

```python
lbl = ctk.CTkLabel(master, **kw)

# === 参数 ===
text=str
font=ctk.CTkFont(...)
text_color=str|tuple
anchor="w"|"center"|"e"          # 对齐
justify="left"|"center"|"right"   # 多行对齐
wraplength=int                    # 自动换行宽度
image=ctk.CTkImage(...)
compound=str                      # 图文位置

# === 方法 ===
lbl.configure(text="新文字")
lbl.configure(text_color="red")
```

---

## 5. CTkEntry 输入框

```python
var = ctk.StringVar(value="默认")
entry = ctk.CTkEntry(master, **kw)

# === 参数 ===
textvariable=var                  # 绑定变量
placeholder_text=str              # 占位文字
width=int
height=int
show="*"                          # 密码模式
state="normal"|"disabled"|"readonly"

# === 方法 ===
entry.get()                       # 读取内容
entry.delete(0, "end")            # 清空
entry.insert(0, "文字")           # 插入
var.get()                         # 从变量读
var.set("新值")                   # 设置变量
```

---

## 6. CTkTextbox 文本框（多行）

```python
box = ctk.CTkTextbox(master, **kw)

# === 参数 ===
width=int
height=int
wrap="word"|"char"|"none"        # 换行模式
font=ctk.CTkFont(...)
state="normal"|"disabled"         # disabled=只读

# === 方法 ===
box.insert("1.0", "内容")         # 第1行第0列插入
box.insert("end", "追加")         # 末尾追加
box.get("1.0", "end")             # 获取全部
box.delete("1.0", "end")          # 清空
box.see("end")                    # 滚动到底
box.configure(state="disabled")   # 设为只读
```

---

## 7. CTkCheckBox 复选框

```python
var = ctk.BooleanVar(value=True)
cb = ctk.CTkCheckBox(master, **kw)

# === 参数 ===
text=str
variable=var
onvalue=1|True                    # 选中值
offvalue=0|False                  # 未选中值
command=fn                        # 切换回调
checkbox_width=int                # 框大小
checkbox_height=int

# === 方法 ===
var.get()                         # True/False
cb.select()                       # 选中
cb.deselect()                     # 取消
cb.toggle()                       # 切换
```

---

## 8. CTkRadioButton 单选按钮

```python
var = ctk.StringVar(value="A")
rb = ctk.CTkRadioButton(master, **kw)

# === 参数 ===
text=str
variable=var                     # 同一组用同一个变量
value=any                         # 选中时变量的值
command=fn

# 示例：3选1
theme = ctk.StringVar(value="系统")
ctk.CTkRadioButton(root, text="🌙 暗色", variable=theme, value="dark").pack()
ctk.CTkRadioButton(root, text="☀ 亮色", variable=theme, value="light").pack()
ctk.CTkRadioButton(root, text="💻 跟随系统", variable=theme, value="system").pack()
print(theme.get())  # "dark" / "light" / "system"
```

---

## 9. CTkOptionMenu 下拉菜单

```python
var = ctk.StringVar(value="选项1")
menu = ctk.CTkOptionMenu(master, **kw)

# === 参数 ===
values=list                       # 选项列表
variable=var
command=fn                        # 选中回调(选中的值)
width=int
dynamic_resizing=True|False      # 自动调整宽度

# === 方法 ===
menu.set("选项2")                  # 设置当前值
var.get()                          # 读取
```

---

## 10. CTkProgressBar 进度条

```python
bar = ctk.CTkProgressBar(master, **kw)

# === 参数 ===
width=int
height=int
mode="determinate"|"indeterminate"  # 确定/不确定
progress_color=str|tuple
fg_color=str|tuple

# === 方法 ===
bar.set(0.0~1.0)                   # 设置进度
bar.get()                          # 读取进度
bar.start()                        # 不确定模式开始动画
bar.stop()                         # 停止动画
```

---

## 11. CTkSlider 滑块

```python
var = ctk.DoubleVar(value=50)
sld = ctk.CTkSlider(master, **kw)

# === 参数 ===
from_=int|float
to=int|float
variable=var
command=fn
number_of_steps=int               # 步数
```

---

## 12. CTkSwitch 开关

```python
var = ctk.BooleanVar(value=True)
sw = ctk.CTkSwitch(master, **kw)

# === 参数 ===
text=str
variable=var
command=fn
onvalue/offvalue
```

---

## 13. CTkFrame 容器

```python
f = ctk.CTkFrame(master, **kw)

# === 参数 ===
fg_color=str|tuple                # 背景色
corner_radius=int                 # 圆角
border_width=int                  # 边框
border_color=str|tuple

# 子控件放里面
btn = ctk.CTkButton(f, text="按钮")
btn.pack()

# 阻止Frame缩小
f.pack_propagate(False)

# 清空Frame内所有子控件
for w in f.winfo_children():
    w.destroy()
```

---

## 14. CTkScrollableFrame 可滚动容器

```python
sf = ctk.CTkScrollableFrame(master, **kw)
# 参数同CTkFrame
# 内容太多时自动出现滚动条
```

---

## 15. CTkToplevel 子窗口

```python
win = ctk.CTkToplevel(master)
win.title("子窗口")
win.geometry("400x300")
win.attributes("-topmost", True)   # 置顶

# ⚠ 关闭必须用after延迟！
btn = ctk.CTkButton(win, text="关闭",
    command=lambda: win.after(10, win.destroy))
```

---

## 16. CTkMessagebox 消息框（需安装 CTkMessagebox）

```python
from CTkMessagebox import CTkMessagebox

# === 消息框 ===
CTkMessagebox(title="标题", message="内容", icon="info")
# icon: "info" | "check" | "warning" | "cancel" | "question"

# === 选择框 ===
result = CTkMessagebox(title="确认？", message="确定删除？",
                        icon="question",
                        option_1="是", option_2="否", option_3="取消")
choice = result.get()  # "是"/"否"/"取消"
```

---

## 17. CTkFont 字体

```python
font = ctk.CTkFont(family="Arial", size=12, weight="normal")
# family: "Microsoft YaHei"|"SimSun"|"Consolas"|"Arial"|...
# weight: "normal"|"bold"
# size: 字号
```

---

## 18. CTkImage 图片

```python
from PIL import Image
img = ctk.CTkImage(light_image=Image.open("light.png"),
                    dark_image=Image.open("dark.png"),
                    size=(32, 32))
# 用于按钮/标签的图标
```

---

## 19. 布局（pack）

```python
widget.pack(
    side="top"|"left"|"right"|"bottom",  # 方向
    fill="x"|"y"|"both"|"none",          # 填充
    expand=True|False,                     # 扩展
    padx=int, pady=int,                   # 外边距
    ipadx=int, ipady=int,                 # 内边距
    anchor="n"|"s"|"e"|"w"|"center",     # 锚点
    before=other_widget,                   # 放在某控件前面
    after=other_widget,                    # 放在某控件后面
)
```

---

## 20. 线程安全

```python
# ❌ 不能在子线程直接改UI！
# threading.Thread 里这样写会炸：
# label.configure(text="xxx")

# ✅ 用 after() 回到主线程：
ui_root.after(0, lambda: label.configure(text="xxx"))

# ✅ 定时刷新模式：
def update():
    bar.set(val)
    ui_root.after(100, update)      # 每100ms刷新
ui_root.after(100, update)
```

---

## 21. 常用组合拳

```python
# === 清空Frame ===
for w in frame.winfo_children():
    w.destroy()

# === 切换内容区 ===
def show_page1():
    clear()
    ctk.CTkLabel(content, text="页面1").pack()
def show_page2():
    clear()
    ctk.CTkLabel(content, text="页面2").pack()

# === 选择文件 ===
from tkinter import filedialog
path = filedialog.askdirectory(title="选文件夹")
path = filedialog.askopenfilename(filetypes=[("exe","*.exe")])
path = filedialog.asksaveasfilename(defaultextension=".json")

# === 管理员权限 ===
import ctypes
if not ctypes.windll.shell32.IsUserAnAdmin():
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, __file__, None, 1)
    sys.exit()
```

---

## 22. 完整模板

```python
import customtkinter as ctk
ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")

app = ctk.CTk()
app.title("我的程序")
app.geometry("500x400")
app.minsize(400, 300)

# 标题
ctk.CTkLabel(app, text="欢迎", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=20)

# 输入框
name_var = ctk.StringVar(value="")
ctk.CTkEntry(app, textvariable=name_var, placeholder_text="输入名字").pack(pady=10)

# 复选框
check = ctk.BooleanVar(value=True)
ctk.CTkCheckBox(app, text="启用", variable=check).pack(pady=5)

# 进度条
bar = ctk.CTkProgressBar(app)
bar.pack(pady=10, fill="x", padx=20)
bar.set(0.3)

# Frame
f = ctk.CTkFrame(app, fg_color=("gray90","gray17"))
f.pack(fill="x", padx=20, pady=10)
ctk.CTkLabel(f, text="Frame里的文字").pack(pady=5)

# 按钮
def on_click():
    CTkMessagebox(title="提示", message=f"你好 {name_var.get()}！", icon="info")

ctk.CTkButton(app, text="提交", command=on_click,
              width=120, height=40).pack(pady=15)

app.mainloop()
```
