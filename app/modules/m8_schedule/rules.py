from collections import defaultdict

from app.evidence import issue


def count_runs(amounts):
    """相邻（编码连续且实放非零）的斗口合并为一次放水。"""
    count, open_run = 0, False
    for amount in amounts:
        if amount > 0 and not open_run:
            count += 1
        open_run = amount > 0
    return count


def trim(items, amounts, usable, switch, quantum):
    """裁决缺口：从最低优先级、同级渠尾的斗口逐口削减，减到零即退出轮灌。

    每轮按当前放水次数重算切换损失与缺口，直至本渠段收支平衡。
    """
    while any(amounts):
        deficit = sum(amounts) + count_runs(amounts) * switch - usable
        if deficit <= 0:
            break
        index = max((i for i, amount in enumerate(amounts) if amount > 0),
                    key=lambda i: (items[i]["priority"], items[i]["outlet"]))
        cut = min(-(-deficit // quantum) * quantum, amounts[index])
        amounts[index] -= cut
    return amounts


def run(_data, previous):
    quantum = previous["batches"]["quantum_l"]
    switch = previous["batches"]["switch_loss_l"]
    by_channel = defaultdict(list)
    for row in previous["tail"]["allocations"]:
        by_channel[row["channel"]].append(row)
    decided, events, ledgers = {}, [], []
    for entry in previous["channels"]["channels"]:
        channel = entry["channel"]
        items = sorted(by_channel.get(channel, []), key=lambda row: row["outlet"])
        amounts = trim(items, [row["allocated_l"] for row in items], entry["usable_l"], switch, quantum)
        decided[channel] = dict(zip((row["outlet"] for row in items), amounts))
        run_outlets, run_amount = [], 0
        for row, amount in zip(items, amounts):
            if amount:
                run_outlets.append(row["outlet"])
                run_amount += amount
            elif run_outlets:
                events.append({"channel": channel, "outlets": run_outlets, "release_l": run_amount})
                run_outlets, run_amount = [], 0
        if run_outlets:
            events.append({"channel": channel, "outlets": run_outlets, "release_l": run_amount})
        released, runs = sum(amounts), count_runs(amounts)
        ledgers.append({"channel": channel, "usable_l": entry["usable_l"], "released_l": released,
                        "events": runs, "switch_l": runs * switch,
                        "remainder_l": entry["usable_l"] - released - runs * switch,
                        "source": entry["source"]})
    releases, issues = [], []
    for row in previous["tail"]["allocations"]:
        released = decided[row["channel"]][row["outlet"]]
        unmet = max(0, row["minimum_l"] - released)
        if unmet:
            issues.append(issue("MINIMUM_UNMET", row["source"]))
        releases.append({**row, "released_l": released, "cut_l": row["allocated_l"] - released,
                         "unmet_l": unmet})
    for seq, event in enumerate(events, 1):
        event.update(seq=seq, switch_l=switch, outlets_label="、".join(event["outlets"]))
    return {"switch_loss_l": switch, "events": events, "event_count": len(events),
            "releases": releases, "channels": ledgers,
            "released_l": sum(row["released_l"] for row in releases),
            "switch_l": sum(row["switch_l"] for row in ledgers),
            "cut_l": sum(row["cut_l"] for row in releases),
            "unmet_l": sum(row["unmet_l"] for row in releases),
            "issues": issues}
