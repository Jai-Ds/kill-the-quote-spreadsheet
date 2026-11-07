import io

import pandas as pd
import streamlit as st

from proto import attributes as A
from proto import data, db, ui
from proto import factcheck as F

ui.header("Run evaluation", "Who should I choose?")
ui.need_replies()
names = ui.names()
short = {k: n.split()[0] for k, n in names.items()}
tags = db.item_tags()
mat = data.rm_table().set_index("RM code")["Material"].to_dict()
spec = data.rm_table().set_index("RM code")["Spec strength"].to_dict()
SCORE = {"Cost": "score_cost", "Delivery": "score_delivery", "Quality": "score_quality", "Inventory": "score_inventory", "Supply risk": "score_supply", "Compliance": "score_compliance"}


@st.dialog("Run evaluation")
def run_dialog():
    st.caption("This recalculates scores from the latest quotes and evidence.")
    counts = {t: sum(1 for x in tags.values() if x == t) for t in ui.templates()}
    pick = st.pills("Run for template", list(counts), default=st.session_state.get("run_template") or list(counts)[0], format_func=lambda t: f"{t} ({counts[t]} items)")
    if st.button("Submit", type="primary", width="stretch"):
        if pick:
            st.session_state.run_template = pick
            st.rerun()
        else:
            st.warning("Choose a template first.")


tmpl = st.session_state.get("run_template")
a, b = st.columns([4, 1], vertical_alignment="center")
if not tmpl:
    with a:
        ui.insight("Choose a template to see the best vendors for the items tagged to it.")
else:
    q, _ = ui.scored(tmpl)
    q = q[q["template"] == tmpl]
    live = q[q["not_quoted"] == False]   # noqa: E712
    passed = live[(live["cleared_questionnaire"] == True) & live["sku_score"].notna()]   # noqa: E712
    with a:
        ui.insight(f"{tmpl}: {len(passed)} of {len(live)} quotes can be ranked.", f" {len(live) - len(passed)} are held for failed knockouts or missing answers.")
if b.button("Run evaluation", type="primary", icon=":material/play_arrow:", width="stretch"):
    run_dialog()
if not tmpl:
    st.stop()

items = [c for c, t in sorted(tags.items()) if t == tmpl]
att = A.all_attributes().set_index(["vendor", "attribute"])
if q.empty:
    st.info("No vendor has offered these items yet.", icon=":material/hourglass_empty:")
    st.stop()

bar = st.container(horizontal=True)
level = bar.segmented_control("Level", ["By SKU", "By vendor"], default="By SKU", label_visibility="collapsed", key="lvl") or "By SKU"
show = bar.segmented_control("Show", ["Scores", "Actual values"], default="Scores", label_visibility="collapsed", key="shw") or "Scores"


def s10(x):
    return "No data" if x is None or x != x else f"{x / 10:.1f}"


def why_panel(cells, meta):
    if not cells:
        st.caption("Click any cell to see why.")
        return
    i, col = cells[0]
    r = meta[i]
    if r is None:
        return
    with st.container(border=True):
        if col == "Evidence":
            fc = F.item_claims(r["vendor"], r["rm_code"])
            bad = fc[fc["Result"] == "Fail"]
            st.markdown(f"**{short[r['vendor']]}, {r['material']}: {(fc['Result'] == 'Pass').sum()} of {len(fc)} claims pass. Claims that failed:**")
            st.write("; ".join(f"{x['Claim type']}: {x['How it was checked']}" for _, x in bad.head(4).iterrows()) or "All claims passed.")
        elif col in SCORE:
            st.markdown(f"**{short[r['vendor']]}, {r['material']}: {A.BY_KEY[col]['name']}**")
            st.write(A.why(col, r, att.loc[(r["vendor"], col)]))
        else:
            st.caption("Click a value in an attribute or Evidence column to see why.")


