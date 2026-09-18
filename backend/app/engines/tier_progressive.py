"""Progressive tier electricity: each kWh charged at its band price."""

from app.engines.helpers import kwh_qty, money


class TierValidationError(ValueError):
    """Draft tier sequence failed monotonic-upper-bound / non-negative-price checks."""


def validate_tiers(tiers: list[dict]) -> None:
    """Validate a tier sequence in sort order.

    Rules:
      * at least one tier;
      * every price is non-negative and finite;
      * finite upper bounds strictly increase (monotonic upper bound);
      * an open end (up_to is None) may only be the last tier;
      * finite bounds must be non-negative.
    """
    if not tiers:
        raise TierValidationError("阶梯档至少需要一条")
    prev_up: float | None = None
    saw_open = False
    for i, t in enumerate(tiers):
        price = float(t["price"])
        if price != price or price in (float("inf"), float("-inf")):
            raise TierValidationError(f"第{i + 1}档单价非法")
        if price < 0:
            raise TierValidationError(f"第{i + 1}档单价为负：{price}")
        if saw_open:
            raise TierValidationError("开口档（无上限）只能是最后一档")
        up = t.get("up_to")
        if up is None:
            saw_open = True
            continue
        up_f = float(up)
        if up_f != up_f or up_f in (float("inf"), float("-inf")):
            raise TierValidationError(f"第{i + 1}档上限非法")
        if up_f < 0:
            raise TierValidationError(f"第{i + 1}档上限为负：{up_f}")
        if prev_up is not None and up_f <= prev_up:
            raise TierValidationError(
                f"第{i + 1}档上限 {up_f} 未严格大于前一档上限 {prev_up}（须单调递增）"
            )
        prev_up = up_f


def calc_bill(kwh: float, tiers: list[dict], peak_factor: float = 1.0) -> dict:
    """tiers: [{up_to, price}] last up_to may be None for open end."""
    remain = float(kwh)
    if remain < 0:
        raise ValueError("kwh must be non-negative")
    segments = []
    total = 0.0
    prev = 0.0
    pf = float(peak_factor)
    for t in tiers:
        up = t.get("up_to")
        price = float(t["price"]) * pf
        if up is None:
            qty = remain
        else:
            span = float(up) - prev
            qty = min(remain, max(0.0, span))
        if qty > 1e-9:
            amount = money(qty * price)
            segments.append(
                {
                    "from_kwh": prev,
                    "to_kwh": prev + qty,
                    "qty": kwh_qty(qty),
                    "price": round(price, 4),
                    "amount": amount,
                }
            )
            total += amount
            remain -= qty
        if up is not None:
            prev = float(up)
        if remain <= 1e-9:
            break
    return {
        "kwh": kwh_qty(kwh),
        "peak_factor": pf,
        "total": money(total),
        "segments": segments,
    }
