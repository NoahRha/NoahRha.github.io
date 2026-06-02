# Technical Blog Automation

This repository manages a technical blog and the blog-to-social publishing workflow.
This update focuses on safer, more consistent automation for **image generation**, **parallel social publishing**, and **Korean translation quality checks**.

## What This PR Adds

### 1. Image Generation Policy

The default image generation model is OpenAI `gpt-image-2`.
Local Bonsai and Minimax are fallback or experiment-profile providers, not the default path.

Fallback order:

1. OpenAI `gpt-image-2`
2. Local Bonsai Image 4B
3. Minimax
4. `IMAGE_GENERATION_FAILED`

### 2. Parallel Image Profiles

`scripts/sns/parallel_image_request.py` splits a blog+social image plan into safe parallel batches.

Supported profiles:

- `default`: all assets prefer `gpt-image-2`
- `hybrid`: Threads comic prefers Local Bonsai; all other assets prefer `gpt-image-2`
- `experimental`: channel-specific model assignment for controlled tests

Instagram carousel images are grouped under `instagram-carousel`, so the workflow avoids mixing different models across individual slides.

### 3. Restored Social Publishing Path

`scripts/sns/parallel_sns_publish.py` publishes in this order:

1. Threads first
2. Instagram and Facebook in parallel
3. Combined result reporting

Instagram publishing defaults to carousel mode with 2-10 slides. Single-image publishing requires an explicit `--single` flag.

### 4. Korean Translation Naturalness Gate

`scripts/quality/translation_naturalness_gate.py` checks whether an English-to-Korean blog draft still reads like raw machine translation.

It detects:

- Chinese/Japanese CJK remnants inside Korean text
- Repeated formulaic endings such as `시사합니다`, `전망입니다`, `할 것입니다`, and `가능성이 있습니다`
- Overused untranslated English terms such as `production-ready`, `Robust`, or `Inclusive`

If this gate fails, the draft should go through a `humanize-korean` pass before publishing.

## Security Policy

Never commit:

- API keys
- Meta Graph tokens
- OpenAI keys or OAuth tokens
- `.env` files
- personal memory files
- local workspace state
- generated run logs or temporary outputs

Runtime values must come from local environment files or CI secrets.

Example environment variables:

```bash
META_GRAPH_TOKEN=...
INSTAGRAM_BUSINESS_ACCOUNT_ID=...
INSTAGRAM_PAGE_ID=...
OPENCLAW_ENV_FILE=~/.openclaw/.env
BONSAI_DEMO_DIR=~/.openclaw/Bonsai-Image-Demo
```

## Quick Examples

Build an image request plan:

```bash
python3 scripts/sns/parallel_image_request.py --profile default
```

Run the Korean translation gate:

```bash
python3 scripts/quality/translation_naturalness_gate.py content/posts/example.md
```

Dry-run social publishing:

```bash
python3 scripts/sns/parallel_sns_publish.py \
  --blog-url "https://example.com/posts/demo/" \
  --title "Demo Post" \
  --threads-image "https://example.com/threads.png" \
  --threads-posts "1/3 summary" "2/3 key point" "3/3 link" \
  --ig-images "https://example.com/1.png,https://example.com/2.png" \
  --ig-caption "Instagram caption" \
  --fb-image "https://example.com/cover.png" \
  --fb-summary "Facebook summary" \
  --dry-run
```
