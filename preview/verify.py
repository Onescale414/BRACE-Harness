"""Check the bracket drawing's embedded measurements using squared distances."""

import json
from pathlib import Path
from math import isqrt


def check(condition, message):
    if not condition:
        raise ValueError(message)


def squared_distance(p, q):
    return sum((a - b) ** 2 for a, b in zip(p, q))


def candidates(start, anchors, seen):
    """Enumerate every lattice point in the first circle's bounding box."""
    radii = [squared_distance(start, a) for a in anchors]
    radius = isqrt(radii[0])
    cx, cy = seen[0]
    return {(x, y) for x in range(cx - radius, cx + radius + 1)
            for y in range(cy - radius, cy + radius + 1)
            if all(squared_distance((x, y), a) == r for a, r in zip(seen, radii))}


def main():
    html = Path(__file__).with_name("bracket.html").read_text(encoding="utf-8")
    block = html.split('<script type="application/json" id="measurements">', 1)[1].split("</script>", 1)[0]
    d = json.loads(block)
    third = candidates(d["beforeThird"], d["before"], d["firstTwo"])
    tips = candidates(d["beforeTip"], d["before"], d["firstTwo"])
    check(third == {tuple(c["third"]) for c in d["carts"]} and len(third) == 2, "third mark alternatives")
    check(tips == {tuple(c["actual"]) for c in d["carts"]} and len(tips) == 2, "tip alternatives")
    gap = squared_distance(d["beforeTip"], d["beforeThird"])
    for c in d["carts"]:
        matches = {tip for tip in tips if squared_distance(tip, c["third"]) == gap}
        check(matches == {tuple(c["actual"])}, "tip after the third mark")
    print("Both tips fit after two marks; the third mark uniquely selects each recorded tip.")


if __name__ == "__main__":
    main()
