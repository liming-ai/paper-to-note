---
name: paper-to-note
description: "Use when reading an academic paper or paper URL and saving structured Chinese notes with metadata/assets to Obsidian."
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
  - WebFetch
  - WebSearch
  - Agent
  - mcp__codex__codex
---

# Paper-to-Note

Generate high-quality structured reading notes for academic papers.

## Scope（与 paper-to-skill 的分工）

- **本 skill 目的**：生成"阅读笔记"，让人类读者**读懂论文**（motivation / 核心贡献 / 方法直觉）。
- **如果你的目标是"把算法植入新 codebase"**（需要逐行代码映射、Porting Checklist、commit 锚点、模块接口 contracts）：请使用 `paper-to-skill` skill，产物在 `~/ai-skills/skills/`。
- **最佳工作流**：先用本 skill 读懂，再用 `paper-to-skill` 提炼工程手册。本 skill 在保存笔记时，如果已有对应 paper-to-skill skill，会自动填写 frontmatter 的 `paper_to_skill` 属性以便互相跳转。

## Shared Infrastructure

- `~/.claude/skills/_shared/commit-anchor.md` — commit SHA 锚点格式（Pitfall P5 引用）
- `~/.claude/skills/_shared/pseudocode-rules.md` — 伪代码质量规则
- `~/.claude/skills/_shared/known-categories.md` — Obsidian 分类
- `paper-to-note/scripts/extract_figures.py` — canonical 图像提取工具；arXiv source-first，保留原始 source raster/vector 质量。若 runtime 还有旧的 `$SHARED/extract_figures.py` 镜像，必须确认它与本脚本一致后再用。

### Runtime Path Fallback（跨 runtime 路径约定）

本 skill 同时存在两份副本，在不同 runtime 下读取不同的物理路径（内容保持一致）：

| 逻辑引用 | Claude Code 原生路径 | Cursor / Codex / 其他共享 runtime |
|---|---|---|
| `$SHARED/<file>` | `~/.claude/skills/_shared/<file>` | `~/.agents/skills/_shared/<file>` |
| `$REVIEWER` | `~/.claude/agents/paper-to-note-reviewer.md` | `~/.agents/skills/paper-to-note/agents/paper-to-note-reviewer.md` |

下文所有 `~/.claude/skills/_shared/...` 与 `~/.claude/agents/paper-to-note-reviewer.md` 引用，执行时按上表选择**当前 runtime 下实际存在**的那条路径即可（两条路径等价）。


## Context Budget Rules（必须遵守）

The most common failure mode is re-counting the same long context across many turns and agents. Treat context as a budgeted artifact, not a transcript.

- **Default to path-based handoff**: write intermediate paper text, figure inventory, code notes, and review findings to files in an external scratch directory outside the Obsidian vault; pass only paths plus a short objective in prompts.
- **Do not paste full artifacts into prompts**: pass file paths for the PDF, note `.md`, image directory, repo checkout, and source files. Only paste small excerpts needed for the current decision.
- **Create a compact work packet outside the vault** before review: write a short `review_packet.md` under `$PAPER_TO_NOTE_WORKDIR/<paper-slug>/` if set, otherwise `${TMPDIR:-/tmp}/paper-to-note/<paper-slug>/`. It should contain only paper metadata, note path, image dir, code repo/ref, figure inventory, unresolved risks, and changed sections since the last review. Keep it under ~120 lines by default and never exceed ~200 lines.
- **Never pollute the Obsidian vault with scratch artifacts**: do not create `review_packet*.md`, `revew_packet*.md`, `tmp/`, `_tmp/`, `_work/`, extracted paper text, reviewer notes, or cloned repos anywhere under `/Users/bytedance/Library/CloudStorage/OneDrive-个人/paper_notes/` (or the equivalent `~/OneDrive/paper_notes/`). The vault may contain only the final note under `notes/` and final referenced assets under `files/`.
- **Read selectively**: when revisiting the paper/note/source, use section-level reads, grep headers, or table/figure inventories instead of reloading the full paper, full note, full source tree, or prior chat.
- **Bound multi-agent usage**: multi-agent review is allowed, but use the rule-based set below (do NOT let the agent self-judge "low risk" to skip Source Code Reviewer):
  - **Always run** Format Reviewer + Content Reviewer.
  - **Source Code Reviewer is MANDATORY** whenever the paper has a public GitHub repo (i.e. `github_ref` will be set). The only valid skip condition is: the note explicitly states `代码搜索未找到开源实现` after a documented search.
  - Never spawn a coordinator that then spawns another 3 reviewers unless the runtime has no direct parallel-agent support. Never pass the full conversation or full paper to reviewers.
- **No full-context subagent forks**: when the runtime supports agent context controls, start reviewers without inheriting the whole chat history. Give them only `$REVIEWER`, the external `review_packet.md` path, and concrete file paths.
- **Keep reviewer prompts small**: reviewer prompt should be ≤ ~1,200 words and must not inline the whole skill, note, paper, transcript, or source code. Reference instruction files by path.
- **Targeted re-review only**: after fixing issues, re-run only the reviewer scope affected by the fix. Do not repeat all reviewers with the complete long context unless the note was substantially rewritten.
- **No git-worktree review in paper/vault dirs**: do not use Codex/worktree-isolated review when the current directory is a paper folder, Obsidian vault, or any git repository without a valid `HEAD` (`git rev-parse --verify HEAD` fails). In that case, review in-place with read-only file access and do not try to resolve base branch `HEAD`.

## Language Rules

