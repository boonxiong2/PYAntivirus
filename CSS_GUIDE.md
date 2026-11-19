# CSS 速查（2026版）

## 1. 引入CSS

```html
<!-- 方式1：内联 -->
<style>
  body { background: #0a0a0f; }
</style>

<!-- 方式2：外部文件 -->
<link rel="stylesheet" href="style.css">
```

---

## 2. 选择器

```css
/* 标签 */       body { }
/* 类 */         .card { }
/* ID */         #hero { }
/* 嵌套 */       .card h2 { }
/* 并列 */       .card, .box { }
/* hover */      .btn:hover { }
/* 子元素 */     .nav > a { }
/* 属性 */       [data-theme="dark"] { }
```

---

## 3. 常用属性速查

```css
/* === 颜色 === */
color: #fff;                    /* 文字色 */
background: #0a0a0f;            /* 背景色 */
background: rgba(0,0,0,0.5);    /* 半透明 */
background: linear-gradient(180deg, #1a1a2e, #0a0a0f); /* 渐变 */

/* === 文字 === */
font-size: 16px;
font-weight: bold;              /* normal/500/600/bold */
font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
text-align: center;             /* left/center/right */
line-height: 1.6;
letter-spacing: 1px;
text-decoration: none;          /* 去掉下划线 */

/* === 间距 === */
margin: 20px;                   /* 外边距 */
margin: 10px 20px;             /* 上下 左右 */
margin: 0 auto;                 /* 上下0 左右自动=居中 */
padding: 15px;                  /* 内边距 */

/* === 尺寸 === */
width: 100%;
max-width: 1200px;              /* 最大宽度 */
height: 100vh;                  /* 满屏 */
min-height: 400px;

/* === 边框 === */
border: 1px solid #30363d;
border-radius: 12px;            /* 圆角 */
border-radius: 50%;             /* 正圆 */
border: none;                   /* 去边框 */
outline: none;                  /* 去焦点框 */

/* === 阴影 === */
box-shadow: 0 4px 20px rgba(0,0,0,0.3);

/* === 过渡动画 === */
transition: all 0.3s ease;
transition: transform 0.2s, opacity 0.2s;

/* === 透明度 === */
opacity: 0.8;

/* === 鼠标 === */
cursor: pointer;
user-select: none;              /* 不可选中 */
```

---

## 4. Flex 布局（最常用！）

```css
.container {
  display: flex;
  justify-content: center;      /* 主轴对齐: center/space-between/space-around */
  align-items: center;          /* 交叉轴对齐: center/flex-start/flex-end */
  flex-wrap: wrap;              /* 换行 */
  gap: 20px;                    /* 间距（推荐，比margin好用） */
  flex-direction: column;       /* 竖排 */
}

.item {
  flex: 1;                      /* 等分剩余空间 */
  flex: 0 0 300px;              /* 不伸缩 不压缩 固定300px */
}
```

---

## 5. Grid 布局（卡片网格）

```css
.grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);  /* 3列等宽 */
  gap: 24px;                              /* 间距 */
}

.grid-2 { grid-template-columns: repeat(2, 1fr); }   /* 2列 */
.grid-auto { grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); } /* 自适应 */

/* 合并单元格 */
.big { grid-column: span 2; }
```

---

## 6. 定位

```css
.fixed-nav {
  position: fixed;              /* 固定 */
  top: 0; left: 0; right: 0;
  z-index: 100;                 /* 层级 */
}

.absolute-center {
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%); /* 绝对居中 */
}

.relative { position: relative; }  /* 相对定位（作为绝对定位的参考） */
```

---

## 7. 毛玻璃效果

```css
.glass {
  background: rgba(10, 10, 15, 0.85);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);  /* Safari兼容 */
}
```

---

## 8. 响应式

```css
/* 手机 */
@media (max-width: 768px) {
  .grid { grid-template-columns: 1fr; }
  .nav { flex-direction: column; }
  h1 { font-size: 28px; }
}

/* 平板 */
@media (max-width: 1024px) {
  .grid { grid-template-columns: repeat(2, 1fr); }
}

/* 暗色模式 */
@media (prefers-color-scheme: dark) {
  body { background: #0a0a0f; color: #fff; }
}
```

---

## 9. 按钮模板

```css
.btn {
  display: inline-block;
  padding: 12px 32px;
  font-size: 16px;
  font-weight: 600;
  color: #fff;
  background: #1a73e8;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s;
  text-decoration: none;
}

.btn:hover {
  background: #1557b0;
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(26, 115, 232, 0.4);
}

.btn-outline {
  background: transparent;
  border: 2px solid #1a73e8;
  color: #1a73e8;
}
.btn-outline:hover {
  background: #1a73e8;
  color: #fff;
}
```

