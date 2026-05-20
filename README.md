# Paper-to-Note: AI Agent Skill for Academic Paper Reading Notes

An AI agent skill that generates high-quality, structured reading notes for academic papers. Designed for use with Claude Code, Cursor, Codex, and other AI coding assistants that support the skill/agent framework.

## What It Does

Given a paper (PDF, arXiv link, or title), the skill instructs an AI agent to:

1. **Download and read** the full paper
2. **Extract figures** from arXiv LaTeX source by default (PDF crops only as fallback, with automatic SVG/PNG conversion)
3. **Search for source code** on GitHub (mandatory — never assumes code is unavailable)
4. **Generate structured Chinese notes** with 5 sections: Motivation, Idea, Method, Experimental Setup, Results
5. **Write Python/PyTorch pseudocode** based on actual source code (not paper abstractions)
6. **Run parallel quality review** (Format + Content + Source Code reviewers)
7. **Save to Obsidian vault** with proper frontmatter, tags, and figure embeds

## Output Quality

- All math formulas in LaTeX
- Pseudocode reflects real implementation (verified against source code)
- Code-to-paper mapping table with commit SHA anchoring
- Figures extracted as original arXiv source assets when available (not blurry full-page screenshots)
- Parallel 3-reviewer quality check catches factual errors and structural gaps

## Installation

### For Claude Code

```bash
# Clone to your skills directory
git clone https://github.com/liming-ai/paper-to-note.git ~/.claude/skills/paper-to-note

# Copy shared resources (if not already present)
cp -rn ~/.claude/skills/paper-to-note/_shared ~/.claude/skills/_shared
```

### For Cursor / Codex / Other Runtimes

```bash
# Clone to the shared agents skills directory
git clone https://github.com/liming-ai/paper-to-note.git ~/.agents/skills/paper-to-note

# Copy shared resources (if not already present)
cp -rn ~/.agents/skills/paper-to-note/_shared ~/.agents/skills/_shared
```

### Dependencies

```bash
# Required: figure extraction from PDF
pip install pymupdf Pillow

# Required: Obsidian vault management
# Install obsidian-cli: https://github.com/Yakitrak/obsidian-cli
brew install yakitrak/yakitrak/obsidian  # macOS
# Or download from GitHub Releases for other platforms

# Required: GitHub API access (for source code search & commit anchoring)
# Install gh CLI: https://cli.github.com/
brew install gh  # macOS
# apt install gh  # Linux

# Optional: source PDF/EPS→SVG vector conversion (higher quality figures)
brew install pdf2svg  # macOS
# apt install pdf2svg  # Linux

# Optional: EPS source figure conversion fallback
brew install ghostscript imagemagick
```

### Configuration (IMPORTANT)

After installation, open `SKILL.md` and update the **User Configuration** section at the top:

| Variable | What to set |
|----------|-------------|
| `VAULT_NAME` | Your Obsidian vault name (as shown in Obsidian app) |
| `VAULT_PATH` | Absolute path to your vault (e.g. `~/Documents/my_papers`) |
| `PAPERS_DIR` | Where to store downloaded PDFs (e.g. `~/papers`) |
| `SKILLS_DIR` | Path to paper-to-skill output (optional, can ignore if not using paper-to-skill) |

Then create the required directories:

```bash
mkdir -p $PAPERS_DIR
mkdir -p $VAULT_PATH/notes
mkdir -p $VAULT_PATH/files
```

Verify obsidian-cli can find your vault:

```bash
obsidian vault="YOUR_VAULT_NAME" folders
```

## Directory Structure

```
paper-to-note/
├── SKILL.md                     # Main skill definition (instructions for the AI agent)
├── agents/
│   └── paper-to-note-reviewer.md  # Quality reviewer agent definition
├── scripts/
│   ├── extract_figures.py       # Figure extraction tool (arxiv/PDF/compose/auto-width modes)
│   └── calibrate_widths.py      # Vault-wide figure width and centering audit/fix tool
├── _shared/                     # Shared infrastructure with paper-to-skill
│   ├── commit-anchor.md         # Commit SHA anchoring format spec
│   ├── pseudocode-rules.md      # Pseudocode quality rules
│   ├── known-categories.md      # Obsidian category taxonomy
│   └── reviewer-base.md         # Reviewer output format & severity definitions
└── README.md
```

## Usage

Once installed, the skill is automatically triggered when you ask the AI agent to read a paper:

```
> 帮我读一下这篇论文 https://arxiv.org/abs/2504.xxxxx
> Read this paper and generate notes: [paper title]
> 帮我做一下这篇论文的笔记 [PDF path]
```

### Output Location (Customizable)

By default, notes are saved to (paths configurable in `SKILL.md`):
- Notes: `$VAULT_PATH/notes/<Category>/<PaperTitle>.md`
- Figures: `$VAULT_PATH/files/<Category>/<PaperTitle>/`

See the **Configuration** section below to set your paths.

## Figure Extraction Modes

The `scripts/extract_figures.py` supports three modes:

```bash
# 1. arxiv source (preferred — extracts original high-res figures)
python scripts/extract_figures.py --arxiv 2504.12345 ./output_dir

# 2. PDF crop (for non-arxiv papers)
python scripts/extract_figures.py --pdf paper.pdf --crop ./output_dir \
  --figures "fig1:4:72,48,540,370" "table1:5:100,490,520,610"

# 3. Recommend adaptive embed widths
python scripts/extract_figures.py --auto-width ./output_dir

# 4. Compose grouped subfigures into one SVG
python scripts/extract_figures.py ./output_dir \
  --compose "fig3_group:row:panel_a.svg,panel_b.svg,panel_c.svg"
```

Use `scripts/calibrate_widths.py --auto-center --tolerance 0` to audit existing notes for width drift, broken figure references, and uncentered `<img>` embeds.

## Customization

### Change Language

The skill generates Chinese notes by default. To change:
- Modify the "Language Rules" section in `SKILL.md`

### Add Categories

Edit `_shared/known-categories.md` to add your research categories.

### Skip Obsidian CLI

If you don't use Obsidian or prefer plain markdown files, you can modify Step 5 in `SKILL.md` to use the `Write` tool directly instead of `obsidian` commands. The note content format remains the same.

## Related

- **paper-to-skill**: A companion skill that generates implementation-ready engineering manuals from papers (code-level mapping, porting checklists, module interface contracts). Best workflow: use `paper-to-note` first to understand the paper, then `paper-to-skill` to extract engineering details.

## License

MIT
