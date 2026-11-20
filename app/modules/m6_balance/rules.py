from collections import defaultdict

from app.evidence import issue


def run(_data, previous):
    supply = previous["batches"]["supply_l"]
    channels = previous["channels"]
    schedule = previous["schedule"]
    issues = [warning for section in previous.values() for warning in section["issues"]]
    by_channel, by_outlet = defaultdict(int), defaultdict(list)
    for row in schedule["releases"]:
        by_channel[row["channel"]] += row["released_l"]
        by_outlet[row["outlet"]].append(row["source"])
    for sources in by_outlet.values():
        if len(sources) > 1:
            issues.append(issue("DUPLICATE_OUTLET", *sources))
    switch_by_channel = {row["channel"]: row["switch_l"] for row in schedule["channels"]}
    ledgers, held = [], channels["held_at_head_l"]
    for row in channels["channels"]:
        allocation = by_channel.pop(row["channel"], 0)
        switch = switch_by_channel.pop(row["channel"], 0)
        remainder = row["usable_l"] - allocation - switch
        if remainder < 0:
            issues.append(issue("CHANNEL_UNBALANCED", row["source"]))
        ledgers.append({**row, "allocated_l": allocation, "switch_l": switch,
                        "remainder_l": remainder + row["held_l"]})
        held += remainder + row["held_l"]
    if by_channel or switch_by_channel:
        issues.append(issue("CHANNEL_UNBALANCED"))
    losses = channels["loss_l"]
    allocated = schedule["released_l"]
    switches = schedule["switch_l"]
    difference = supply - losses - allocated - switches - held
    return {"status": "DIFFERENCE" if difference or by_channel or switch_by_channel
                      or any(row["usable_l"] < row["allocated_l"] + row["switch_l"] for row in ledgers)
            else "REVIEW" if issues else "MATCHED", "supply_l": supply, "loss_l": losses,
            "switch_l": switches, "allocated_l": allocated,
            "remaining_l": held, "difference_l": difference, "ledgers": ledgers, "issues": issues}
