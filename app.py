import hmac
import os
import shutil
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Kill the Quote Spreadsheet", page_icon=":material/fact_check:", layout="wide", initial_sidebar_state="auto")


def secret(name):
    try:
        return st.secrets.get(name) or os.environ.get(name)
    except Exception:   # no secrets file on a local machine
        return os.environ.get(name)


def gate():
    """Password screen for the hosted site. A hosted copy with no password stays closed."""
    password = secret("APP_PASSWORD")
    if not password:
        if (Path.home() / ".aerchain" / ".env").exists():
            return      # the owner's own machine
        st.error("This site has no password set. Add APP_PASSWORD to the app's secrets.")
        st.stop()
    if st.session_state.get("signed_in"):
        return
    st.title("Kill the Quote Spreadsheet")
    with st.form("sign_in"):
        typed = st.text_input("Password", type="password")
        if st.form_submit_button("Open the demo", type="primary"):
            if hmac.compare_digest(typed.encode(), str(password).encode()):
                st.session_state.signed_in = True
                st.rerun()
            st.error("That password isn't right.")
    st.stop()


gate()

from proto import data, db, ui  # noqa: E402

replay = data.RUNTIME / "replay"
seed = Path(__file__).parent / "replay_seed"
if seed.exists() and not (replay.exists() and any(replay.iterdir())):
    shutil.copytree(seed, replay, dirs_exist_ok=True)     # a fresh disk starts with the saved answers
ui.load_style()

GROUPS = {
    "QUOTE COLLECTION": [
        st.Page("app_pages/rfx.py", title="RFP co-pilot", icon=":material/edit_note:", default=True),
        st.Page("app_pages/inbox.py", title="Vendor inbox", icon=":material/inbox:"),
        st.Page("app_pages/status.py", title="Vendor status", icon=":material/fact_check:"),
        st.Page("app_pages/analysis.py", title="Analysis hub", icon=":material/query_stats:"),
    ],
    "EVALUATION": [
        st.Page("app_pages/manage.py", title="Attributes management", icon=":material/tune:"),
        st.Page("app_pages/evidence.py", title="Claims vs evidence", icon=":material/verified:"),
        st.Page("app_pages/evaluation.py", title="Run evaluation", icon=":material/play_circle:"),
    ],
    "UNDER THE HOOD": [
        st.Page("app_pages/trace.py", title="Agent trace", icon=":material/account_tree:"),
        st.Page("app_pages/architecture.py", title="Architecture", icon=":material/schema:"),
    ],
}
nav = st.navigation([p for g in GROUPS.values() for p in g], position="hidden")
waiting = len({a["vendor"] for a in db.approvals()})

with st.sidebar:
    ui.brand()
    ui.journey()
    for label, pages in GROUPS.items():
        st.html(f'<div class="nav-label">{label}</div>')
        for p in pages:
            key = "nav_" + p.title.lower().replace(" ", "_")
            with st.container(key=key):
                st.page_link(p, label=f"{p.title} ({waiting})" if p.title == "Vendor inbox" and waiting else p.title, icon=p.icon)
            if p.title == nav.title:
                st.html(f'<style>.st-key-{key} a{{background:#e9f2ee!important}}.st-key-{key} a p,.st-key-{key} a span{{color:#174c3d!important;font-weight:700}}</style>')
    ui.live()
    ui.spend_panel()
    st.caption("All company and vendor data is fictional.")
st.html("""<script>
if (!window.kqMenu) {
  window.kqMenu = true;
  document.addEventListener('click', (e) => {
    if (window.innerWidth <= 768 && e.target.closest('[data-testid="stSidebar"] a')) {
      setTimeout(() => {
        const c = document.querySelector('[data-testid="stSidebarCollapseButton"] button') || document.querySelector('[data-testid="stSidebarCollapseButton"]');
        if (c) c.click();
      }, 400);
    }
  }, true);
}
</script>""", unsafe_allow_javascript=True)     # on a phone, close the menu after tapping a page
nav.run()
