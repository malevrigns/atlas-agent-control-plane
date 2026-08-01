# 第五十五章. 对话叙事流与 Markdown 代码陈列

## 55.1 本章目标

​        学完本章后，你将能够：

​        换句话说，第一，理解为什么 Agent 产品的主界面应该围绕“对话叙事流”组织；第二，理解普通文本渲染和 Markdown 渲染在 AI 回复中的差异；第三，使用 `react-markdown` 和 `remark-gfm` 渲染代码块、列表、链接和表格；第四，把 AI 回复和最终总结改成 Markdown 展示；第五，把步骤里的工具调用从“大按钮”收敛成轻量内联节点；第六，让主对话区更接近真实 AI Agent 产品的中间内容流。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

## 55.2 最终效果

​        本章结束后，访问：

```Plain
http://localhost:8088
```

​        页面仍然是第 54 章的工作台，但中间对话区会发生三个变化：

​        从实现顺序看，第一，AI 回复支持 Markdown；第二，代码块会显示为独立代码区域，不再混在普通文本里；第三，计划步骤下的工具调用变成轻量节点，点击后仍然打开右侧工具详情。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        本章不是最终 UI 封版。第 56 章会继续把底部计划条和执行动效做得更像真实任务流，第 57 章会继续重做右侧工具详情。

## 55.3 本章要解决的问题

​        第 50-54 章已经把前端从功能面板逐步收敛到了 AI 工作台。

​        但还有一个很明显的问题：

```Plain
AI 对话内容看起来还是像普通文本面板。
```

​        真实 Agent 产品里，AI 回复经常包含：

```Plain
代码
命令
列表
表格
链接
小标题
执行总结
```

​        如果只用：

```TypeScript
<p className="whitespace-pre-wrap">{message.content}</p>
```

​        代码块、列表和表格都会失去结构，用户很难阅读。

​        另外，工具调用也不应该像控制台按钮一样占据很大面积。更好的方式是：

```Plain
中间时间线：轻量展示“正在搜索 / 正在执行命令 / 正在打开网页”
右侧详情：点击工具节点后查看完整参数、输出、截图或文件内容
```

​        所以本章先完成对话流的第一轮产品化对齐。

## 55.4 新增和修改的文件

```Plain
README.md
docs/course/coverage-matrix.md
docs/course/outline.md
docs/course/chapters/55-conversation-narrative-markdown.md
ui/README.md
ui/package.json
ui/pnpm-lock.yaml
ui/app/components/markdown-content.tsx
ui/app/components/chat-workspace.tsx
ui/app/components/conversation/message-bubble.tsx
ui/app/components/conversation/agent-run-block.tsx
ui/app/components/conversation/step-card.tsx
```

## 55.5 实施步骤
### 55.5.1 安装 Markdown 渲染依赖

​        进入前端目录：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents/ui
```

​        安装依赖：

```Bash
pnpm add react-markdown remark-gfm
```

​        安装后，`ui/package.json` 会新增：

```JSON
"react-markdown": "^10.1.0",
"remark-gfm": "^4.0.1"
```

#### 55.5.1.1 为什么需要这两个依赖

​        `react-markdown` 负责把 Markdown 字符串转换成 React 组件。

​        `remark-gfm` 负责支持 GitHub Flavored Markdown，例如：

```Plain
表格
任务列表
删除线
自动链接
```

​        AI 回复非常容易包含代码块和列表，因此从这一章开始，不再把 AI 消息当普通纯文本处理。

### 55.5.2 新增 MarkdownContent 组件

​        创建 `ui/app/components/markdown-content.tsx`。

​        本章核心代码如下：

```TypeScript
"use client";

import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

type MarkdownContentProps = {
  className?: string;
  content: string;
};

// 中文标点紧跟 URL 时，自动链接有时会把后面的中文也吃进去。
// 这里先做一次文本归一化，让链接边界更稳定。
const cjkRanges = "\\u3000-\\u303F\\u4E00-\\u9FFF\\uFF01-\\uFF60";
const urlFollowedByCjk = new RegExp(
  `(https?:\\/\\/[^\\s${cjkRanges}]+)([${cjkRanges}])`,
  "g",
);

function normalizeAutolinks(value: string) {
  return value.replace(urlFollowedByCjk, "$1 $2");
}

const components: Components = {
  p: ({ children }) => (
    <p className="mb-3 text-base leading-8 text-zinc-400 last:mb-0">
      {children}
    </p>
  ),
  strong: ({ children }) => (
    <strong className="font-semibold text-zinc-100">{children}</strong>
  ),
  code: ({ children, className }) => {
    const value = String(children);
    const block = value.includes("\n") || className?.startsWith("language-");
    if (!block) {
      return (
        <code className="rounded-md border border-white/10 bg-white/[0.07] px-1.5 py-0.5 font-mono text-[0.9em] text-zinc-100">
          {children}
        </code>
      );
    }
    return (
      <code className="block overflow-x-auto whitespace-pre rounded-2xl border border-white/10 bg-black/45 p-4 font-mono text-sm leading-6 text-zinc-100">
        {children}
      </code>
    );
  },
  pre: ({ children }) => <pre className="my-4 overflow-x-auto">{children}</pre>,
};

