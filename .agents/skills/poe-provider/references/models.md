# Poe Model Catalog

> **⚠️ This catalogue WILL get out of date.** Poe adds and removes models frequently. Always check the live API for current availability, pricing, and feature support:
> ```bash
> # All models with tool support
> curl -s https://api.poe.com/v1/models | jq '.data[] | select(.supported_features | contains(["tools"])) | .id' -r
> ```

---

## Listing Models

### API Endpoint

```
GET https://api.poe.com/v1/models
```

No auth required. Returns all publicly available models.

```bash
# Fetch and filter
curl -s https://api.poe.com/v1/models | jq '.data[].id' -r

# Only models with tool support
curl -s https://api.poe.com/v1/models | jq '.data[] | select(.supported_features | contains(["tools"])) | .id' -r

# Filter by provider
curl -s https://api.poe.com/v1/models | jq '.data[] | select(.owned_by=="Anthropic") | .id' -r

# Filter by input modality
curl -s https://api.poe.com/v1/models | jq '.data[] | select(.architecture.input_modalities | contains(["image"])) | .id' -r

# Full details for a specific model
curl -s https://api.poe.com/v1/models | jq '.data[] | select(.id=="glm-5")'
```

### Response Format

```json
{
  "object": "list",
  "data": [
    {
      "id": "claude-sonnet-4.5",
      "object": "model",
      "owned_by": "Anthropic",
      "architecture": {
        "input_modalities": ["text", "image"],
        "output_modalities": ["text"]
      },
      "pricing": {
        "prompt": "0.0000026",
        "completion": "0.000013",
        "input_cache_read": "0.00000026",
        "input_cache_write": "0.0000032"
      },
      "supported_features": ["web_search", "tools"]
    }
  ]
}
```

Pricing is per-token in USD. Multiply by 1,000,000 for per-1M-token pricing. When `pricing.prompt` is `null`, the model uses per-request pricing (see `pricing.request`). The `supported_features` array indicates capabilities: `"tools"` means tool calling is supported.

---

## Models with Tool Support (by Provider)

> Only models where `supported_features` contains `"tools"` are listed below.
> Models without tool support cannot be used for agent workflows.

### Anthropic

| Model | Input | Price In/Out (per 1M tokens) | Cache Read | Cache Write | Features |
|-------|-------|------------------------------|------------|-------------|----------|
| `claude-opus-4.6` | text, image | $4.30 / $21.00 | $0.43 | $5.30 | web_search, tools |
| `claude-opus-4.5` | text, image | $4.30 / $21.00 | $0.43 | $5.30 | web_search, tools |
| `claude-opus-4.1` | text, image | $13.00 / $64.00 | $1.30 | $16.00 | web_search, tools |
| `claude-opus-4` | text, image | $13.00 / $64.00 | $1.30 | $16.00 | web_search, tools |
| `claude-sonnet-4.6` | text, image | $2.60 / $13.00 | $0.26 | $3.20 | web_search, tools |
| `claude-sonnet-4.5` | text, image | $2.60 / $13.00 | $0.26 | $3.20 | web_search, tools |
| `claude-sonnet-4` | text, image | $2.60 / $13.00 | $0.26 | $3.20 | web_search, tools |
| `claude-sonnet-3.7` | text, image | $2.60 / $13.00 | $0.26 | $3.20 | web_search, tools |
| `claude-haiku-4.5` | text, image | $0.85 / $4.30 | $0.085 | $1.10 | web_search, tools |
| `claude-haiku-3.5` | text, image | $0.68 / $3.40 | $0.068 | $0.85 | web_search, tools |
| `claude-haiku-3` | text, image | $0.21 / $1.10 | $0.021 | $0.26 | tools |

### OpenAI

