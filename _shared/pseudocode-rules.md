# 伪代码质量规则

两个 skill 在生成伪代码时都必须遵守此规则；reviewer 会按此检查。

## 必须

- **从真实源码提取**，不从论文 Algorithm box 抄写
- **每段代码块头部注释 `# source: <file>:L<a>-L<b>`** — `paper-to-skill` 必须包含完整行号范围
- **paper-to-note 例外** — 允许简写为 `# source: <file>`（不带 `L<a>-L<b>`），因 paper-to-note 映射只到 §节级别
- **关键步骤内联注释** `# paper: §X.Y, Eq.N` 标注论文对应位置
- **代码独有的 trick** 用 `# [CODE-ONLY] <说明>` 标注
- **每个核心组件一个独立代码块**（不合并多个组件到一段伪代码）
- **Python/PyTorch 风格**：使用 `def` / `class` / `for` / `if` / `torch.*` / `F.*`；不使用 Algorithm-1 式编号步骤
- **已有 shape 注释保留**：如果源码注释或 docstring 标注了 tensor shape，在伪代码中保留 `# [B, C, H, W]` 形式
- **每一行可执行伪代码都要有中文行内注释**：说明这一行在算法中做什么、为什么需要、数据/张量如何流动；不要只机械翻译变量名
- **注释可合并信息**：source / paper / shape / `[CODE-ONLY]` 标注可以和中文解释写在同一个 `# ...` 中，但每个可执行语句仍必须有解释性中文
- **例外行**：空行、装饰器、纯注释行、仅包含闭合括号/方括号/花括号的行可以不写行内中文注释

## 允许

- 去掉 **非核心代码**：logging、分布式 wrapper、debug assertion、非关键错误处理、progress bar
- 长函数截断：用 `# ... <省略理由，如"数据加载部分不影响算法理解"> ...`
- 简化命名：源码中的 `self._internal_buffer_for_ema_weights` 可简化为 `self.ema_buf`，但需注释 `# renamed from self._internal_buffer_for_ema_weights`

## 禁止

- 只写函数签名不写核心逻辑（签名是 Module Interface Contracts 的事）
- 用 pseudo-English 替代真实代码（e.g. 写 "compute cross entropy loss" 而不写 `F.cross_entropy(...)`）
- **猜测 tensor shapes**：只写代码注释 / docstring 明确标注的 shape
- 伪代码与源码对应关系不清晰（reviewer 会抽查比对）
- 同一组件多段不同伪代码（选一个主版本即可）
- 可执行语句缺少中文行内注释，或注释只写“计算 loss / forward pass”这类无法帮助读者理解算法意图的空泛描述

## 示例

### 好的伪代码

```python
# source: model/dit.py:L145-L189
# paper: §3.2, Algorithm 1
def forward(self, x, t, cond):
    x_t = self.patch_embed(x)  # 将输入图像从像素网格切成 patch tokens，得到 Transformer 可处理的序列表示；shape 来自源码注释 [B, C, H, W]
    t_emb = self.time_embed(t)  # 把 diffusion timestep 编码成条件向量，让网络知道当前去噪阶段
    h = self.blocks(x_t + t_emb, cond)  # 将图像 tokens、时间条件和外部条件送入 DiT blocks，建模条件去噪所需的全局交互；paper: Eq.7
    out = self.head(h)  # 把 Transformer hidden states 投影回模型需要预测的输出空间，例如噪声或 velocity
    return out * (1.0 / math.sqrt(2))  # [CODE-ONLY] 对输出做数值缩放以稳定训练，这是源码实现中的额外 trick
```

### 坏的伪代码（会被 reviewer FAIL）

```python
# DiT forward pass
def forward(x, t, cond):
    x = patch_embed(x)
    x = x + t_embed
    return blocks(x, cond)
```

问题：无 source 标注、无 shape、可执行语句没有中文行内注释、核心逻辑退化为英文描述、没写关键细节（scale factor）。
