# Chat Service UI 开发与交互说明

本文档记录前端界面的最新特性实现方式与样式维护规范，主要包括：
1. **主对话窗口与 Trace 窗口的宽度可拖拽调整机制**
2. **VS Code / Claude 扁平极简风格垂直滚动条的实现与修改位置**
3. **Trace 视图中 LLM Generation 步骤的结构化展示**

---

## 1. 如何实现可拖拽宽度

### 1.1 架构与实现原理

三栏布局基于 CSS Grid (`.layout`) 实现：
```text
Sidebar (220px / 56px)  |  Center (1fr, 主对话/问答)  |  Trace (可拖拽宽度 / 44px)
```

拖拽功能由 `Layout.jsx` 与 `TracePanel.jsx` 协同完成：

1. **状态管理 (`Layout.jsx`)**：
   - 维护 `traceWidth` 状态变量，默认宽度为 `380px`。
   - 设置合理的尺寸边界钳位（Clamp）：
     - `TRACE_MIN = 240px`：保证 Trace 面板内的步骤名称、元数据和按钮不会挤压错位。
     - `TRACE_MAX = 700px`：保证中间主对话区域始终拥有充足的阅读与输入空间。
   - 当 Trace 折叠时自动取 `TRACE_W_COLLAPSED = 44px`，展开时恢复用户拖拽设定的宽度。

2. **事件监听与坐标计算 (`Layout.jsx`)**：
   - 在拖拽分割条上按下鼠标时触发 `onDividerMouseDown`，记录初始光标位置 `startX` 和初始宽度 `startWidth`。
   - 将 `mousemove` 和 `mouseup` 注册在 `window` 全局对象上（而非仅在分割条元素上），防止鼠标快速移动或滑入 iframe/文本区时出现“掉帧”或“脱手”现象。
   - 宽度增量计算：`delta = startX - e.clientX`（向左拖动为增大 Trace 宽度，向右拖动为减小 Trace 宽度）。
   - 拖拽期间全局设置 `document.body.style.cursor = "col-resize"` 及 `userSelect = "none"`，防止选中文本。
   - 松开鼠标时在 `mouseup` 中注销监听器并还原全局样式。

3. **渲染性能与即时反馈 (`Layout.jsx`)**：
   - 通过 `rootStyle = { gridTemplateColumns: ... }` 内联样式直接更新网格定义，避免了拖拽过程频繁读写 CSS 变量或产生 CSS transitions 缓动延迟导致的“卡顿/拉扯感”。
   - CSS 中的 `transition: grid-template-columns 0.18s ease` 仅在用户点击折叠/展开按钮（通过 class 切换）时触发平滑动画。

4. **拖拽手柄定位与交互反馈 (`TracePanel.jsx` & `styles.css`)**：
   - 手柄元素 `<div className="tracepanel__divider" />` 位于 `TracePanel` 内部最左侧。
   - CSS 采用绝对定位贴紧左边界：
     ```css
     .tracepanel {
       position: relative;
     }
     .tracepanel__divider {
       position: absolute;
       left: 0;
       top: 0;
       bottom: 0;
       width: 6px;
       cursor: col-resize;
       z-index: 20;
       background: transparent;
       transition: background-color 0.15s ease;
       user-select: none;
       touch-action: none;
     }
     .tracepanel__divider::after {
       /* 扩展点击/触控热区（向左右扩展各 4px），无需加宽视觉线条 */
       content: "";
       position: absolute;
       inset: 0 -4px;
     }
     .tracepanel__divider:hover {
       background: rgba(108, 140, 255, 0.12);
     }
     ```

---

## 2. Scrollbar 样式改在哪里

为了彻底告别浏览器默认的粗大、高对比度 3D 滚动条，主对话和 Trace 面板已统一采用类似 **VS Code / Claude** 的极简扁平滚动条风格：
- **极窄**：宽度压缩至 `5px`（代码块内为 `4px`）。
- **背景融合**：轨道 (`track`) 设为 `transparent`，不出现独立灰色槽位。
- **低对比度**：滑块 (`thumb`) 默认半透明灰色，静止时克制不抢视觉焦点。
- **动态感知**：鼠标悬停在滑块时对比度适度提升。
- **精确作用域**：样式严格隔离在目标容器下，绝不污染系统或页面其他元素。

