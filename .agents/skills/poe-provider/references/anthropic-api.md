# Poe Anthropic-Compatible API Reference

Drop-in replacement for the Anthropic Messages API. Use your Poe API key and subscription points to access Claude models through the same request/response format that the Anthropic SDK uses.

---

## Endpoint

```
POST https://api.poe.com/v1/messages
```

Requests are proxied directly to Anthropic with minimal transformation — this is not a reimplementation, it's a pass-through. Only official Anthropic models are supported on this endpoint. For custom bots or other providers, use the Responses API or the OpenAI-compatible Chat Completions API instead.

---

## Authentication

Two methods are supported. If both are provided, `x-api-key` takes precedence.

### x-api-key header (Anthropic standard)

```bash
curl "https://api.poe.com/v1/messages" \
  -H "x-api-key: $POE_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json"
```

### Authorization: Bearer header

For tools that use Bearer token authentication:

```bash
curl "https://api.poe.com/v1/messages" \
  -H "Authorization: Bearer $POE_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json"
```

---

## Claude Code Setup

Set two environment variables to route Claude Code through Poe:

```bash
export ANTHROPIC_API_KEY=$POE_API_KEY
export ANTHROPIC_BASE_URL="https://api.poe.com"
```

Then restart Claude Code. Verify with the `/status` command.

---

## Request Format

### Minimal Request

```json
{
  "model": "claude-sonnet-4-6",
  "max_tokens": 1024,
  "messages": [
    {"role": "user", "content": "Hello"}
  ]
}
```

### Full Request

```json
{
  "model": "claude-sonnet-4-6",
  "max_tokens": 4096,
  "messages": [
    {"role": "user", "content": "Explain quantum computing"}
  ],
  "system": "You are a helpful physics tutor.",
  "temperature": 0.7,
  "top_p": 1.0,
  "stream": false,
  "stop_sequences": ["\n\nEND"]
}
```

---

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | string | Required | Model identifier (see model table below) |
| `max_tokens` | int | Required | Maximum tokens in the response |
| `messages` | array | Required | Conversation messages |
| `system` | string/array | null | System prompt |
| `temperature` | float | 1.0 | Sampling randomness (0.0–1.0) |
| `top_p` | float | null | Nucleus sampling |
| `top_k` | int | null | Top-K sampling |
| `stream` | boolean | false | Stream response with SSE |
| `stop_sequences` | array | null | Custom stop sequences (max 10) |
| `metadata` | object | null | User metadata (user_id) |
| `tools` | array | null | Tool definitions |
| `tool_choice` | object/string | null | Tool selection strategy |

### system Parameter

Can be a plain string or a structured array for multi-part system prompts:

```json
"system": [
  {"type": "text", "text": "You are a helpful assistant."},
  {"type": "text", "text": "Always respond in French.", "cache_control": {"type": "ephemeral"}}
]
```

### Temperature vs Top-P

Use `temperature` **or** `top_p`, not both simultaneously — combining them can produce unexpected results.

---

## Message Format

### Roles

| Role | Description |
|------|-------------|
| `user` | Human messages |
| `assistant` | AI responses (for multi-turn) |

Unlike the OpenAI Chat Completions API, Anthropic's Messages API does **not** use a `system` role inside the messages array. System prompts go in the top-level `system` field instead.

### Text Content

```json
{"role": "user", "content": "What is machine learning?"}
```

### Multimodal Content (Images)

```json
{
  "role": "user",
  "content": [
    {"type": "text", "text": "What's in this image?"},
    {
      "type": "image",
      "source": {
        "type": "base64",
        "media_type": "image/png",
        "data": "iVBORw0KGgoAAAANSUhEUg..."
      }
    }
  ]
}
```

Or by URL:

```json
{
  "type": "image",
  "source": {
    "type": "url",
    "url": "https://example.com/photo.jpg"
  }
}
```

Supported image types: `image/png`, `image/jpeg`, `image/gif`, `image/webp`.

### Multi-Turn Conversation

```json
"messages": [
  {"role": "user", "content": "What is Python?"},
  {"role": "assistant", "content": "Python is a programming language."},
  {"role": "user", "content": "What can I build with it?"}
]
```

