# 01: Diagnose invalid video overview answers

Status: open

## Problem

A video overview request still fails on the integration branch after native
JSON schema support was added. The generic error hides which answer rule failed.

## Acceptance criteria

- Verify that the configured Groq model receives the strict schema at the HTTP boundary.
- Explain the app's claim and evidence requirements in the generation prompt.
- Identify the failed rule using fixed, safe error text. Keep the failed answer
  out of the conversation and retain the existing explicit Retry action.
- Verify the change with synthetic model responses. Keep live verification
  under the owner's control, as described in the [specification](../spec.md).

## Findings

An HTTP mock confirmed the installed LiteLLM Groq adapter sends the strict
schema unchanged. The schema defines object fields and types. The app also
checks nonblank text, claim and evidence counts, and consistency between the
outcome and claim list. The prompt now states those rules and validation
reports which rule failed using fixed messages.

The dependency and compilation checks and all 105 deterministic tests passed.
The original response is unavailable. Keep this ticket open until the owner
repeats the overview request and either gets a cited answer or captures the
more precise error.