export function MarkdownContent({ className = "", content }: MarkdownContentProps) {
  return (
    <div className={`break-words ${className}`}>
      <ReactMarkdown components={components} remarkPlugins={[remarkGfm]}>
        {normalizeAutolinks(content)}
      </ReactMarkdown>
    </div>
  );
}
```

#### 55.5.2.1 这段代码的业务作用

​        `MarkdownContent` 是 AI 回复的统一渲染入口。

​        后续只要是模型返回给用户看的内容，都优先交给它处理：

```Plain
assistant 消息
最终回答
工具总结
文件生成说明
```

​        这样做的好处是，AI 输出代码时会自然显示为代码块，而不是一段难读的普通文字。

### 55.5.3 让 AI 回复使用 MarkdownContent

​        打开 `ui/app/components/conversation/message-bubble.tsx`。

​        用户消息仍然用普通气泡展示，因为用户输入通常是短文本。

​        AI 消息改成：

```TypeScript
<MarkdownContent className="mt-3" content={message.content} />
```

#### 55.5.3.1 为什么只改 AI 消息

​        用户消息是“任务输入”，更像一条指令。

​        AI 消息是“执行解释和结果输出”，经常包含结构化内容。

​        所以本章先让 AI 消息支持 Markdown。后续如果用户上传 Markdown 片段，也可以再按需要扩展用户消息渲染。

### 55.5.4 让最终总结使用 MarkdownContent

​        打开 `ui/app/components/conversation/agent-run-block.tsx`。

​        原来最终回答只是按换行拆成多个段落：

```TypeScript
<FormattedAnswer value={firstAnswer} />
```

​        本章改成：

```TypeScript
<MarkdownContent content={firstAnswer} />
```

#### 55.5.4.1 为什么最终总结更需要 Markdown

​        最终总结通常包含：

```Plain
1. 完成了什么
2. 生成了哪些文件
3. 下一步建议
4. 可能附带代码或命令
```

​        这些内容用 Markdown 展示会更清晰。

### 55.5.5 弱化步骤外壳，突出对话流

​        打开 `ui/app/components/conversation/agent-run-block.tsx`。

​        本章把计划区域从厚重卡片改成更轻的折叠行：

```TypeScript
<button className="flex w-full items-center justify-between gap-4 rounded-xl px-2 py-2 text-left transition hover:bg-white/[0.035]">
```

#### 55.5.5.1 为什么这样改

​        主对话区应该让用户先看到：

```Plain
AI 正在做什么
每一步发生了什么
工具调用了什么
最终结果是什么
```

​        如果每个计划块都像大面板，页面会更像管理后台，而不是 AI 对话产品。

### 55.5.6 把工具调用改成轻量节点

​        打开 `ui/app/components/conversation/step-card.tsx`。

​        工具调用按钮从大块卡片改成轻量节点：

```TypeScript
<button className="inline-flex w-fit max-w-full items-center gap-2 rounded-lg border border-white/10 bg-white/[0.055] px-3 py-1.5 text-left text-sm font-medium text-zinc-500 transition hover:border-blue-500/40 hover:bg-blue-500/10 hover:text-zinc-100">
```

#### 55.5.6.1 这段代码的业务作用

​        中间对话流只展示工具摘要：

```Plain
正在搜索 ...
正在执行命令 ...
正在打开网页 ...
```

​        完整参数、输出、截图和文件内容仍然交给右侧工具详情。

​        这就是“中间轻、右侧详”的设计：

```Plain
中间：看执行过程
右侧：看工具证据
```

## 55.6 关键理解

​        本章最重要的是理解：Agent 产品不是把日志贴到页面上。

​        更好的展示方式是：

```Plain
用户输入任务
AI 用自然语言说明理解
计划和步骤以可折叠时间线展示
工具调用以轻量节点展示
最终结果用 Markdown 输出
```

​        这样用户可以快速读懂任务过程，也可以在需要时打开右侧详情检查证据。

## 55.7 运行验证

​        下面命令默认在项目根目录执行。

### 55.7.1 检查前端类型

```Bash
cd ui
pnpm typecheck
```

​        预期没有 TypeScript 报错。

### 55.7.2 构建前端

```Bash
pnpm build
```

​        预期构建成功。

### 55.7.3 Docker 验证

​        回到项目根目录：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
docker compose build ui
docker compose up -d --force-recreate ui nginx
```

​        访问：

```Plain
http://localhost:8088
```

​        创建或选择会话后，发送一条包含代码需求的任务，例如：

```Plain
帮我写一个 Python 函数，计算列表中所有偶数的和，并解释代码。
```

​        预期：

​        放到工程语境里看，第一，AI 回复中的代码块有独立背景；第二，列表和加粗能正常显示；第三，计划步骤下的工具调用更轻量；第四，点击工具节点仍然能打开右侧详情。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

## 55.8 常见问题

- 问题：页面里代码还是普通文本怎么办？

​        解释：先确认 AI 返回内容里是否包含 Markdown 代码围栏，例如三个反引号。如果后端返回的是纯文本，前端无法自动判断哪些内容一定是代码。

- 问题：链接后面的中文也变成链接怎么办？

​        解释：`MarkdownContent` 已经对 URL 后接中文标点的情况做了归一化。如果还有特殊样例，可以继续扩展 `normalizeAutolinks()`。

- 问题：为什么本章没有一次性重做右侧工具区？

​        解释：本章先解决中间对话流和代码展示。右侧工具区会在第 57 章继续最终对齐，避免一次改动过大。

## 55.9 本章小结

​        本章完成了对话流产品化的第一步：

​        展开来看，第一，安装了 Markdown 渲染依赖；第二，新增了 `MarkdownContent`；第三，AI 回复和最终总结开始支持 Markdown；第四，工具调用从大按钮收敛为轻量节点；第五，主对话区宽度继续向中间叙事流靠拢。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        下一章会继续处理底部计划折叠条和执行流动效，让任务执行过程更像连续的 AI 工作流。