| Model | Input | Price In/Out (per 1M) | Cache Read | Features |
|-------|-------|-----------------------|------------|----------|
| **GPT-5.4** | | | | |
| `gpt-5.4-pro` | text, image | $27.00 / $160.00 | — | web_search, tools |
| `gpt-5.4` | text, image | $2.20 / $14.00 | $0.22 | web_search, tools |
| `gpt-5.4-mini` | text, image | $0.68 / $4.00 | $0.068 | web_search, tools |
| `gpt-5.4-nano` | text, image | $0.18 / $1.10 | $0.018 | web_search, tools |
| **GPT-5.3** | | | | |
| `gpt-5.3-codex` | text, image | $1.60 / $13.00 | $0.16 | tools |
| `gpt-5.3-codex-spark` | text | **Free** (req) | — | tools |
| `gpt-5.3-instant` | text, image | $1.60 / $13.00 | $0.16 | web_search, tools |
| **GPT-5.2** | | | | |
| `gpt-5.2-pro` | text, image | $19.00 / $150.00 | — | web_search, tools |
| `gpt-5.2` | text, image | $1.60 / $13.00 | $0.16 | web_search, tools |
| `gpt-5.2-codex` | text, image | $1.60 / $13.00 | $0.16 | tools |
| `gpt-5.2-instant` | text, image | $1.60 / $13.00 | $0.16 | web_search, tools |
| **GPT-5.1** | | | | |
| `gpt-5.1-codex-max` | text, image | $1.10 / $9.00 | $0.11 | tools |
| `gpt-5.1-codex` | text, image | $1.10 / $9.00 | $0.11 | tools |
| `gpt-5.1-codex-mini` | text | $0.22 / $1.80 | $0.022 | tools |
| `gpt-5.1` | text, image | $1.10 / $9.00 | $0.11 | web_search, tools |
| `gpt-5.1-instant` | text, image | $1.10 / $9.00 | $0.11 | web_search, tools |
| **GPT-5** | | | | |
| `gpt-5-pro` | text, image | $14.00 / $110.00 | — | web_search, tools |
| `gpt-5` | text, image | $1.10 / $9.00 | $0.11 | web_search, tools |
| `gpt-5-chat` | text, image | $1.10 / $9.00 | $0.11 | web_search, tools |
| `gpt-5-codex` | text, image | $1.10 / $9.00 | — | tools |
| `gpt-5-mini` | text, image | $0.22 / $1.80 | $0.022 | web_search, tools |
| `gpt-5-nano` | text, image | $0.045 / $0.36 | $0.0045 | web_search, tools |
| **Legacy** | | | | |
| `gpt-4.1` | text, image | $1.80 / $7.20 | $0.45 | tools |
| `gpt-4.1-mini` | text, image | $0.36 / $1.40 | $0.090 | tools |
| `gpt-4.1-nano` | text, image | $0.090 / $0.36 | $0.022 | tools |
| `gpt-4o-aug` | text, image | $2.20 / $9.00 | $1.10 | tools |
| `gpt-4o` | text, image | — | — | tools |
| `gpt-4o-mini` | text, image | $0.14 / $0.54 | $0.068 | tools |
| `gpt-4o-search` | text | $2.20 / $9.00 | — | tools |
| `gpt-4o-mini-search` | text | $0.14 / $0.54 | — | tools |
| `gpt-4-turbo` | text, image | $9.00 / $27.00 | — | tools |
| **Reasoning (o-series)** | | | | |
| `o1-pro` | text, image | $140.00 / $540.00 | — | web_search, tools |
| `o1` | text, image | $14.00 / $54.00 | — | tools |
| `o3-pro` | text, image | $18.00 / $72.00 | — | tools |
| `o3-deep-research` | text | $9.00 / $36.00 | $2.20 | web_search, tools |
| `o3` | text, image | $1.80 / $7.20 | $0.45 | tools |
| `o3-mini` | text, image | $0.99 / $4.00 | — | tools |
| `o3-mini-high` | text, image | $0.99 / $4.00 | — | tools |
| `o4-mini-deep-research` | text | $1.80 / $7.20 | $0.45 | web_search, tools |
| `o4-mini` | text, image | $0.99 / $4.00 | $0.25 | tools |

Anything older than what is listed is not recommended.

### Google

| Model | Input | Price In/Out (per 1M) | Cache Read | Features |
|-------|-------|-----------------------|------------|----------|
| `gemini-3.1-pro` | text, image, video, audio | $2.00 / $12.00 | $0.20 | tools |
| `gemini-3-flash` | text, image, video, audio | $0.40 / $2.40 | $0.040 | tools |
| `gemini-3.1-flash-lite` | text, image, video, audio | $0.25 / $1.50 | — | tools |
| `gemini-2.5-pro` | text, image, video, audio | $0.87 / $7.00 | $0.087 | tools |
| `gemini-2.5-flash` | text, image, video, audio | $0.21 / $1.80 | $0.021 | tools |
| `gemini-2.5-flash-lite` | text, image, video, audio | $0.070 / $0.28 | — | tools |
| `gemini-2.0-flash` | text, image, video, audio | $0.10 / $0.42 | — | tools |
| `gemini-2.0-flash-lite` | text, image, video, audio | $0.052 / $0.21 | — | tools |
| `gemma-4-31b` | text, image | **Free** (req) | — | tools |

