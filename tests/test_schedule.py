from app.pipeline import calculate


def test_switch_loss_default(clean):
    """未配置切换损失时按零核算，实放与实配一致。"""
    schedule = clean["schedule"]
    assert schedule["switch_loss_l"] == 0 and schedule["switch_l"] == 0
    assert all(row["released_l"] == row["allocated_l"] for row in schedule["releases"])
    assert schedule["cut_l"] == 0 and schedule["unmet_l"] == 0


def test_merge_adjacent_outlets(clean):
    """相邻斗口合并放水：同渠段连续编码的斗口合成一次放水。"""
    events = [(row["channel"], row["outlets"]) for row in clean["schedule"]["events"]]
    assert events == [("总干渠", ["020"]), ("东支渠", ["001", "002", "003", "004"]),
                      ("西支渠", ["011", "012"]), ("北斗渠", ["031", "032"]),
                      ("苗圃渠", ["041", "042"])]
    assert [row["seq"] for row in clean["schedule"]["events"]] == [1, 2, 3, 4, 5]


def test_drought_priority_protected(drought):
    """总量不足时先保高优先级：001 全额，低优先级 002、003 被削减。"""
    released = {row["outlet"]: row["released_l"] for row in drought["schedule"]["releases"]}
    assert released == {"001": 2000, "002": 0, "003": 400, "020": 2000, "021": 1000}


def test_drought_unmet_minimum(drought):
    schedule = drought["schedule"]
    unmet = {row["outlet"]: row["unmet_l"] for row in schedule["releases"] if row["unmet_l"]}
    assert unmet == {"002": 400, "003": 200}
    assert schedule["unmet_l"] == 600
    assert [item["code"] for item in schedule["issues"]] == ["MINIMUM_UNMET", "MINIMUM_UNMET"]


def test_drop_splits_event_and_rebills_switch(drought):
    """002 减到零退出后，东支渠一次放水拆成两次，切换损失随之重算。"""
    events = [row for row in drought["schedule"]["events"] if row["channel"] == "东支渠"]
    assert [row["outlets"] for row in events] == [["001"], ["003"]]
    ledger = next(row for row in drought["schedule"]["channels"] if row["channel"] == "东支渠")
    assert (ledger["events"], ledger["switch_l"]) == (2, 1000)
    assert ledger["usable_l"] == ledger["released_l"] + ledger["switch_l"] + ledger["remainder_l"]


def test_rotation_order_unique(drought):
    """轮灌顺序：渠段先上游后下游，渠段内按斗口编码。"""
    events = drought["schedule"]["events"]
    assert [(row["seq"], row["channel"], row["outlets"]) for row in events] == [
        (1, "总干渠", ["020", "021"]), (2, "东支渠", ["001"]), (3, "东支渠", ["003"])]
    assert drought["schedule"]["event_count"] == 3


def test_surplus_destination(drought):
    """余水去向：总干渠余 400 L 留存本渠，东支渠无余水。"""
    ledgers = {row["channel"]: row for row in drought["schedule"]["channels"]}
    assert ledgers["总干渠"]["remainder_l"] == 400
    assert ledgers["东支渠"]["remainder_l"] == 0


def test_schedule_ties_with_balance(drought):
    """排程与勾稽对账一致：供水 = 渠损 + 切换 + 实放 + 剩余。"""
    schedule, balance = drought["schedule"], drought["balance"]
    assert balance["switch_l"] == schedule["switch_l"] == 1500
    assert balance["allocated_l"] == schedule["released_l"] == 5400
    assert balance["supply_l"] == (balance["loss_l"] + balance["switch_l"]
                                   + balance["allocated_l"] + balance["remaining_l"])
    assert balance["difference_l"] == 0 and balance["status"] == "REVIEW"
    for row in balance["ledgers"]:
        assert row["inflow_l"] == (row["loss_l"] + row["child_inflow_l"] + row["allocated_l"]
                                   + row["switch_l"] + row["remainder_l"])


def test_dispatch_matches_schedule(drought):
    dispatch = drought["dispatch"]
    assert dispatch["state"] == "held"
    assert dispatch["receipt_l"] == drought["schedule"]["released_l"]
    assert {row["outlet"] for row in dispatch["receipts"]} == {"001", "003", "020", "021"}


def test_reordered_input_stable(drought_data):
    def settled(schedule):
        amounts = {row["outlet"]: (row["released_l"], row["cut_l"], row["unmet_l"])
                   for row in schedule["releases"]}
        return schedule["event_count"], schedule["events"], amounts

    before = settled(calculate(drought_data)["schedule"])
    drought_data["rights"].reverse()
    assert settled(calculate(drought_data)["schedule"]) == before


def test_rerun_adds_no_release_event(client):
    """同一输入重跑不新增放水次数：归档复用且轮灌顺序一致。"""
    first = client.post("/api/runs", json={"sample": "drought"}).json()
    second = client.post(f"/api/runs/{first['id']}/rerun").json()
    assert second["reused"] and second["id"] == first["id"]
    assert (second["result"]["schedule"]["event_count"]
            == first["result"]["schedule"]["event_count"] == 3)
    assert second["result"]["schedule"]["events"] == first["result"]["schedule"]["events"]


def test_explicit_zero_switch_matches_default(clean_data):
    clean_data["config"]["switch_loss"] = "0"
    result = calculate(clean_data)
    assert result["schedule"]["event_count"] == 5
    assert result["balance"]["allocated_l"] == 16700


def test_switch_loss_bad_value_rejected(clean_data):
    clean_data["config"]["switch_loss"] = "-"
    response_code = None
    try:
        calculate(clean_data)
    except Exception as error:
        response_code = getattr(error, "code", None)
    assert response_code == "BAD_BATCH"


def test_all_cut_when_switch_exceeds_usable(drought_data):
    """切换损失吞掉全部可配水时，所有斗口实放为零、无放水次数。"""
    drought_data["config"]["switch_loss"] = "100"
    drought_data["config"]["unit"] = "m³"
    schedule = calculate(drought_data)["schedule"]
    assert schedule["event_count"] == 0
    assert schedule["released_l"] == 0
    assert all(row["released_l"] == 0 for row in schedule["releases"])
