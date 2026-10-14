# Video and audit report sources

Everything needed to rebuild the silent walkthrough (`docs/demo/demo.mp4`) and the audit report
(`docs/demo/AUDIT_REPORT.*`) from this repository alone. Paths below are relative to the repo root.

## What is here

| Path | What it is |
|---|---|
| `index.html` | Root of the video: theme (colours, type), and the timing of every slide |
| `compositions/bg.html`, `compositions/chrome.html` | Background grid, and the persistent project label, slide counter and progress bar |
| `compositions/s01-context.html` | Slide 01, the industry and four everyday problems |
| `compositions/s02-hook.html` | Slide 02, the project in one sentence |
| `compositions/explainer.html` | Slides 03-04, the white "how it works" chapter (edit its `CONFIG` block) |
| `compositions/s03-architecture.html` | Slide 05, the architecture diagram (node array `N`, wire array `W`) |
| `compositions/s04-routes.html` | Slide 06, the daily margin plot and the COD policy frontier |
| `compositions/value.html` | Slide 07, the COD decision sheet and checkout scene (data injected by `tools/inject_sheet.py`) |
| `compositions/s05-results.html`, `s06-twist.html`, `s07-end.html` | Slides 08-10, results, what didn't win, end card |
| `assets/plot-daily.png`, `assets/plot-frontier.png` | Dark versions of `outputs/daily_margin.png` and `outputs/policy_frontier.png`, made by `tools/darkmap.py` |
| `assets/cod_sheet.json` | COD decisions for 2025-11-24 (sale week), exported by `tools/export_cod_sheet.py` |
| `audit/facts.yaml` | Every figure (F-xx), assumption (A-xx), slide text and check expression used by the report |
| `tools/build_audit_report.py` | Builds the slide stills, re-checks every figure against the repo outputs, writes MD, DOCX and PDF |
| `tools/export_cod_sheet.py` | Re-runs the repo's own model (same data, seed, split, LightGBM + isotonic) for one day and exports the sheet as JSON |
| `tools/inject_sheet.py` | Inlines that JSON into `compositions/value.html` (renders cannot fetch files) |
| `tools/darkmap.py` | Converts the two matplotlib figures into the dark panels |
| `package.json`, `hyperframes.json`, `meta.json` | HyperFrames project files (CLI pinned to 0.8.156) |

Fonts (Inter, JetBrains Mono, Montserrat) are referenced by name and embedded by the HyperFrames
renderer; all three are SIL Open Font License.

## Requirements

- Node 22 and `npx` (HyperFrames 0.8.156 is fetched by `npx`), plus Chrome/Chromium for rendering.
- `ffmpeg` for compressing the video and extracting slide stills.
- LibreOffice (`soffice`) to convert the report to PDF.
- The repo's own environment (`uv sync`) for `make run` and `export_cod_sheet.py`.
- For `build_audit_report.py`, `inject_sheet.py` and `darkmap.py` (any Python 3.11+, not added to the
  repo's `pyproject.toml`): `pip install pyyaml pandas python-docx pillow numpy matplotlib`.

## Rebuild the numbers, the video and the report

```bash
# 1. repo outputs (about 2 minutes)
make run

# 2. inputs for the video
python3 docs/demo/source/tools/darkmap.py outputs docs/demo/source/assets
PYTHONPATH=src .venv/bin/python docs/demo/source/tools/export_cod_sheet.py docs/demo/source/assets/cod_sheet.json
python3 docs/demo/source/tools/inject_sheet.py docs/demo/source/assets/cod_sheet.json \
  docs/demo/source/compositions/value.html \
  --rows 315400,316055,316096,316229,315744,316309 --animate 315400,316096,316229,315744

# 3. render (85.6 s, 1920x1080, 30 fps, silent) and compress
cd docs/demo/source
npx --yes hyperframes@0.8.156 check
npx --yes hyperframes@0.8.156 render -f 30 -q looks -o renders/order-outcome-margin-master.mp4
cd -
ffmpeg -y -i docs/demo/source/renders/order-outcome-margin-master.mp4 -c:v libx264 -preset slow -crf 25 \
  -pix_fmt yuv420p -movflags +faststart -an docs/demo/demo.mp4

# 4. audit report: slide stills, automated checks, AUDIT_REPORT.md/.docx/.pdf
python3 docs/demo/source/tools/build_audit_report.py docs/demo/source/audit/facts.yaml
```

`build_audit_report.py` exits with code 1 if any figure on screen no longer matches the repo outputs.
`export_cod_sheet.py` also re-scores the whole test window and prints the number of hidden COD orders,
which must equal the 5,498 in `outputs/policy.csv` (audit check F-42).

The `renders/` folder (about 14 MB) is not committed; step 3 recreates it.
