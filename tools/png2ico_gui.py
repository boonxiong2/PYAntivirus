#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PNG2ICO 图形化转换工具"""
import os, sys
import customtkinter as ctk
from tkinter import filedialog
from PIL import Image

ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")

SIZES = [(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)]

class PNG2ICOApp:
    def __init__(self):
        self.win = ctk.CTk()
        self.win.title("PNG2ICO — 图标转换工具")
        self.win.geometry("420x380")
        self.win.resizable(False, False)

        ctk.CTkLabel(self.win, text="🖼 PNG → ICO",
                     font=ctk.CTkFont(size=22, weight="bold")).pack(pady=(25,5))
        ctk.CTkLabel(self.win, text="拖不了窗口，点按钮选文件",
                     font=ctk.CTkFont(size=11), text_color="gray").pack()

        # 文件选择
        frame = ctk.CTkFrame(self.win)
        frame.pack(pady=20, padx=30, fill="x")

        self.path_var = ctk.StringVar()
        ctk.CTkEntry(frame, textvariable=self.path_var, height=32).pack(side="left", padx=(5,0), fill="x", expand=True)
        ctk.CTkButton(frame, text="选择PNG", width=70, command=self.pick_png).pack(side="left", padx=5)

        # 尺寸勾选
        ctk.CTkLabel(self.win, text="包含尺寸:", font=ctk.CTkFont(size=12)).pack()
        size_frame = ctk.CTkFrame(self.win, fg_color="transparent")
        size_frame.pack(pady=5)
        self.size_vars = {}
        for s in SIZES:
            v = ctk.BooleanVar(value=True)
            self.size_vars[s] = v
            ctk.CTkCheckBox(size_frame, text=f"{s[0]}×{s[1]}", variable=v, width=60,
                           checkbox_width=16, font=ctk.CTkFont(size=11)).pack(side="left", padx=4)

        # 转换按钮
        self.btn = ctk.CTkButton(self.win, text="转换 →", font=ctk.CTkFont(size=15, weight="bold"),
                                  height=42, state="disabled", command=self.convert)
        self.btn.pack(pady=15)

        # 状态
        self.status = ctk.CTkLabel(self.win, text="", font=ctk.CTkFont(size=13))
        self.status.pack()

        # 打开文件夹
        self.open_btn = ctk.CTkButton(self.win, text="📂 打开所在文件夹", fg_color="gray",
                                       height=30, state="disabled", command=self.open_folder)
        self.open_btn.pack(pady=5)

        self.win.mainloop()

    def pick_png(self):
        p = filedialog.askopenfilename(filetypes=[("PNG图片", "*.png")])
        if p:
            self.path_var.set(p)
            self.btn.configure(state="normal", fg_color="#188038", hover_color="#0d6522")
            self.status.configure(text=f"✓ {os.path.basename(p)}", text_color="gray")

    def convert(self):
        png = self.path_var.get()
        if not png:
            return
        try:
            img = Image.open(png)
            out = png.rsplit('.', 1)[0] + '.ico'
            selected = [s for s in SIZES if self.size_vars[s].get() and s[0] <= img.width]
            img.save(out, format='ICO', sizes=selected)
            self.out_path = out
            self.status.configure(text=f"✅ {os.path.basename(out)} ({', '.join(f'{s[0]}' for s in selected)})", text_color="green")
            self.open_btn.configure(state="normal")
        except Exception as e:
            self.status.configure(text=f"❌ {e}", text_color="red")

    def open_folder(self):
        if hasattr(self, 'out_path'):
            os.startfile(os.path.dirname(self.out_path))


if __name__ == "__main__":
    PNG2ICOApp()