---

## Tool Use

### Defining Tools

```json
{
  "model": "claude-sonnet-4-6",
  "max_tokens": 4096,
  "tools": [
    {
      "name": "get_weather",
      "description": "Get current weather for a location",
      "input_schema": {
        "type": "object",
        "properties": {
          "location": {
            "type": "string",
            "description": "City name"
          },
          "unit": {
            "type": "string",
            "enum": ["celsius", "fahrenheit"],
            "description": "Temperature unit"
          }
        },
        "required": ["location"]
      }
    }
  ],
  "messages": [
    {"role": "user", "content": "What's the weather in Paris?"}
  ]
}
```

### Tool Use Response

When the model wants to call a tool:

```json
{
  "content": [
    {
      "type": "text",
      "text": "I'll check the weather in Paris for you."
    },
    {
      "type": "tool_use",
      "id": "toolu_01A09q90qw90lq917835lq9",
      "name": "get_weather",
      "input": {"location": "Paris", "unit": "celsius"}
    }
  ],
  "stop_reason": "tool_use",
  "model": "claude-sonnet-4-6",
  "usage": {
    "input_tokens": 250,
    "output_tokens": 50
  }
}
```

### Continuing After Tool Use

Send the tool result back as a `tool_result` content block in a `user` message:

```json
"messages": [
  {"role": "user", "content": "What's the weather in Paris?"},
  {"role": "assistant", "content": [
    {"type": "tool_use", "id": "toolu_01A09q90qw90lq917835lq9", "name": "get_weather", "input": {"location": "Paris", "unit": "celsius"}}
  ]},
  {"role": "user", "content": [
    {
      "type": "tool_result",
      "tool_use_id": "toolu_01A09q90qw90lq917835lq9",
      "content": "{\"temperature\": 22, \"conditions\": \"Sunny\"}"
    }
  ]}
]
```

### tool_choice Options

| Value | Behavior |
|-------|----------|
| `"auto"` | Model decides whether to use tools (default) |
| `"any"` | Model must use at least one tool |
| `{"type": "tool", "name": "get_weather"}` | Force a specific tool |

---

## Response Format

### Non-Streaming

```json
{
  "id": "msg_01XFDUDYJhyAAC8vn8option",
  "type": "message",
  "role": "assistant",
  "content": [
    {
      "type": "text",
      "text": "Hello! How can I help you today?"
    }
  ],
  "model": "claude-sonnet-4-6",
  "stop_reason": "end_turn",
  "stop_sequence": null,
  "usage": {
    "input_tokens": 10,
    "output_tokens": 15
  }
}
```

### Stop Reasons

| Reason | Meaning |
|--------|---------|
| `end_turn` | Natural end of response |
| `max_tokens` | Hit `max_tokens` limit |
| `stop_sequence` | Hit a custom stop sequence |
| `tool_use` | Model requested tool execution |

---

## Streaming

### Request

Set `stream: true`:

```json
{
  "model": "claude-sonnet-4-6",
  "max_tokens": 1024,
  "stream": true,
  "messages": [
    {"role": "user", "content": "Write a haiku about coding"}
  ]
}
```

### Streaming Response Format

Server-Sent Events with these event types:

```
event: message_start
data: {"type": "message_start", "message": {"id": "msg_...", "type": "message", "role": "assistant", "content": [], "model": "claude-sonnet-4-6", "usage": {"input_tokens": 10, "output_tokens": 0}}}

event: content_block_start
data: {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}

event: content_block_delta
data: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello"}}

event: content_block_delta
data: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": " world"}}

event: content_block_stop
data: {"type": "content_block_stop", "index": 0}

event: message_delta
data: {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 50}}

event: message_stop
data: {"type": "message_stop"}
```

### SSE Event Types

| Event | Description |
|-------|-------------|
| `message_start` | Beginning of response, includes metadata |
| `content_block_start` | New content block beginning |
| `content_block_delta` | Incremental content (text or tool input) |
| `content_block_stop` | Content block complete |
| `message_delta` | Stop reason and final usage |
| `message_stop` | Response complete |
| `ping` | Keep-alive |