all_rows = []
if level == "By SKU":
    for code in items:
        g = q[(q["rm_code"] == code) & (q["not_quoted"] == False)]   # noqa: E712
        ok = g[(g["cleared_questionnaire"] == True) & g["sku_score"].notna()].sort_values("sku_score", ascending=False).head(3)   # noqa: E712
        rest = g[~g.index.isin(ok.index)]
        with ui.card(f"sku{code}"):
            ui.title(f"Item {code[-3:]}", f"{mat[code]} · {spec[code]}", ui.badge(f"{len(ok)} ranked · {len(rest)} held", "good" if len(ok) else "bad"))
            if g.empty:
                st.caption("No bidder for this item.")
                all_rows.append({"SKU": code, "Vendor": "No bidder"})
                continue
            rows, meta = [], []
            for rank, (_, r) in enumerate(list(ok.iterrows()) + list(rest.iterrows()), 1):
                good = r.name in ok.index
                line = {"Vendor": short[r["vendor"]]}
                for k, col in SCORE.items():
                    x = att.loc[(r["vendor"], k)]
                    line[k] = s10(r[col]) if show == "Scores" else A.fact(k, r, x)
                why_not = ", ".join(r["knockouts"]) or ("Answers pending" if not r["comparable"] else "")
                line["Evidence"] = F.item_level(r["vendor"], code)
                line["Total"] = s10(r["sku_score"]) if good else "Failed"
                line["Note"] = "Best" if good and rank == 1 else why_not
                rows.append(line)
                meta.append(r)
            df = pd.DataFrame(rows)
            all_rows += [{"SKU": code, **x} for x in rows]
            ev = st.dataframe(ui.colored(df, ["Evidence", "Note"]), hide_index=True, height="content", on_select="rerun", selection_mode="single-cell", key=f"t{tmpl}{show}{code}", alt=f"Evaluation for {mat[code]}", column_config={"Note": st.column_config.TextColumn(width="medium")})
            why_panel(ev.selection.cells, meta)
else:
    rows = []
    for vid, g in q[q["not_quoted"] == False].groupby("vendor"):   # noqa: E712
        sc = g[g["sku_score"].notna()]
        w = sc["spend_inr"].fillna(0)
        line = {"Vendor": short[vid], "Items offered": f"{len(g)} of {len(items)}"}
        for k, col in SCORE.items():
            x = sc[[col, "spend_inr"]].dropna()
            val = (x[col] * x["spend_inr"]).sum() / x["spend_inr"].sum() if len(x) and x["spend_inr"].sum() else None
            if show == "Scores":
                line[k] = s10(val)
            else:
                a2 = att.loc[(vid, k)]
                line[k] = {"Cost": f"Rs {sc['spend_inr'].sum():,.0f} total", "Delivery": f"OTIF {g['otif'].mean():.0%}" if g["otif"].notna().any() else "No history",
                           "Quality": f"{g['defect_rate'].mean():.1%} defects" if g["defect_rate"].notna().any() else "No history",
                           "Inventory": f"Rs {sc['inventory_cost_inr'].sum():,.0f} holding"}.get(k, f"{a2['answered']} of {a2['questions']} answered")
        line["Total"] = s10((sc["sku_score"] * w).sum() / w.sum()) if w.sum() else "No data"
        rows.append(line)
    rows.sort(key=lambda r: -1 if r["Total"] == "No data" else float(r["Total"]), reverse=True)
    all_rows = rows
    with ui.card("byvendor"):
        ui.title("Vendor view", f"{len(rows)} vendors on {tmpl} items")
        st.dataframe(pd.DataFrame(rows), hide_index=True, height="content", alt="Evaluation by vendor")
        ui.note("Each score is rolled up from the vendor's items, weighted by spend. Switch to By SKU to see each item.")

with ui.card("decision"):
    ui.title("Your decision", "Choose a vendor for each item")
    pickrows = []
    cols = st.columns(2)
    for i, code in enumerate(items):
        g = q[(q["rm_code"] == code) & (q["cleared_questionnaire"] == True) & q["sku_score"].notna()].sort_values("sku_score", ascending=False)   # noqa: E712
        opts = [short[x] for x in g["vendor"]] + ["Hold"]
        c = cols[i % 2].selectbox(f"{code[-3:]} {mat[code]}", opts, key=f"aw{tmpl}{code}")
        pickrows.append({"SKU": code, "Chosen vendor": c, "Template": tmpl})
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as x:
        pd.DataFrame(pickrows).to_excel(x, sheet_name="Decision", index=False)
        pd.DataFrame(all_rows).to_excel(x, sheet_name="Evaluation", index=False)
    st.download_button("Export decisions", buf.getvalue(), f"Kesavi_{tmpl.replace(' ', '_')}_decision.xlsx", icon=":material/download:", type="primary")

ui.next_step("Review how the agents reached this point", "app_pages/trace.py")
