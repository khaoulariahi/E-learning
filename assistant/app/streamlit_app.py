"""Dev UI for the study assistant.

Run from the repo root:  streamlit run assistant/app/streamlit_app.py
"""

import sys
from pathlib import Path

# Streamlit puts this file's folder on sys.path, not the repo root.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from assistant.app import common, tab_performance, tab_settings  # noqa: E402

st.set_page_config(page_title="Study assistant (dev)", page_icon="📚", layout="wide")
common.init_once()

notebook = common.sidebar()

tabs = st.tabs(["📥 Sources", "💬 Chat", "📝 Résumé", "🎧 Podcast", "🎓 Learn", "🧪 Eval", "⚡ Performance", "⚙️ Settings"])
placeholders = {
    0: "Phase 1: upload and inspect sources.",
    1: "Phase 1: grounded chat with citations.",
    2: "Phase 5: verified exam-night summary.",
    3: "Phase 6: podcast.",
    4: "Phase 7: quizzes, flashcards, mastery.",
    5: "Phase 2: evaluation runs.",
}
for i, text in placeholders.items():
    with tabs[i]:
        st.info(text)
        if notebook is None:
            st.caption("Create or select a notebook in the sidebar.")

with tabs[6]:
    tab_performance.render(notebook)
with tabs[7]:
    tab_settings.render()
