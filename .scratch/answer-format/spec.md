# Reliable structured answers

Status: implemented

## Problem

Some video questions fail with `The model returned an invalid structured answer.`
The UI displays this backend validation error when model output is valid JSON
but does not match VidSage's required answer shape. Malformed JSON and citation
validation have separate errors.

## Agreed behavior

- Ask LiteLLM for provider-supported JSON-schema output when its capability
  metadata says the configured model supports it.
- For models known not to support native structured output, use the existing
  prompt-only JSON request and strict application validation.
- If a provider unexpectedly rejects structured output, fail the request
  clearly. Do not automatically make a second model call.
- Reject the whole invalid response. Do not coerce its shape, display partial
  claims, or weaken caption-evidence/citation validation.
- Show a safe, useful error and retain the existing user-controlled Retry
  action. Never expose raw model output in the UI or logs.

## Acceptance criteria

1. A model marked as supporting response schemas receives the answer schema.
2. A model marked unsupported receives no response-format option and retains
   the existing JSON prompt.
3. A provider rejection of structured output results in one failed call with a
   useful user-safe message and no fallback call.
4. Invalid JSON and valid JSON with invalid answer shape remain rejected with
   distinct safe error messages.
5. Valid answers and insufficient-context responses continue through existing
   exact-source citation validation.
6. The frontend shows the failure and explicit Retry; raw provider output stays
   out of the interface and application logs.
7. Mocked tests cover supported, unsupported, rejection, malformed, invalid,
   and valid responses. No live provider or paid call is part of verification.

## Testing boundary

Mock LiteLLM at the external provider boundary. Tests establish format
selection, call count, validation, and displayed errors, not real provider
compatibility or semantic answer quality. Those require separate owner-led,
price-verified checks.