### Client Implementation

```typescript
async function* streamMessages(messages: any[], model: string) {
  const response = await fetch('https://api.poe.com/v1/messages', {
    method: 'POST',
    headers: {
      'x-api-key': process.env.POE_API_KEY!,
      'anthropic-version': '2023-06-01',
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      model,
      max_tokens: 4096,
      stream: true,
      messages
    })
  });

  const reader = response.body?.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (reader) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6);
        try {
          const parsed = JSON.parse(data);
          if (parsed.type === 'content_block_delta') {
            yield parsed.delta;
          }
        } catch {}
      }
    }
  }
}

// Usage
for await (const delta of streamMessages(
  [{ role: 'user', content: 'Hello' }],
  'claude-sonnet-4-6'
)) {
  if (delta.type === 'text_delta') {
    process.stdout.write(delta.text);
  }
}
```

---

## Error Format

Errors follow Anthropic's error format:

```json
{
  "type": "error",
  "error": {
    "type": "authentication_error",
    "message": "Invalid API key"
  }
}
```

### Error Types

| Type | Status | Description |
|------|--------|-------------|
| `authentication_error` | 401 | Invalid API key |
| `permission_error` | 403 | Insufficient subscription |
| `not_found_error` | 404 | Model not found |
| `rate_limit_error` | 429 | Too many requests |
| `invalid_request_error` | 400 | Malformed request |
| `api_error` | 500 | Server error |

### Streaming Errors

If an error occurs mid-stream, an SSE error event is sent before the stream closes:

```
event: error
data: {"type": "error", "error": {"type": "api_error", "message": "An error occurred"}}
```

---

## Supported Models

Use either the Poe bot name or the Anthropic API model name:

| Anthropic API Name | Poe Bot Name | Description |
|--------------------|-------------|-------------|
| `claude-sonnet-4-6` | `claude-sonnet-4.6` | Claude Sonnet 4.6 |
| `claude-opus-4-6` | `claude-opus-4.6` | Claude Opus 4.6 |
| `claude-haiku-4-5` | `claude-haiku-4.5` | Claude Haiku 4.5 |

Only official Anthropic models are available on this endpoint. For custom bots or other providers, use the Responses API or OpenAI-compatible Chat Completions API.

---

## Rate Limits

**500 requests per minute (rpm)**

### Rate Limit Headers

| Header | Description |
|--------|-------------|
| `x-ratelimit-limit-requests` | Max requests per time window (500) |
| `x-ratelimit-remaining-requests` | Remaining requests in current window |
| `x-ratelimit-reset-requests` | Seconds until rate limit resets |

When rate limited, you receive HTTP 429 with `rate_limit_error`.

**Retry strategy**: Use exponential backoff starting at 250ms with jitter. Check the rate limit headers to proactively avoid hitting limits.

---

## Anthropic SDK Compatibility

Since this is a pass-through to the Anthropic API, the official Anthropic SDKs work with just a base URL change.

### Python

```python
import anthropic

client = anthropic.Anthropic(
    api_key=os.environ.get("POE_API_KEY"),
    base_url="https://api.poe.com"
)

message = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    messages=[
        {"role": "user", "content": "Hello, Claude!"}
    ]
)
```

### TypeScript

```typescript
import Anthropic from '@anthropic-ai/sdk';

const client = new Anthropic({
  apiKey: process.env.POE_API_KEY,
  baseURL: 'https://api.poe.com'
});

const message = await client.messages.create({
  model: 'claude-sonnet-4-6',
  max_tokens: 1024,
  messages: [
    { role: 'user', content: 'Hello, Claude!' }
  ]
});
```

---

## Migration Checklist (Anthropic → Poe)

1. **Swap base URL**: `https://api.anthropic.com` → `https://api.poe.com`
2. **Replace API key**: `ANTHROPIC_API_KEY` → `POE_API_KEY`
3. **Run your code** — Everything else stays the same

No other changes needed. Request/response formats, streaming events, tool use, and error handling are identical to the Anthropic API.