- **All note content in Chinese**, except:
  - Technical terms keep English (e.g. Diffusion Model, RLHF, Transformer)
  - Names, institutions, datasets, model names keep original language
  - Code and pseudocode in English
- **All math formulas in LaTeX**: inline `$...$`, display `$$...$$`

## Note Format

### Detail-first Standard（默认深度要求）

Unless the user explicitly asks for a short summary, **write the note as a detailed reading note, not an abstract-style overview**. The target is that a reader can understand the paper's motivation, method, experiments, and practical caveats from the note itself without immediately reopening the PDF.

- **Depth over brevity**: include concrete assumptions, design motivations, component-by-component mechanics, algorithm flow, objective terms, important implementation details, ablation interpretations, and limitations. Avoid one-paragraph summaries for sections where the paper spends substantial space.
- **Specificity over generic prose**: name the actual modules, datasets, baselines, reward models, losses, schedules, hyperparameters, and measured numbers. Do not write generic phrases like "提升效果明显" without the exact table/figure evidence.
- **Explain, do not only transcribe**: after formulas, figures, algorithms, and tables, add human-readable interpretation: what each symbol/component means, why the design is needed, what failure mode it addresses, and how it differs from prior work.
- **Appendix is in scope**: if appendix/supplement includes training details, extra ablations, prompt lists, implementation choices, or failure cases that materially affect understanding or reproduction, incorporate them into §3–§5 instead of ignoring them.
- **Minimum length**: unless the user explicitly asks for a short summary, the final saved note MUST contain at least **350 Markdown lines**. If the note is shorter, expand with substantive method details, experiment evidence, appendix material, code-to-paper interpretation, figure/table explanations, and limitations; never pad with repetitive filler.
- **Depth priority**: allocate the most detail to **§1 Motivation, §2 Idea, and especially §3 Method**. These three sections should carry the main paper understanding: why the problem matters, what the core insight is, and how the method actually works. Only after these are clear and detailed should §4 Experimental Setup and §5 Experimental Results be summarized with exact evidence.

### 0. Mandatory Skeleton（每篇笔记的格式硬底线）

These are **non-negotiable structural items**. A note missing any of them will be marked P0 by the Format Reviewer and must be fixed before approval.

1. **frontmatter MUST contain a `title` field** with the full paper title (not just the short name). Reason: Obsidian uses `title` as the canonical display name; without it, search and graph view both degrade.
   ```yaml
   ---
   title: "World-R1: Reinforcing 3D Constraints for Text-to-Video Generation"
   authors: ...
   ---
   ```
2. **Top of the note MUST contain a Paper / Code / Code-reference blockquote block** immediately after the H1 heading, before any section. Skip `Code` / `Code reference` lines only when no public code exists.
   ```
   # <Paper Title>

   > **Paper**: [arXiv:XXXX.XXXXX](https://arxiv.org/abs/XXXX.XXXXX)
   > **Code**: [<owner>/<repo>](https://github.com/<owner>/<repo>)
   > **Code reference**: `<branch>` @ `<short_sha>` (YYYY-MM-DD)
   ```
3. **frontmatter MUST contain `tags`** with ≥4 specific technical tags (concrete techniques, not generic categories). Bad: `["RL", "video"]`. Good: `["RL", "video-generation", "Flow-GRPO", "3D-consistency"]`.
4. **Training-config numbers MUST come from the actual launch script / experiment config** (e.g. `config/<paper_name>.py`, `configs/<exp>.yaml`, `scripts/train_*.py`), NOT from `config/base.py` default values or generic README defaults. Whenever the reported number could plausibly be a default, the note MUST cite the specific file path that overrides it.
5. **When paper formula and released code disagree** (e.g. paper says HPSv3 but code calls `hpsv2`; paper writes "average over $K$ frames" but code samples 1 random frame), the note MUST explicitly call out the gap in §3 Method, format: `论文公式与 released code 实现差异：...`. Do NOT silently align the note to one side.

---

### 1–5: Required Section Content

Output strictly in these 5 sections, each with substantive content. **Default to maximum useful detail**: do not compress a multi-page method/experiment section into a few bullets unless the user explicitly asks for a brief note. The note's explanatory center of gravity should be **Motivation → Idea → Method**; experiments and results are still required, but they support the reader's understanding rather than replacing method explanation.

---

### 1. Motivation (研究动机)

<!-- checklist: must answer 3 questions below with specifics, not generic restatements -->

- What problems exist in current methods? *(be specific: what capability is missing or what bottleneck exists)*
- What problem does this paper aim to solve? *(state the concrete target, not a broad area)*
- Why is this problem worth studying? *(what unlocks once solved)*

---

### 2. Idea (核心思想)

<!-- checklist (per P6): core insight MUST be concrete; no generic "本文提出了…" summaries -->

