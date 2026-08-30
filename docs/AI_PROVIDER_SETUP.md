# AI Provider Setup

One switch selects the reasoning engine. Everything downstream is unchanged,
because every provider returns the same validated `BobAnalysis` contract.

```bash
AI_PRIMARY_PROVIDER=ibm-bob      # or watsonx | anthropic | gemini | host | manual
AI_FALLBACK_PROVIDER=gemini
AI_FALLBACK_ENABLED=true
```

`KUBEMEDIC_REASONING_PROVIDER` is the older name and still works; `auto` picks
the first configured engine in order, ending at `host`.

---

## Status, as tested on 2026-08-30

| Provider | Status | Evidence |
|---|---|---|
| **IBM watsonx** | **AUTHENTICATION OK, SERVICE INACTIVE** | IAM token exchange succeeds; deployment list succeeds; inference returns `403 invalid_instance_status_error` — the WML instance behind the deployment is Inactive and cannot be reactivated on this account |
| **IBM Bob** | **UNVERIFIED / AUTHENTICATION FAILURE** | See below |
| **Gemini** | **VERIFIED WORKING** | Live analysis returned in ~14s on `gemini-3.6-flash`: ranked hypothesis, root cause labelled as inference, contradicting evidence, and `rollback_deployment -> ticket-booking {to_revision: 11}` |
| **Host IDE** | **CONFIGURED** | Detects Claude Code / Bob IDE / Antigravity; verified working in this workspace |

**Gemini has produced live analyses**; the IBM engines have not. Records from
a Gemini run read `analysis_source: "gemini"`. IBM records still read
`"unavailable"`.

Two bugs a live model found that no fixture had:

1. `BobAnalysis.from_raw` crashed with `TypeError: unhashable type` when the
   model returned an object for `recommended_action` instead of a string. It
   now refuses cleanly.
2. The prompt named the schema by **file path** -- which a hosted model cannot
   open -- so the model invented its own field names. The required shape is
   now stated inline.

### IBM Bob — what probing established

Tested with a real Inference-scoped key from the Bob console:

| Host | Result |
|---|---|
| `cloud.manufact.com` | Cloudflare blocks urllib's default user-agent with `403 error code: 1010`. With a browser User-Agent it reaches the API and returns a genuine **401 Unauthorized** on every path tried — `/api/v1/chats`, `/agents`, `/me`, `/models`, `/chat/completions` — with both `x-api-key` and `Authorization: Bearer` |
| `bob.ibm.com` | **404 HTML** on every API path. It is the web console, not the API host |

An Inference-scoped key is *"scoped to a specific instance"*, so the base URL is
most likely instance-specific and neither of the above.

---

## Configuring each provider

### IBM watsonx

```bash
export KUBEMEDIC_WATSONX_API_KEY="..."        # IBM Cloud IAM key
export KUBEMEDIC_WATSONX_PROJECT_ID="..."
export KUBEMEDIC_WATSONX_URL="https://us-south.ml.cloud.ibm.com"
export KUBEMEDIC_WATSONX_MODEL_ID="ibm/granite-3-8b-instruct"
```

Test: `python -m agent.cli providers`

### IBM Bob

```bash
export KUBEMEDIC_BOB_API_KEY="..."
export KUBEMEDIC_BOB_AGENT_ID="..."
export KUBEMEDIC_BOB_API_BASE="https://<your-instance>"
```

### Gemini

```bash
export GEMINI_API_KEY="..."        # from https://aistudio.google.com/apikey
export GEMINI_MODEL="gemini-3.6-flash"
export AI_FALLBACK_ENABLED=true
```

No SDK is required — the provider calls the REST endpoint directly, and the key
travels in the `x-goog-api-key` header so it cannot land in a URL or proxy log.

### Host IDE — needs no credentials

```bash
export AI_PRIMARY_PROVIDER=host
```

The pipeline writes `.kubemedic/reasoning-request.md`; the agentic IDE hosting
the workspace answers into `.kubemedic/reasoning-response.json`; the answer is
validated exactly as a headless one. In the IBM Bob IDE the record is stamped
`ibm-bob`, because it genuinely is Bob.

---

## How fallback works

```
primary provider
   ├── answers            -> use it
   └── fails (401, timeout, unparseable, unconfigured)
          ├── AI_FALLBACK_ENABLED=false -> return the failure
          └── true -> try AI_FALLBACK_PROVIDER
```

Two rules it follows deliberately:

**A failure is never swallowed.** The reason the primary could not answer is
logged and carried into the result, so an audit record shows that IBM was tried
and why it did not answer — not merely that something else spoke:

```
IBM provider unavailable: authentication failed.
Falling back to gemini because AI_FALLBACK_ENABLED=true.
```

**A failure is never retried in place.** An invalid credential is invalid on the
second attempt too; retrying turns one clear 401 into a retry storm against
someone else's service.

No credential is ever logged: `_invocation()` excludes both the prompt (it
carries cluster detail) and the key, and `agent/secrets.py:redact()` reports
short secrets as present rather than revealing a prefix.

## Health

```bash
curl localhost:8100/health/ai
```

```json
{
  "primary_provider": "ibm-bob",
  "primary_status": "not_configured",
  "fallback_provider": "gemini",
  "fallback_status": "available",
  "fallback_enabled": true,
  "active_provider": "gemini"
}
```

It never probes the network — a health endpoint that calls a model API turns a
slow third party into a red dashboard — and never returns a credential, only
whether one is present.
