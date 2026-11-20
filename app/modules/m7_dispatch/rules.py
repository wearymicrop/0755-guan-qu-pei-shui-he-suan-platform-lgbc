def run(_data, previous):
    batch = previous["batches"]
    balance = previous["balance"]
    routes = {row["channel"]: row["source"] for row in balance["ledgers"]}
    state = "ready" if balance["status"] == "MATCHED" else "held"
    receipts = []
    for row in previous["schedule"]["releases"]:
        if row["released_l"]:
            receipts.append({"receipt": f"{batch['batch']}/{row['outlet']}", "outlet": row["outlet"],
                             "channel": row["channel"], "allocated_l": row["released_l"], "state": state,
                             "sources": [row["source"], *([routes[row["channel"]]] if row["channel"] in routes else [])]})
    return {"state": state, "receipts": receipts, "receipt_l": sum(row["allocated_l"] for row in receipts),
            "issues": balance["issues"]}