---

## 10. 卡片模板

```css
.card {
  background: #1a1a2e;
  border-radius: 16px;
  padding: 30px;
  transition: transform 0.3s, box-shadow 0.3s;
}

.card:hover {
  transform: translateY(-6px);
  box-shadow: 0 12px 40px rgba(0,0,0,0.5);
}
```

---

## 11. 完整页面骨架

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PYAntivirus</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
      background: #0a0a0f;
      color: #fff;
      line-height: 1.6;
    }

    /* 导航 */
    .nav {
      position: fixed; top: 0; width: 100%;
      padding: 16px 40px;
      background: rgba(10,10,15,0.9);
      backdrop-filter: blur(10px);
      display: flex; justify-content: space-between; align-items: center;
      z-index: 100;
    }
    .nav a { color: #9aa0a6; text-decoration: none; margin-left: 24px; }
    .nav a:hover { color: #fff; }

    /* 英雄区 */
    .hero {
      min-height: 100vh;
      display: flex; flex-direction: column;
      justify-content: center; align-items: center;
      text-align: center; padding: 0 20px;
    }
    .hero h1 { font-size: 56px; margin-bottom: 16px; }
    .hero p { font-size: 18px; color: #9aa0a6; max-width: 600px; margin-bottom: 32px; }

    /* 按钮 */
    .btn { display: inline-block; padding: 14px 36px; border-radius: 10px;
           font-size: 16px; font-weight: 600; text-decoration: none;
           transition: all 0.3s; margin: 8px; }
    .btn-primary { background: #1a73e8; color: #fff; }
    .btn-primary:hover { background: #1557b0; transform: translateY(-2px); }
    .btn-outline { border: 2px solid #1a73e8; color: #1a73e8; }

    /* 卡片网格 */
    .section { max-width: 1200px; margin: 0 auto; padding: 80px 20px; }
    .section h2 { text-align: center; font-size: 36px; margin-bottom: 48px; }
    .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; }
    .card { background: #1a1a2e; border-radius: 16px; padding: 32px;
            transition: transform 0.3s; }
    .card:hover { transform: translateY(-6px); }
    .card .icon { font-size: 40px; margin-bottom: 16px; }
    .card h3 { margin-bottom: 8px; }
    .card p { color: #9aa0a6; font-size: 14px; }

    /* 响应式 */
    @media (max-width: 768px) {
      .grid { grid-template-columns: 1fr; }
      .hero h1 { font-size: 32px; }
      .nav { padding: 12px 16px; }
    }
  </style>
</head>
<body>
  <nav class="nav">
    <span>🛡️ PYAntivirus</span>
    <div>
      <a href="#">首页</a>
      <a href="#">功能</a>
      <a href="#">下载</a>
      <a href="#">文档</a>
    </div>
  </nav>

  <section class="hero">
    <h1>🛡️ PYAntivirus</h1>
    <p>下一代 Python 智能杀毒软件 · 110万病毒库 · 8层引擎 · ML检测</p>
    <div>
      <a href="#" class="btn btn-primary">⬇ 免费下载</a>
      <a href="#" class="btn btn-outline">📖 查看文档</a>
    </div>
  </section>

  <section class="section">
    <h2>核心功能</h2>
    <div class="grid">
      <div class="card">
        <div class="icon">🔒</div>
        <h3>实时防护</h3>
        <p>文件监控 + 进程守护，5分钟自动巡检</p>
      </div>
      <div class="card">
        <div class="icon">🧠</div>
        <h3>ML检测</h3>
        <p>13维特征 + 100棵树随机森林投票</p>
      </div>
      <div class="card">
        <div class="icon">⚡</div>
        <h3>极速扫描</h3>
        <p>110万哈希 Set O(1)查找，秒级匹配</p>
      </div>
      <div class="card">
        <div class="icon">🎯</div>
        <h3>YARA规则</h3>
        <p>银狐/WannaCry/熊猫烧香/CS 精准识别</p>
      </div>
      <div class="card">
        <div class="icon">🛡️</div>
        <h3>TI权限</h3>
        <p>TrustedInstaller级别，系统文件照删</p>
      </div>
      <div class="card">
        <div class="icon">🔐</div>
        <h3>防篡改</h3>
        <p>SHA256完整性校验，启动自动检测</p>
      </div>
    </div>
  </section>
</body>
</html>
```
