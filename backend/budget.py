"""Conservative reservations; never treat missing provider usage as free."""
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlsplit
import json
import math
from threading import BoundedSemaphore

from .schemas import PipelineError

PROVIDER_SLOTS = BoundedSemaphore(2)


@dataclass(frozen=True)
class Rate:
    input_per_million: float
    output_per_million: float = 0

    def __post_init__(self):
        if any(not math.isfinite(v) or v < 0 for v in (self.input_per_million, self.output_per_million)):
            raise ValueError("Rates must be finite and nonnegative.")

    def upper_cost(self, input_bytes, output_tokens):
        return (input_bytes * self.input_per_million + output_tokens * self.output_per_million) / 1_000_000


def load_rates(path):
    data = json.loads(path.read_text())
    try:
        date.fromisoformat(data["verified_at"])
        if urlsplit(data["source"]).scheme != "https" or not urlsplit(data["source"]).hostname:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise ValueError("A rate card needs an ISO verification date and HTTPS pricing source.") from None
    return {model: Rate(**rate) for model, rate in data["models"].items()}


class Meter:
    def __init__(self, rates, allowance, max_attempts=100):
        if not 0 < allowance <= 5 or not math.isfinite(allowance):
            raise ValueError("A paid run must reserve between $0 and $5.")
        self.rates, self.allowance, self.reserved = rates, allowance, 0.0
        if not isinstance(max_attempts, int) or max_attempts < 1:
            raise ValueError("Reserve a positive number of provider attempts.")
        self.max_attempts = max_attempts
        self.calls = []

    def before(self, kind, model, input_bytes, output_tokens=0):
        if len(self.calls) >= self.max_attempts:
            raise PipelineError("request_limit", "This run exhausted its reserved provider attempts.")
        if model not in self.rates:
            raise PipelineError("unknown_price", "Verify this model's price in the owner's rate card first.")
        amount = self.rates[model].upper_cost(input_bytes, output_tokens)
        if self.reserved + amount > self.allowance + 1e-12:
            raise PipelineError("spend_limit", "This run would exceed its reserved spend limit.")
        self.reserved += amount
        self.calls.append({"kind": kind, "reserved_usd": amount})
