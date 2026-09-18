"""Validation gate for tier rule sequences before they become official."""


def validate_tier_rows(rows: list[dict]) -> None:
    """Raise ValueError unless rows form an applicable tier sequence.

    Rules: at least one tier; every price non-negative; up_to bounds strictly
    increasing; an open-ended tier (up_to None) only as the last entry.
    """
    if not rows:
        raise ValueError("阶梯序列不能为空")
    prev = 0.0
    open_seen = False
    for i, r in enumerate(rows, start=1):
        price = r.get("price")
        if price is None:
            raise ValueError(f"第{i}档缺少单价")
        if float(price) < 0:
            raise ValueError(f"第{i}档单价不能为负（{price}）")
        if open_seen:
            raise ValueError(f"第{i}档出现在开放档（上限为空）之后")
        up = r.get("up_to")
        if up is None:
            open_seen = True
            continue
        up = float(up)
        if up <= prev:
            raise ValueError(f"第{i}档上限 {up} 未严格大于前一档上限 {prev}")
        prev = up