### XAI

| Model | Input | Price In/Out (per 1M) | Cache Read | Features |
|-------|-------|-----------------------|------------|----------|
| `grok-4.20-multi-agent` | text, image | $2.00 / $6.00 | $0.20 | tools |
| `grok-4` | text, image | $3.00 / $15.00 | $0.75 | tools |
| `grok-4.1-fast-reasoning` | text, image | $0.20 / $0.50 | $0.050 | tools |
| `grok-4.1-fast-non-reasoning` | text, image | $0.20 / $0.50 | $0.050 | tools |
| `grok-4-fast-reasoning` | text, image | $0.20 / $0.50 | $0.050 | tools |
| `grok-4-fast-non-reasoning` | text, image | $0.20 / $0.50 | $0.050 | tools |
| `grok-code-fast-1` | text | $0.20 / $1.50 | $0.020 | tools |
| `grok-3` | text | $3.00 / $15.00 | $0.75 | tools |
| `grok-3-mini` | text | $0.30 / $0.50 | $0.075 | tools |

### Novita AI

**GLM (via Novita):**

| Model | Input | Price In/Out (per 1M) | Cache Read | Max Output | Features |
|-------|-------|-----------------------|------------|------------|----------|
| `glm-5` | text | $1.00 / $3.20 | $0.20 | 131072 | tools |
| `glm-4.7-n` | text | $0.60 / $2.20 | — | 131072 | tools |
| `glm-4.7-flash` | text | $0.070 / $0.40 | $0.010 | 65500 | tools |
| `glm-4.6` | text | $0.55 / $2.20 | $0.11 | 131072 | tools |
| `glm-4.6v` | text, image | $0.30 / $0.90 | $0.055 | 32768 | tools |

**Kimi (via Novita):**

| Model | Input | Price In/Out (per 1M) | Cache Read | Features |
|-------|-------|-----------------------|------------|----------|
| `kimi-k2.5` | text, image, video | $0.60 / $3.00 | $0.10 | tools |
| `kimi-k2-thinking` | text | $0.60 / $2.50 | $0.15 | tools |

**MiniMax (via Novita):**

| Model | Input | Price In/Out (per 1M) | Cache Read | Features |
|-------|-------|-----------------------|------------|----------|
| `minimax-m2.7` | text | $0.30 / $1.20 | $0.060 | tools |
| `minimax-m2.5` | text | $0.30 / $1.20 | $0.030 | tools |
| `minimax-m2.1` | text | $0.30 / $1.20 | $0.030 | tools |

**DeepSeek (via Novita):**

| Model | Input | Price In/Out (per 1M) | Cache Read | Features |
|-------|-------|-----------------------|------------|----------|
| `deepseek-v3.2` | text | $0.27 / $0.40 | $0.13 | tools |

**Other (via Novita):**

| Model | Input | Price In/Out (per 1M) | Cache Read | Features |
|-------|-------|-----------------------|------------|----------|
| `qwen3.5-397b-a17b` | text, image, video | $0.60 / $3.60 | — | tools |
| `qwen3-coder-next` | text | $0.20 / $1.50 | — | tools |
| `mimo-v2-flash` | text | $0.10 / $0.30 | $0.020 | tools |

### Fireworks AI

| Model | Input | Price | Cache Read | Features |
|-------|-------|-------|------------|----------|
| `glm-5.1-fw` | text | $1.40 / $4.40 per 1M | $0.26 | tools |
| `kimi-k2.5-fw` | text, image | **Free** (req) | — | tools |

### CerebrasAI

| Model | Input | Price In/Out (per 1M) | Features |
|-------|-------|-----------------------|----------|
| `gpt-oss-120b-cs` | text | $0.35 / $0.75 | tools |
| `llama-3.1-8b-cs` | text | $0.10 / $0.10 | tools |

### Empirio Labs AI