### 2.1 具体修改位置清单 (`chat_service/frontend/src/styles.css`)

#### ① 主对话与 Ask 消息滚动列表 (`.chatwindow__messages`)
- **文件**：`chat_service/frontend/src/styles.css`
- **代码位置**：约第 `610 - 635` 行
```css
.chatwindow__messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px 96px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 100px;

  /* VS Code / Claude style flat scrollbar */
  scrollbar-width: thin;
  scrollbar-color: rgba(160, 170, 195, 0.18) transparent;
}
.chatwindow__messages::-webkit-scrollbar {
  width: 5px;
}
.chatwindow__messages::-webkit-scrollbar-track {
  background: transparent;
}
.chatwindow__messages::-webkit-scrollbar-thumb {
  background: rgba(160, 170, 195, 0.18);
  border-radius: 3px;
}
.chatwindow__messages::-webkit-scrollbar-thumb:hover {
  background: rgba(160, 170, 195, 0.38);
}
```

#### ② Trace 面板内容滚动区域 (`.tracepanel__body`)
- **文件**：`chat_service/frontend/src/styles.css`
- **代码位置**：约第 `820 - 850` 行
```css
.tracepanel__body {
  overflow-y: auto;
  padding: 12px;
  flex: 1;

  /* VS Code / Claude style flat scrollbar */
  scrollbar-width: thin;
  scrollbar-color: rgba(160, 170, 195, 0.18) transparent;
}
.tracepanel__body::-webkit-scrollbar {
  width: 5px;
}
.tracepanel__body::-webkit-scrollbar-track {
  background: transparent;
}
.tracepanel__body::-webkit-scrollbar-thumb {
  background: rgba(160, 170, 195, 0.18);
  border-radius: 3px;
}
.tracepanel__body::-webkit-scrollbar-thumb:hover {
  background: rgba(160, 170, 195, 0.38);
}
```

#### ③ Raw Generation Output 完整文本预览区域 (`.trace-raw-output__body`)
- **文件**：`chat_service/frontend/src/styles.css`
- **代码位置**：约第 `1050 - 1080` 行
```css
.trace-raw-output__body {
  margin: 0;
  padding: 8px;
  font-size: 11.5px;
  line-height: 1.4;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  color: var(--text);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 400px;
  overflow-y: auto;

  /* Flat scrollbar inside raw output block */
  scrollbar-width: thin;
  scrollbar-color: rgba(160, 170, 195, 0.18) transparent;
}
.trace-raw-output__body::-webkit-scrollbar {
  width: 4px;
}
.trace-raw-output__body::-webkit-scrollbar-track {
  background: transparent;
}
.trace-raw-output__body::-webkit-scrollbar-thumb {
  background: rgba(160, 170, 195, 0.2);
  border-radius: 3px;
}
```

---

## 3. Trace 视图的 Generation Step 结构化展示

在 `TracePanel.jsx` 中针对 `name === "llm"` 步骤进行了专门的分区渲染：
1. **Request / Input**：以简洁紧凑的等宽字体表格列出 `model`、`max_tokens`、`thinking_enabled`、`question_chars`、`context_chars`。
2. **Raw Generation Output**：
   - 完整展示模型生成的原始字符串（对应后端 `qa_service.pipeline` 的 `raw_output` 字段）。
   - 即使模型输出如 `User Safety: safe`、异常截断或特殊标记，均 100% 原样呈现，不会因为文本截断而漏看。
   - 提供快捷 **"Copy"** 按钮，点击即可一键复制原始回答至剪贴板（带有 `✓ Copied` 反馈）。
   - 支持独立折叠/展开。
3. **Metadata**：清晰展示 `answer_chars` 等元数据。