- What is the core insight? *(1–3 sentences; what's fundamentally new, not just renamed)*
- Summarize the key innovation in 1–3 sentences
- What is the fundamental difference from existing methods? *(name a specific competing approach and contrast)*

---

### 3. Method (方法)

**This is the most important section — expand in detail.** Cover every novel component and every paper section that materially contributes to the method. If the paper has multiple modules/stages/objectives, each should get its own subsection with intuition, mechanics, formula/code where applicable, and interaction with the rest of the pipeline.

<!-- checklist (per P6): method section MUST include ALL 5 items below; include at least one intuition paragraph (prose, not math/code) -->

1. **Overall framework**: describe the overall design, **embed the architecture figure**
2. **Key components**: explain each core module with sub-figures where available. For each component, include: what input it consumes, what output it produces, which objective or constraint it optimizes, why the authors need it, and what would likely fail if it were removed.
   - **Every figure MUST have a "Figure N 解读" paragraph** after the `<img>` tag, **separated by a blank line** (see P8)
   - The walkthrough should explain what each part of the figure shows and how it relates to the method
   - When text references a figure (e.g. "如图 3a 所示"), always specify the figure number
3. **Math formulas**: key loss functions, objectives, algorithm formulas (LaTeX)
4. **Pseudocode** (for algorithm-improvement papers):
   - **ALWAYS search for open-source code** — never assume code is unavailable just because the paper says "plan to release"
   - Use `WebSearch` to verify: `[paper title] github`, `[author org] github [method name]`
   - Read the actual source code and produce pseudocode reflecting real implementation
   - **Write pseudocode for EACH key component separately**, not just the overall pipeline
   - E.g. if a paper has 4 novel components, write 4 separate pseudocode blocks
   - **Pseudocode MUST be Python/PyTorch style** — use real Python syntax with PyTorch API (e.g. `torch.tensor`, `nn.Module`, `F.cross_entropy`)
   - Use `python` code blocks for syntax highlighting
   - Format: write as a runnable Python/PyTorch function or class, not numbered steps
   - Example:
   ```python
   def train_step(model, batch, optimizer):
       x, y = batch
       logits = model(x)  # forward pass
       loss = F.cross_entropy(logits, y)
       loss.backward()
       optimizer.step()
       return loss.item()
   ```
5. **Code-to-paper mapping table**: map key paper concepts to actual source files/classes. **Always add a reference header** immediately before the table:
   ```
   > **Code reference**: `main` @ `abc12345` (2026-04-17) — pseudocode and mapping based on this commit
   ```

---

### 4. Experimental Setup (实验设置)

<!-- checklist: all 4 items MUST be present with specifics (not placeholders) -->

- Datasets used and their scale *(name each dataset + sample count)*
- Baseline methods compared *(list specific methods by name)*
- Evaluation metrics *(list each metric with 1-line definition if non-obvious)*
- Training config (model, hardware, hyperparameters) *(GPU type/count, training steps, LR, batch size)*

---

### 5. Experimental Results (实验结果)

<!-- checklist: main numbers MUST be exact (not approximated); include limitations if mentioned in paper -->

- Performance numbers on main benchmarks (use tables or lists) *(exact values from paper tables, no approximations)*
- Key findings from ablation studies *(which components matter and by how much)*
- Limitations of the method *(if mentioned by authors; do not fabricate)*
- Overall conclusions *(what the results demonstrate)*

---

## Execution Steps

### Step 1: Obtain paper content

- **User uploaded PDF**: read directly with `Read` tool
- **User gave a link**: prefer `WebFetch` for normal web pages; **if `WebFetch` fails with domain safety verification / enterprise policy errors, immediately fall back to `Bash(curl -L ...)` or `python urllib/request`** and continue.
- **arXiv links**: use `curl` as the default path in proxy/offline-routed runtimes; fetch the HTML abstract page and PDF directly:
  ```bash
  curl -L "https://arxiv.org/abs/<arxiv_id>" -o ~/ai-skills/papers/<arxiv_id>.html
  curl -L "https://arxiv.org/pdf/<arxiv_id>" -o ~/ai-skills/papers/<arxiv_id>.pdf
  ```
- **Only a title given**: use `WebSearch` to find the paper, then fetch it
- **Always download PDF** to `~/ai-skills/papers/` for figure extraction

### Step 2: Extract original figures

**Source-first rule for arXiv papers（默认路径）**: if the paper has an arXiv ID, you MUST extract figures from the arXiv LaTeX source before considering any PDF crop. The PDF is for reading/verification; it is **not** the default figure source. Do not create cropped PDF screenshots for arXiv papers unless source extraction returns no usable figure for a specific required figure/table, and record that exception in the working notes.

**For arxiv papers (default)**: download source tarball/e-print to get original high-res figure files:

```bash
python3 ~/.claude/skills/paper-to-note/scripts/extract_figures.py \
  --arxiv <arxiv_id> <notes_image_dir>
```

This downloads the LaTeX source, extracts original figure files (PNG/JPG/SVG/PDF/EPS), preserves source raster dimensions by default, converts source PDFs to SVG when possible, and only uses high-DPI PNG conversion when vector conversion is unavailable. This avoids the blur introduced by PDF-page crops or downsampled screenshots.

If source extraction returns too few figures, first inspect the arXiv source tree / `.tex` `\includegraphics` paths to find missing assets. Use PDF cropping only as a documented fallback for assets that are not present in the source package (for example, a publisher-only table image).

#### Preserve grouped subfigures from LaTeX source

When the arXiv source places multiple panels under one `figure` caption (e.g. `subfigure`, `subcaptionbox`, `minipage`, `tabular`, or repeated `\includegraphics` with `(a)/(b)/(c)` labels), **preserve that grouped layout in the note**.

- Inspect the relevant `.tex` figure environment whenever extracted filenames look like panels (`fig3a`, `breakdown`, `quant_proxy`) or the caption/text references `Figure 3a/3b/3c`; the source `.tex` is the authority for grouping/layout.
- Preferred output: create one composite file named like `fig3_group.svg` / `fig3_abc.svg` matching the source/PDF layout, then embed it once at normal width.
- Use the helper after extraction when panels are separate files:
  ```bash
  python3 ~/.claude/skills/paper-to-note/scripts/extract_figures.py \
    <notes_image_dir> \
    --compose "fig3_group:row:breakdown.svg,quant_degradation.svg,quant_proxy.svg"
  ```
- Write one combined paragraph such as `Figure 3a–3c 解读：...`, explaining each panel inside the paragraph. **Do not embed grouped panels as three separate full-width images.**
- Only embed individual subpanels separately if the paper treats them as standalone figures; cap each at `width="320"`–`width="450"` or place them side-by-side.

**After writing notes**: delete any extracted figures that are NOT referenced by an `<img>` tag or Obsidian image embed in the final notes. Keep only files that are actually embedded.

#### Figure whitespace QA（必须做）

Before finalizing the note, verify every embedded image is a real figure crop, not a mostly-blank canvas:

- For each referenced PNG/JPG, check pixel dimensions and near-white bounding box. If non-white content uses <70% of image height or width, re-crop/trim the file before saving the note.
- Use a small padding crop (roughly 20–30 px) around the detected non-white content; preserve labels/arrows and do not crop into axes or captions.
- If an image becomes visually tiny in Obsidian despite `width="1000"`, suspect hidden whitespace inside the PNG/PDF crop first; fix the asset, not only the Markdown width.
- Re-open or preview the final embedded figures after trimming. Dimensions alone are not sufficient because PDF page crops often look valid but contain large blank margins.

Helper command:
```bash
python3 ~/.claude/skills/paper-to-note/scripts/extract_figures.py <notes_image_dir> --trim
```
Use `--trim-pad <px>` if labels are close to the edge.

**For non-arxiv papers, or documented arXiv-source misses only (fallback)**: crop individual figures from PDF pages:

```bash
# Crop individual figures (PREFERRED for non-arxiv)
python3 ~/.claude/skills/paper-to-note/scripts/extract_figures.py \
  --pdf <pdf_path> --crop <notes_image_dir> \
  --figures "fig1:4:72,48,540,370" "table1:4:100,490,520,610" "fig2:5:72,48,540,260"
```

Each `--figures` entry format: `name:page:x0,y0,x1,y1` (page is 1-indexed, coordinates in PDF points).

**How to determine crop coordinates**: Read PDF pages with the Read tool to see content layout, then estimate coordinates. Standard PDF page is 612×792 points. Typical margins are 72pt on each side. Iterate: extract, verify with Read tool, re-crop if needed.

```bash
# Full-page rendering (LAST RESORT only — avoid this)
python3 ~/.claude/skills/paper-to-note/scripts/extract_figures.py \
  --pdf <pdf_path> <notes_image_dir> --pages <page_numbers...>
```

The output directory should mirror the current multi-level note category: `/Users/bytedance/Library/CloudStorage/OneDrive-个人/paper_notes/files/<TopCategory>/<SubCategory>/<PaperTitle>/` (or the equivalent `~/OneDrive/paper_notes/files/<TopCategory>/<SubCategory>/<PaperTitle>/` runtime path).

### Step 3: Search for source code (MANDATORY)

**NEVER skip this step. NEVER assume code is unavailable.**

1. Check paper for GitHub links (abstract, footnotes, project page)
2. Use `WebSearch`: `[paper title] github`, `[first author org] [method name] github`
3. If found: use `WebFetch` on the GitHub API tree endpoint to map repo structure
4. **Record the exact branch and commit** — run via Bash:
   ```bash
   gh api repos/<owner>/<repo>/commits/HEAD --jq '(.sha[:8]) + " (" + .commit.author.date[:10] + ")"'
   # e.g. outputs: abc12345 (2026-04-17)
   ```
   Save as `<branch>@<short_sha>` (e.g. `main@abc12345`). This anchors all pseudocode and mapping to a reproducible code state.
5. Read key files: model definition, loss functions, training loop, scheduler
6. If truly not found after searching: note "代码搜索未找到开源实现" in the notes

### Step 4: Read and extract

- Read the full paper carefully (skip references/acknowledgments to save tokens)
- Extract all key formulas from the paper text — do NOT write from memory
- Extract exact numbers from tables — do NOT approximate

### Step 5: Output notes via Obsidian CLI

**Use the Obsidian CLI to create and manage notes.** This ensures proper vault integration (backlinks, tags, search indexing).

**Vault name**: `paper_notes` (current macOS path: `/Users/bytedance/Library/CloudStorage/OneDrive-个人/paper_notes/`; some runtimes may expose the same vault as `/Users/bytedance/OneDrive/paper_notes/`)

#### 5a: Classify into current multi-level category

Always classify into the **actual current multi-level taxonomy**, not the historical flat folders. The taxonomy may change often, so first inspect the live vault categories:

```bash
obsidian vault="paper_notes" folders folder="notes"
# If the CLI output is incomplete, inspect the filesystem too:
find "/Users/bytedance/Library/CloudStorage/OneDrive-个人/paper_notes/notes" -maxdepth 2 -type d | sort
```

Current top-level taxonomy and expected subcategories:

```text
Agent
├── Agentic Systems & Applications
├── Memory
├── Personalization
└── RL
LLM & VLM
├── Pretraining & Architecture
├── Long-Context & Streaming
├── RL & Post-Training
├── Evaluation & Analysis
└── Theory
Multimodal Generation
├── Pretraining & Architecture
├── Video & Audio-Video Generation
├── Acceleration & Distillation
├── RL & Alignment
└── Reasoning & Test-Time Scaling
World Model
├── Long-Horizon Generation
├── Real-Time & Streaming
├── Interactive & Controllable
└── 3D & Multi-View Simulation
Physical AI
├── VLA & World-Action Models
├── Robot Data & Manipulation
├── Physical Video Generation
└── Embodied & Driving Simulation
```

Classification rules:

- Choose exactly one `notes/<TopCategory>/<SubCategory>/` destination using the paper's main contribution, not just keywords in the title.
- Prefer an existing subcategory when it fits. Before creating anything new, compare the paper's **main contribution** against every current top-level/subcategory option above. Create a new subcategory automatically only when you have **high confidence** that the paper's subject is materially outside all existing categories; if confidence is medium/low, choose the closest existing subcategory and note the fit caveat in the final notification instead of expanding the taxonomy. If you create one, also use the matching `files/<TopCategory>/<SubCategory>/<PaperTitle>/` asset path.
- Do not repeat the parent name in the child label (e.g. use `Pretraining & Architecture`, not `VLM Pretraining & Architecture`).
- Frontmatter `tags` must include one hierarchical category tag of the form `paper/<top-slug>/<sub-slug>` plus specific technical tags. Remove stale historical category tags such as `visual-understanding`, `rl-for-visual-generation`, `world-model-long-video-generation`, `multi-modal-generation`, `diffusion-acceleration`, `rl-for-llm-vlm`, and `agent-memory`.

#### 5b: Create the note

Use `obsidian create` with the full note content. The note should use **Obsidian Flavored Markdown**:
- Use `![[fig_name.png]]` Obsidian embed syntax for figures (instead of raw `<img>` tags)
- Use YAML frontmatter properties for metadata
- Use `[[wikilinks]]` for cross-references to other papers in the vault

```bash
obsidian vault="paper_notes" create \
  name="<PaperTitle>" \
  path="notes/<TopCategory>/<SubCategory>/" \
  content="<note_content>" \
  silent
```

**Note**: for long content that exceeds shell argument limits, use the `Write` tool to create the file directly at `/Users/bytedance/Library/CloudStorage/OneDrive-个人/paper_notes/notes/<TopCategory>/<SubCategory>/<PaperTitle>.md`, then use Obsidian CLI to set properties.

#### 5c: Set properties via Obsidian CLI

After creating the note, set structured YAML frontmatter properties:

```bash
obsidian vault="paper_notes" property:set name="authors" value="Name1, Name2" type=text file="<PaperTitle>"
obsidian vault="paper_notes" property:set name="affiliations" value="Univ A, Company B" type=text file="<PaperTitle>"
obsidian vault="paper_notes" property:set name="arxiv" value="XXXX.XXXXX" type=text file="<PaperTitle>"
obsidian vault="paper_notes" property:set name="github" value="https://github.com/..." type=text file="<PaperTitle>"
obsidian vault="paper_notes" property:set name="venue" value="NeurIPS 2025" type=text file="<PaperTitle>"
obsidian vault="paper_notes" property:set name="year" value="2025" type=text file="<PaperTitle>"
obsidian vault="paper_notes" property:set name="tags" value="S2V,benchmark,dataset" type=list file="<PaperTitle>"
obsidian vault="paper_notes" property:set name="github_ref" value="main@abc12345" type=text file="<PaperTitle>"

# 若该论文已有对应的 paper-to-skill skill，追加此属性以便双向跳转
obsidian vault="paper_notes" property:set name="paper_to_skill" value="<skill-name>" type=text file="<PaperTitle>"
```

`github_ref` 格式为 `<branch>@<short_sha>`，如 `main@abc12345`。若无开源代码则省略此属性。

`paper_to_skill` 检测方式：扫描 `~/ai-skills/skills/*/sources.json`，若某个 skill 的 `papers[].id` 或 `papers[].url` 中的 arxiv_id 与当前论文（归一化后，strip `v<N>` / 前缀 `arxiv:`）匹配，则填入该 skill 的目录名。若未找到匹配 skill 则省略此属性。

伪代码：
```python
import json, glob, os, re

def to_arxiv(s):
    """Normalize an arxiv id from either a bare id string or a full URL.
    Examples:
      '2405.01234v2'                         -> '2405.01234'
      'arxiv:2405.01234'                     -> '2405.01234'
      'https://arxiv.org/abs/2405.01234v1'   -> '2405.01234'
    """
    if not s:
        return ""
    s = str(s).lower().replace('arxiv:', '')
    m = re.search(r'arxiv\.org/abs/([^/?#]+)', s)
    if m:
        s = m.group(1)
    return re.sub(r'v\d+$', '', s)

target_arxiv = to_arxiv(this_paper_arxiv)
paper_to_skill_value = None
for sd in glob.glob(os.path.expanduser("~/ai-skills/skills/*/")):
    src_path = os.path.join(sd, "sources.json")
    if not os.path.isfile(src_path):
        continue
    src = json.load(open(src_path))
    for p in src.get("papers", []):
        if to_arxiv(p.get("id", "")) == target_arxiv or to_arxiv(p.get("url", "")) == target_arxiv:
            paper_to_skill_value = os.path.basename(os.path.dirname(sd))
            break
    if paper_to_skill_value:
        break
# 若 paper_to_skill_value 仍为 None，说明该论文暂无对应 skill → 省略该 property
```

#### 5d: Figure embedding

Figures are stored in `/Users/bytedance/Library/CloudStorage/OneDrive-个人/paper_notes/files/<TopCategory>/<SubCategory>/<PaperTitle>/`, mirroring the note category.

In note content, reference figures using relative paths from the note file:
- `<img src="../../../files/<TopCategory>/<SubCategory>/<PaperTitle>/fig_name.png" alt="Figure X" width="1000">`
- Or use Obsidian embeds if the files directory is within vault: `![[fig_name.png|1000]]`

**Wide table hygiene**: do not put long code paths and long hyperparameter lists into one Markdown table row. Obsidian will force awkward column widths and make key values appear as a narrow unreadable strip. For training configs or code mappings with long values, prefer short sections / definition lists:
```
#### RAVEN DMD
- **Config path**: `configs/.../raven.jsonc`
- **Sampling / shape**: `training_steps=220`, ...
- **Optimizer**: backbone LR `2e-6`, ...
```
Use tables only when every cell is short enough to wrap cleanly.

**CRITICAL (P8)**: always leave a **blank line** between `<img>` and the "Figure N 解读" text. Without the blank line, Markdown treats the text as part of an HTML block and `$...$` inline math won't render:
```
<img src="..." alt="Figure 3" width="1000">

Figure 3 解读：由 $K$ 个 reward models 打分…
```

For grouped subfigures (`Figure 3a/3b/3c`, `(a)/(b)/(c)` under one caption), embed **one composite image**:
- `<img src="../../../files/<TopCategory>/<SubCategory>/<PaperTitle>/fig3_group.svg" alt="Figure 3a–3c" width="1000">`
- Follow with `Figure 3a–3c 解读：...` (after a blank line)
- Never place each subpanel as a separate `width="1000"` image unless the original paper shows them as separate figures.

#### 5e: Verify note creation

```bash
obsidian vault="paper_notes" read file="<PaperTitle>"
wc -l "/Users/bytedance/Library/CloudStorage/OneDrive-个人/paper_notes/notes/<TopCategory>/<SubCategory>/<PaperTitle>.md"
```

**Content checklist**:
- **Minimum length**: saved Markdown note is ≥350 lines unless the user explicitly requested a short summary
- **Pseudocode**: based on actual source code, not just paper descriptions
- **Code mapping table**: `| Paper Concept | Source File | Key Class/Function |` (§section-level granularity; line numbers are `paper-to-skill`'s job)
- **Code reference header**: `> **Code reference**: \`branch\` @ \`short_sha\` (date)` appears before the mapping table
- **`github_ref` property**: set via Obsidian CLI (format: `branch@short_sha`)
- **`paper_to_skill` property**: set if matching skill found in `~/ai-skills/skills/`
- **Idea section core insight**: 1–3 sentences stating what's fundamentally new (per P6)
- **Method section intuition paragraph**: at least one prose paragraph explaining *why* it works, not just formulas/code (per P6)
- All 5 sections with substantive content (each with per-section checklist, see "Note Format" above)

**Directory structure** (unchanged):
```
paper_notes/
├── notes/
│   └── <TopCategory>/
│       └── <SubCategory>/
│           └── <PaperTitle>.md          ← reading notes
└── files/
    └── <TopCategory>/
        └── <SubCategory>/
            └── <PaperTitle>/            ← extracted figures (PNG/SVG)
```

**Vault hygiene check (MANDATORY)**: before notifying the user, confirm this run did not create scratch artifacts inside the vault:
```bash
VAULT="/Users/bytedance/Library/CloudStorage/OneDrive-个人/paper_notes"
find "$VAULT" \( -type f \( -name 'review_packet*.md' -o -name 'revew_packet*.md' -o -name 'review-packet*.md' \) -o -type d \( -name tmp -o -name _tmp -o -name _work -o -name 'review_packet*' \) \) -print
```
If the command shows artifacts created by the current run, move them to the external scratch directory or delete them before finalizing. If it shows pre-existing user artifacts, do not create more; mention the pre-existing paths separately.

**Notify the user**: print the top category, subcategory, hierarchical category tag, and the full file path after saving.

### Step 7: Budgeted parallel review and fix (MANDATORY)

After saving, run at least one review round, but keep the review context small.

1. First create an external scratch directory outside the Obsidian vault, then create a compact `review_packet.md` there (≤ ~120 lines by default; hard cap ~200 lines). Use `$PAPER_TO_NOTE_WORKDIR/<paper-slug>/` if set, otherwise `${TMPDIR:-/tmp}/paper-to-note/<paper-slug>/`. Never place the packet next to the note, under `paper_notes/notes/`, under `paper_notes/files/`, or under vault-level `tmp/` / `_tmp` folders. The packet should contain: note path, image directory, paper/PDF path, source repo URL, `github_ref`, figure/table inventory, sections changed, exact unresolved risks, and reviewer scopes requested.
2. Use `$REVIEWER` only as the reviewer instruction source; pass reviewers **file paths + the compact packet**, not the full paper, full note, full prior transcript, full skill text, or full source tree.
3. Reviewer set is **rule-based, not agent-judged**:
   - **Format Reviewer**: ALWAYS run. Checks Mandatory Skeleton items 1–3, code indentation, image paths, `<img>` tags, LaTeX syntax.
   - **Content Reviewer**: ALWAYS run. Checks 5 sections completeness, ≥350-line minimum, per-component pseudocode, results numbers, intuition paragraphs.
   - **Source Code Reviewer**: MANDATORY whenever the paper has a public GitHub repo. The only valid skip condition is the note explicitly says `代码搜索未找到开源实现`. Checks Mandatory Skeleton items 4–5, pseudocode vs actual code, training-config sourcing, paper-vs-code gaps.
   - Do NOT use the prior Low/Normal/High self-classification — it caused notes with public code to silently skip source-code review.
4. Round 1: run all applicable reviewers in parallel (typically 3, or 2 if no public code).
5. Prefer direct parallel reviewers over a nested coordinator. If the runtime only supports a coordinator, the coordinator must not spawn more than these 3 agents and must pass only the compact packet + paths.
6. If `REQUEST_CHANGES`: fix all P0/P1 issues, then run **targeted re-review only** for the affected scope(s). Do not re-run unrelated reviewers.
7. Stop when all applicable scopes are `APPROVE` or only P2 style issues remain. If a second targeted re-review still has P0/P1 issues, notify the user with the remaining blocker instead of repeatedly spawning agents.

This step is non-negotiable for quality, but repeated full-context review is forbidden.

## Quality Rules

- **Formulas must be accurate**: extract from paper, never guess
- **Pseudocode must reflect real implementation**: not a restatement of the abstract
- **If information is missing**: state "论文未详细说明" — never fabricate
- **Result numbers must be exact**: read directly from paper tables
- **Method section must be thorough**: this is where readers get the most value
- **Depth priority**: make Motivation, Idea, and Method detailed and clear first; then cover Experimental Setup and Results with exact but more compact evidence
- **Notes should be as detailed as possible by default**: include all major method details, experiment settings, ablation findings, qualitative observations, and appendix details that affect understanding; only shorten when the user explicitly asks for brevity
- **Minimum note length**: final saved notes must be ≥350 Markdown lines by default; expand with evidence-backed technical content if shorter
- **Detailed does not mean padded**: every added paragraph should explain a concrete mechanism, evidence item, design trade-off, limitation, or reproducibility detail from the paper/code
- **ALWAYS search for code**: even if paper says "will release", search anyway — it may already be public
- **Figures must be included**: at minimum the architecture diagram and key result figures
- **Obsidian math compatibility**: prefer `\boldsymbol{...}` over `\bm{...}` in note formulas; avoid macros that Obsidian/KaTeX commonly renders as raw red text unless the vault is known to support them

## Known Pitfalls — Must Avoid

These are real bugs found in past notes. Check every note against this list.

### P1: Code block closing syntax
- **Bug**: closing a code block with ` ```python ` instead of plain ` ``` `
- **Effect**: everything after the code block gets swallowed into the block, breaking the entire note
- **Rule**: opening fence is ` ```python `, closing fence is ALWAYS just ` ``` ` with nothing after it
- **Check**: after writing notes, verify no closing fence has a language tag

### P2: Full-page PDF screenshots instead of individual figures
- **Bug**: embedding `page_5.png` (a full PDF page) instead of cropping out just `fig2_overview.png`
- **Effect**: figures show irrelevant surrounding text, look unprofessional, waste space, and are often blurry compared with arXiv source assets
- **Rule**: For arXiv papers, ALWAYS run source extraction first and embed original source figures; for non-arXiv papers, extract individual figures/tables/algorithms — never embed full pages
- **How**:
  1. For arxiv papers: use `--arxiv` mode as the default path; it extracts original LaTeX-source figures, preserves source raster dimensions, and prefers vector SVG for source PDFs
  2. Only if a required arXiv figure is missing from the source package, document the miss and use `--pdf --crop` for that specific asset
  3. After extraction, verify each image contains ONLY the figure/table, not surrounding text
  4. Name files descriptively: `fig2_overview.png`, `table1_comparison.png`, `algo1_training.png` — NOT `page_5.png`
- **Cleanup**: after writing notes, delete any extracted images that are NOT referenced by `<img>` tags or Obsidian image embeds

### P3: Missing figures — not all paper figures embedded
- **Bug**: only embedding a few "main" figures while skipping Tables, Algorithms, qualitative comparisons
- **Effect**: notes are incomplete; reader must go back to the PDF to see important visuals
- **Rule**: embed ALL of these when present in the paper:
  - Architecture / overview diagram (mandatory)
  - Key comparison tables (Table with main results)
  - Algorithm pseudocode boxes
  - Qualitative comparison figures
  - Ablation / component analysis figures
  - Application / demo figures
- **Check**: compare the paper's figure/table inventory against what's embedded in notes. If a figure is discussed in text but not embedded, add it.

### P7: Split grouped subfigures into oversized panels
- **Bug**: original arXiv source/PDF shows `Figure 3a/3b/3c` as one row/grid, but the note embeds `fig3a`, `fig3b`, `fig3c` separately at `width="1000"`.
- **Effect**: each panel becomes visually oversized, the original cross-panel comparison is lost, and the Method/Result flow becomes noisy.
- **Rule**: if panels share one figure number/caption in LaTeX, embed one composite `fig<N>_group.svg` / `fig<N>_abc.svg` that preserves the source layout.
- **How**:
  1. Inspect the `.tex` figure environment for `subfigure`, `subcaptionbox`, `minipage`, `tabular`, or repeated `\includegraphics`.
  2. Compose the extracted panel files with `extract_figures.py --compose "fig3_group:row:a.svg,b.svg,c.svg"` or crop the already-combined PDF figure.
  3. Use one `<img ... width="1000">` for the composite plus one `Figure 3a–3c 解读` paragraph.
  4. Delete unreferenced individual panel files unless they are reused elsewhere.
- **Check**: search the final note for adjacent full-width embeds of the same figure number (`Figure 3a`, `Figure 3b`, `Figure 3c`). If found, replace with a grouped composite.

### P5: Missing code version anchor
- **Bug**: pseudocode and mapping table written from code without recording which branch/commit was used
- **Effect**: code may be updated after note-writing; future readers can't tell if notes match current code or an older version
- **Rule**: ALWAYS record `<branch>@<short_sha> (date)` as both a blockquote header before the mapping table and as the `github_ref` Obsidian property
- **How**: `gh api repos/<owner>/<repo>/commits/HEAD --jq '(.sha[:8]) + " (" + .commit.author.date[:10] + ")"'`
- **Check**: confirm `github_ref` property exists in frontmatter and reference blockquote appears before the mapping table

### P4: Shallow section content
- **Bug**: key sections (RL, distillation, data processing) written in <15 lines when the paper has 1-2 pages of detail
- **Effect**: notes lose the most valuable technical depth
- **Rule**: for each paper section that spans ≥1 page, the corresponding note section should have proportional depth. Specifically:
  - If the paper devotes a full section to a topic, the notes should cover: motivation for the design, technical details, key equations/algorithms, and limitations/caveats
  - Don't summarize a 2-page section in 3 bullet points
  - Include appendix material when it contains training configs, extra ablations, prompt/evaluation details, or implementation notes that change interpretation
- **Check**: after writing, scan for any section <10 lines that corresponds to a major paper section; if found, expand it before review unless the paper itself is genuinely terse

### P8: `<img>` tag and text on adjacent lines breaks inline LaTeX
- **Bug**: `<img>` tag on its own line followed by "Figure N 解读" text on the very next line (no blank line in between) causes `$...$` inline math in the text to render as raw text instead of LaTeX
- **Effect**: all inline formulas (`$K$`, `$\ell_k$`, `$\pi_\theta$`, etc.) in figure descriptions display as literal dollar-sign strings
- **Cause**: per CommonMark spec, a standalone `<img>` line starts an HTML block; all subsequent lines until the next blank line are treated as raw HTML, where MathJax/KaTeX delimiters are not processed
- **Rule**: ALWAYS insert a blank line between any `<img>` tag and the following "Figure N 解读" paragraph
- **Good**:
  ```
  <img src="..." alt="Figure 3" width="1000">

  Figure 3 解读：分别由 $K$ 个 reward models 打分…
  ```
- **Bad**:
  ```
  <img src="..." alt="Figure 3" width="1000">
  Figure 3 解读：分别由 $K$ 个 reward models 打分…
  ```
- **Check**: after writing notes, verify no `<img ...>` line is immediately followed by text on the next line without a blank line separator

### P9: Large blank margins inside extracted figures
- **Bug**: a PNG/PDF crop contains the target figure plus huge white margins, so Obsidian shows a small diagram with a large blank area below/around it.
- **Effect**: figures look tiny or leave large vertical gaps even when the Markdown `width` is correct.
- **Rule**: after extraction, run a visual or automated whitespace check for every embedded bitmap. If the content bounding box is much smaller than the canvas, trim the asset itself and keep a small padding.
- **How**:
  1. Detect near-white margins with PIL/ImageMagick or manually preview the image.
  2. Crop to the content bounding box plus 20–30 px padding.
  3. Re-open the cropped image and verify labels/arrows are intact.
- **Check**: any embedded image whose non-white content occupies <70% of image height or width must be inspected and usually re-cropped.

### P10: Wide Markdown tables for training configs
- **Bug**: putting `Stage | Config path | Key values` into one row with long code paths and dozens of hyperparameters.
- **Effect**: Obsidian squeezes one column into a narrow strip, wraps every token vertically, and makes the table unreadable.
- **Rule**: for long configs, use subsections or definition lists instead of wide Markdown tables. Keep the exact config path, but split key values into semantic bullets such as Sampling, Trajectory/Loss, Optimizer, Reward weights.
- **Check**: if a table row contains a path or key-value cell longer than ~120 characters, convert it before saving.

### P11: Obsidian vault pollution by temporary/review artifacts
- **Bug**: saving `review_packet*.md` / `revew_packet*.md`, extracted paper text, reviewer scratch notes, cloned repos, or folders such as `tmp/`, `_tmp/`, `_work/` inside `paper_notes/`.
- **Effect**: Obsidian indexes and displays workflow internals as user-facing notes/folders, polluting search, graph view, and navigation.
- **Rule**: the vault must contain only final reading notes under `notes/` and final referenced figures/assets under `files/`; all review packets and scratch files must live outside the vault in `$PAPER_TO_NOTE_WORKDIR/<paper-slug>/` or `${TMPDIR:-/tmp}/paper-to-note/<paper-slug>/`.
- **Check**: before final response, run the vault hygiene check from Step 5e and remove or move any current-run scratch artifacts found inside the vault.

### P6: Over-codification — note becomes code dump, not reading notes
- **Bug**: Method section becomes a pile of pseudocode blocks with no intuition paragraph; Idea section just says "本文提出了XXX方法" without explaining what's fundamentally new
- **Effect**: Reader finishes the note but still doesn't understand why the paper matters or what the core insight is
- **Rule**: This skill produces **reading notes for humans**, NOT implementation manuals. If the task is line-by-line code mapping / Porting Checklist / Module Interface Contracts, redirect the user to the `paper-to-skill` skill
- **Check**:
  - Idea section MUST contain a core insight (1–3 sentences) stating what's fundamentally different, not a generic summary
  - Method section MUST contain at least one "intuition paragraph" — prose that explains *why* the approach works, not just math or code
  - Code-to-paper mapping granularity is §section-level; line-level (`file:L<a>-L<b>`) is not required here (that's `paper-to-skill`'s job)