| Model | Input | Price In/Out (per 1M) | Cache Read | Features |
|-------|-------|-----------------------|------------|----------|
| `nova-premier-1.0` | text, image, video | $3.00 / $15.00 | $1.60 | tools |
| `magistral-medium-2509-thinking` | text, image | $2.60 / $6.50 | — | tools |
| `seed-2.0-pro` | text, image, video | $0.62 / $3.80 | — | tools |
| `mistral-medium-3.1` | text, image | $0.52 / $2.60 | — | tools |
| `nova-lite-2` | text, image, video | $0.38 / $3.20 | $0.21 | tools |
| `seed-2.0-lite` | text, image, video | $0.31 / $2.50 | — | tools |
| `seed-2.0-mini` | text, image, video | $0.12 / $0.50 | — | tools |
| `nova-lite-1.0` | text, image, video | $0.069 / $0.28 | $0.038 | tools |
| `nova-micro-1.0` | text | $0.040 / $0.16 | $0.022 | tools |

### Poe

| Model | Input | Price | Features |
|-------|-------|-------|----------|
| `assistant` | text, image, video | — | web_search, tools |

---

## Cross-Provider Model Index

The same base model may be available through multiple providers at different prices or with different capabilities. **Check `supported_features` via the API** — not all providers enable tool calling for the same model.

### GLM-5.1

| Provider | Model ID | Input | Price (per 1M) | Tools |
|----------|----------|-------|----------------|-------|
| Fireworks AI | `glm-5.1-fw` | text | $1.40 / $4.40 | ✅ |
| Together AI | `glm-5.1-t` | text | Free (req) | ❌ |

### GLM-5

| Provider | Model ID | Input | Price (per 1M) | Tools |
|----------|----------|-------|----------------|-------|
| Novita AI | `glm-5` | text | $1.00 / $3.20 | ✅ |
| Together AI | `glm-5-t` | text | Free (req) | ❌ |

### Kimi K2.5

| Provider | Model ID | Input | Price | Tools |
|----------|----------|-------|-------|-------|
| Novita AI | `kimi-k2.5` | text, image, video | $0.60 / $3.00 per 1M | ✅ |
| Fireworks AI | `kimi-k2.5-fw` | text, image | Free (req) | ✅ |
| Together AI | `kimi-k2.5-tog` | text | $11.00/req | ❌ |

### MiniMax

| Provider | Model ID | Input | Price | Tools |
|----------|----------|-------|-------|-------|
| **M2.7** | | | | |
| Novita AI | `minimax-m2.7` | text | $0.30 / $1.20 per 1M | ✅ |
| **M2.5** | | | | |
| Novita AI | `minimax-m2.5` | text | $0.30 / $1.20 per 1M | ✅ |
| Together AI | `minimax-m2.5-t` | text | $3.90/req | ❌ |

---

## Model Selection Guide

### By Task

| Task | Recommended Models |
|------|-------------------|
| **Coding** | claude-sonnet-4.6, glm-5.1-fw, gpt-5.4 |
| **Fast coding** | minimax-m2.7, kimi-k2.5, grok-code-fast-1 |
| **Complex reasoning** | claude-opus-4.6, o3, gpt-5.4-pro |
| **Long documents** | gemini-3.1-pro, gemini-2.5-pro |
| **Multimodal (vision)** | gemini-3.1-pro, kimi-k2.5, claude-sonnet-4.6 |
| **Cheap/fast** | gpt-5.4-nano, gemini-2.0-flash-lite, glm-4.7-flash |
| **Free** | gpt-5.3-codex-spark, gemma-4-31b, kimi-k2.5-fw |
| **Multi-agent** | grok-4.20-multi-agent |

---

## Best Practices

1. **⚠️ Always check the live API** — this catalogue is a snapshot. Models, pricing, and features change. Use `GET /v1/models` for current data.

2. **Check `supported_features` for tool support** — not all providers enable tool calling for the same base model. Only models with `"tools"` in `supported_features` work for agent workflows.

3. **Check pricing type** — some models use per-token pricing, others per-request. Per-request models show `pricing.prompt: null` with `pricing.request` set.

4. **Use specific providers for the same model** — e.g., `kimi-k2.5-fw` (Fireworks, free, tools) vs `kimi-k2.5-tog` (Together, $11/req, no tools).

5. **Cache the model list** — call `GET /v1/models` once per session/day. The list changes infrequently enough to cache but frequently enough that you must refresh.

6. **Filter by modality** — use `architecture.input_modalities` to find vision-capable models, etc.

7. **Pin versions for production** — model availability and pricing can change.

8. **Check `parameters` for model-specific options** — many models expose `enable_thinking`, `temperature`, and `max_output_tokens` as tunable parameters with documented min/max/default values.
