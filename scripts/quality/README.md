# Track-B Quality Module

Translation-quality and image-quality scorers, plus a 2-stage review
orchestrator. Stage 1 is fully deterministic (no LLM cost, no network) so
the audit runs in CI; Stage 2 is the existing LLM (Claude 1st / GPT
fallback) review per `agents/blogger/AGENT.md`.

## What's in here

| File | Purpose |
| --- | --- |
| `translation_checker.py` | Score a blog `.md` post 0..100 across 5 dimensions. |
| `image_checker.py` | Score a folder of blog/SNS images 0..100 across 5 dimensions. |
| `review_orchestrator.py` | Run both stage-1 checks; only invoke the LLM if they pass. |
| `../tests/test_quality_*.py` | 72 pytest cases. Run with `pytest -v scripts/tests/test_quality_*.py`. |
| `../tests/_quality_helpers.py` | Shared `clean_post_body`, `tiny_post_body`, `make_png` fixtures. |

## CLI quick reference

```bash
# Translation only (stage 1)
python3 scripts/quality/translation_checker.py \
  --post content/posts/spacex-google-ai-chip-deal-ipo.md \
  --source-url https://the-decoder.com/.../ \
  --json

# Image folder only (stage 1)
python3 scripts/quality/image_checker.py \
  --image-dir static/images/spacex-google-ai-chip-deal-ipo/ \
  --style hand-drawing \
  --image-plan data/image-plans/spacex-google-ai-chip-deal-ipo.json \
  --json

# 2-stage review
python3 scripts/quality/review_orchestrator.py review-all \
  --slug spacex-google-ai-chip-deal-ipo \
  --post content/posts/spacex-google-ai-chip-deal-ipo.md \
  --source-url https://the-decoder.com/.../ \
  --image-dir static/images/spacex-google-ai-chip-deal-ipo/ \
  --style hand-drawing \
  --json
```

## Scoring weights

### `translation_checker.py` (default threshold 70)

| Category | What it catches | Deduct |
| --- | --- | --- |
| Translation tells | `이는 …이다`, `이러한 …은`, `다음과 같은`, `~로 알려져 있다`, `~라 할 수 있다`, `~라고 할 수 있다`, `~라고 생각된다`, `~것으로 판단된다`, `또한`, `그리고`, `그러나`, `따라서`, `즉,`, `저는/제가/저의` | 1-4 per match, capped at 4×/pattern |
| English leftover | `The following`, `In this article`, `As mentioned above`, `It is worth noting`, `In conclusion`, `First and foremost` | 3-5 per match, capped at 3×/pattern |
| Word repetition | Same content word 5+ times; harsher on small posts | `min((count-4)*2, 12)` per word, +4 if post < 2000 chars |
| Sentence rhythm | Short (<18c) sentences >50% of total, or long (>200c) >25% | 15 × ratio |
| Paragraph structure | 5+ line paragraphs (3× each), bad intros in ≥1/3 of paragraphs (4× each) | 3-4 per occurrence |
| Fact grounding | Numeric figure in post that's not in the source | 3-15 per figure (network/timeout = no penalty) |

### `image_checker.py` (default threshold 80)

| Category | What it catches | Deduct |
| --- | --- | --- |
| File integrity | 0-byte file, bad magic bytes, truncated IEND, <5KB placeholder | 30 per hard issue / 8 per soft issue per image |
| Visual placeholder | Mean RGB monochrome black/white (max-min ≤12, R<8 or R>247) | 30 per image |
| Aspect ratio | not 1:1 (±5%) or side not 1024±5% / 1080±5% | 30 per image |
| Dedup (global) | SHA-256 appears in 5+ images | 50 (huge penalty) |
| Visual diversity | max pairwise RGB distance < 30 (over all images) | 12 (warning if < 60) |
| Style consistency | per-asset `style` field != requested, or prompt missing `hand-drawn`/`oil painting` prefix | 20 per asset |

## Interpreting scores

- **90-100** — publishable; the orchestrator will only block on a real LLM
  flag.
- **70-89** — fixable; the issues list is concrete. Run humanize-korean or
  regenerate images.
- **<70 (translation) / <80 (images)** — gate fails. Treat as a hard
  blocker: the workflow_guard `audit` will refuse to advance.

## False positive 보정 (Tuning)

The defaults err on the side of strictness (because Track-A failures have
been silently inflating shipping time). If a specific heuristic misfires
in your writing style:

1. **Add a new entry to `KR_TRANSLATION_TELLS` with weight `0`** to silence
   a pattern without losing the data. Weight 0 still records hits in the
   `issues` list but does not deduct.
2. **Override the threshold per-call** with `--min-score`. CI can use
   `--min-score 80` to be strict; a human-in-the-loop pass can use
   `--min-score 50` to highlight rather than block.
3. **For images**: provide `--image-plan` JSON so the style check is
   measured against the actual asset plan, not a per-image guess.

## Wiring into `blog_workflow_guard`

Set `QUALITY_HOOK=enabled` to activate. Default is **OFF** so the
parallel Track A (resilience) commit does not collide on the audit path.
Once both branches are merged, flip the env var in the orchestrator
configuration.

```bash
# Activate quality gate for the next audit
export QUALITY_HOOK=enabled
python3 scripts/blog_workflow_guard.py audit --slug <slug> --stage draft
```

When active, `cmd_audit` calls `review_orchestrator` at the end of `draft`
(translation) and `images` (image folder) stages. Sub-threshold scores
produce error lines in the audit JSON and an exit code of 1.

## Design notes

- **No LLM dependency** — `translation_checker` and `image_checker` are
  pure-Python + PIL. The orchestrator's LLM step is an *optional* thin
  wrapper that calls `claude` / `openai` CLIs and degrades gracefully.
- **Deterministic scores** — same input → same output, every time. CI can
  diff scores across runs.
- **No `agents/blogger/AGENT.md` touched** — this module is a *mechanism*
  for the policy that already lives in that file, not a replacement.
- **No PIL/Pillow regressions** — uses only `PIL.Image`; no
  `image_gen` / no Anthropic / OpenAI SDK at scoring time.
