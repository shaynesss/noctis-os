"""API list prices, per model.

What a turn WOULD have cost on the API -- never a charge. Under a
subscription the marginal cost of a turn is zero, and the figure exists to
answer "what is this plan worth", not "what do I owe". Every name that
carries it says `list`.

Why a table here rather than the engine's own figure: the CLI reported a
per-turn `total_cost_usd` while Noctis drove it with `-p`, and 120 turns
still carry that in `usage.list_cost_usd`. Since the PTY migration the
transcript is the source and it carries tokens, not dollars, so a sum over
the stored column could never cover more than those 120 turns. Priced from
tokens, every turn is covered, and the old 120 are the check: their engine
figures reproduce from this table to the cent.
"""
from __future__ import annotations

# USD per million tokens: input, output, cache read, cache write.
#
# Cache writes at the 1-hour rate, 2x input. The CLI keeps its prefix warm on
# the hour TTL, and the engine-priced turns say so: they reproduce at 2x and
# miss by a third at the 5-minute 1.25x. Cache reads are 0.1x input except
# Fable 5.1's, which is 0.025x.
LIST_PRICES: dict[str, tuple[float, float, float, float]] = {
    "claude-fable-5-1": (10.0, 50.0, 0.25, 20.0),
    "claude-opus-5": (5.0, 25.0, 0.5, 10.0),
    "claude-sonnet-5": (2.0, 10.0, 0.2, 4.0),
    "claude-sonnet-4-6": (3.0, 15.0, 0.3, 6.0),
    "claude-haiku-4-5": (1.0, 5.0, 0.1, 2.0),
}


def rates(model: str) -> tuple[float, float, float, float] | None:
    """The row for a model id, by longest matching prefix: a dated id such as
    `claude-haiku-4-5-20251001` is Haiku 4.5."""
    best = ""
    for name in LIST_PRICES:
        if model.startswith(name) and len(name) > len(best):
            best = name
    return LIST_PRICES[best] if best else None


def list_price(model: str, input_tokens: int, output_tokens: int,
               cached_tokens: int, cache_write_tokens: int) -> float | None:
    """USD at list price, or None for a model this table does not know.

    A turn that spent nothing costs nothing whatever it calls itself: the
    CLI writes `<synthetic>` rows with every count at zero, and those are
    priced, at zero, rather than counted as gaps in the figure.
    """
    if not (input_tokens or output_tokens or cached_tokens or cache_write_tokens):
        return 0.0
    r = rates(model)
    if r is None:
        return None
    return (input_tokens * r[0] + output_tokens * r[1]
            + cached_tokens * r[2] + cache_write_tokens * r[3]) / 1_000_000
