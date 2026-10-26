"""Student interface (NotebookLM-style): Sources | Chat | Studio.

This is the interface shown to students and teachers for validation. The developer UI is streamlit_app.py.
All data comes from student_backend.py.

Run from the repo root:
    streamlit run assistant/app/student_app.py --theme.base=dark --server.port=8502
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from assistant.app import student_backend as backend  # noqa: E402
from assistant.core.db import init_db  # noqa: E402
from assistant.core.runtime import limiter  # noqa: E402

st.set_page_config(page_title="Assistant d'étude", page_icon=":material/school:", layout="wide")

KIND_ICONS = {"pdf": ":material/picture_as_pdf:", "scan": ":material/document_scanner:",
              "image": ":material/image:", "audio": ":material/graphic_eq:", "markdown": ":material/description:",
              "text": ":material/article:", "docx": ":material/description:", "pptx": ":material/slideshow:"}

STUDIO = [
    ("resume", "Résumé d'examen", ":material/summarize:"),
    ("podcast", "Podcast audio", ":material/podcasts:"),
    ("quiz", "Quiz", ":material/quiz:"),
    ("flashcards", "Flashcards", ":material/style:"),
    ("mindmap", "Carte mentale", ":material/account_tree:"),
    ("progress", "Ma progression", ":material/insights:"),
]
VIEW_TITLES = {key: title for key, title, _ in STUDIO}

CSS = """
<style>
.block-container {padding-top: 1.2rem; padding-bottom: 0.5rem; max-width: 100%;}
header[data-testid="stHeader"] {background: transparent;}
div[data-testid="stVerticalBlockBorderWrapper"] {border-radius: 18px;}
.app-title {font-size: 1.55rem; font-weight: 600; margin: 0;}
.panel-title {font-size: 1.05rem; font-weight: 600; margin: 0 0 .4rem 0;}
.muted {color: #9aa0a6; font-size: .85rem;}
.badge {display:inline-block; padding: 2px 10px; border-radius: 999px; background:#2b2f36; color:#c8ccd2;
        font-size:.78rem; margin-left:.4rem;}
</style>
"""


# ---- state -----------------------------------------------------------------------------------------

@st.cache_resource
def _init_runtime() -> bool:
    init_db()
    limiter.configure("ui")
    return True


def state() -> backend.NotebookState:
    if "nb" not in st.session_state:
        st.session_state.nb = backend.NotebookState()
        st.session_state.messages = []
        st.session_state.view = "chat"
    return st.session_state.nb


def open_view(view: str) -> None:
    st.session_state.view = view


# ---- header ----------------------------------------------------------------------------------------

def header(nb: backend.NotebookState) -> None:
    left, right = st.columns([3, 1], vertical_alignment="center")
    with left:
        mode = "IA connectée" if backend.live_llm_available() else "Mode démo"
        st.markdown(f'<p class="app-title">📚 {nb.title}<span class="badge">{mode}</span></p>',
                    unsafe_allow_html=True)
    with right:
        st.selectbox("Langue des réponses", ["auto", "fr", "en"], key="answer_lang",
                     format_func={"auto": "Langue : auto", "fr": "Français", "en": "English"}.get,
                     label_visibility="collapsed")


# ---- sources panel ---------------------------------------------------------------------------------

def sources_panel(nb: backend.NotebookState) -> None:
    with st.container(border=True, height=740):
        st.markdown('<p class="panel-title">Sources</p>', unsafe_allow_html=True)
        with st.popover("Ajouter des sources", icon=":material/add:", width="stretch"):
            files = st.file_uploader(
                "PDF, images, audio, Word, PowerPoint, texte",
                type=list(backend.KIND_BY_EXT), accept_multiple_files=True, key="uploader",
            )
            if files and st.button("Ajouter", type="primary", width="stretch"):
                for f in files:
                    st.toast(backend.add_upload(nb, f.name, f.getvalue()))
                st.rerun()
            st.caption("Dans cette démo, les fichiers TXT et Markdown sont lus tout de suite ; "
                       "les autres formats sont ajoutés et seront analysés quand leur pipeline sera prêt.")

        ready = [s for s in nb.sources if s.ready]
        all_on = all(s.selected for s in ready) if ready else False
        if st.checkbox("Sélectionner toutes les sources", value=all_on, key=f"all_{all_on}") != all_on:
            for s in ready:
                s.selected = not all_on
            st.rerun()
        st.divider()
        for s in nb.sources:
            cols = st.columns([0.12, 0.88], vertical_alignment="top")
            with cols[0]:
                st.markdown(KIND_ICONS.get(s.kind, ":material/description:"))
            with cols[1]:
                checked = st.checkbox(s.name, value=s.selected, key=f"src_{s.id}", disabled=not s.ready)
                if checked != s.selected:
                    s.selected = checked
                st.caption(s.meta)


# ---- chat ------------------------------------------------------------------------------------------

def show_citations(cites: list[backend.Citation]) -> None:
    if not cites:
        return
    cols = st.columns(min(len(cites), 5))
    for i, c in enumerate(cites):
        with cols[i % len(cols)]:
            with st.popover(f"[{c.n}] {c.source_name}", width="stretch"):
                st.caption(c.source_name)
                st.markdown(c.snippet)


def chat_view(nb: backend.NotebookState) -> None:
    messages = st.session_state.messages
    box = st.container(height=640, border=False)
    with box:
        if not messages:
            st.markdown("### 👋 Prêt à réviser")
            st.markdown(backend.demo.OVERVIEW)
            st.markdown("**Questions suggérées**")
            for q in backend.demo.SUGGESTED_QUESTIONS:
                if st.button(q, key=f"sugg_{q}", icon=":material/chat_bubble:"):
                    st.session_state.pending = q
                    st.rerun()
        for m in messages:
            with st.chat_message(m["role"], avatar=":material/person:" if m["role"] == "user" else ":material/auto_awesome:"):
                st.markdown(m["content"])
                if m["role"] == "assistant":
                    show_citations(m.get("citations", []))

    n_ready = sum(s.selected and s.ready for s in nb.sources)
    question = st.chat_input(f"Pose une question sur tes documents… ({n_ready} sources)")
    question = question or st.session_state.pop("pending", None)
    if question:
        history = list(messages)
        messages.append({"role": "user", "content": question})
        with box:
            with st.chat_message("user", avatar=":material/person:"):
                st.markdown(question)
            with st.chat_message("assistant", avatar=":material/auto_awesome:"):
                tokens, citations_for = backend.answer(nb, question, history, st.session_state.get("answer_lang", "auto"))
                text = st.write_stream(tokens)
                cites = citations_for(text)
                show_citations(cites)
        messages.append({"role": "assistant", "content": text, "citations": cites})
        st.rerun()


# ---- studio views ----------------------------------------------------------------------------------

def generate_once(nb: backend.NotebookState, key: str, steps: list[str]) -> None:
    """Show the generation steps the first time an output is opened (the real pipeline runs as a job)."""
    if key in nb.generated:
        return
    with st.status(f"Génération : {VIEW_TITLES[key]}…", expanded=True) as status:
        for step in steps:
            st.write(f"✓ {step}")
            time.sleep(0.45)
        status.update(label=f"{VIEW_TITLES[key]} prêt", state="complete", expanded=False)
    nb.generated.append(key)


def resume_view(nb: backend.NotebookState) -> None:
    generate_once(nb, "resume", backend.resume_steps())
    st.markdown(backend.resume_markdown(), unsafe_allow_html=True)
    with st.expander("Rapport de vérification", icon=":material/verified:"):
        st.dataframe(pd.DataFrame(backend.resume_report()), hide_index=True, width="stretch")
        st.caption("Chaque définition et formule est citée mot pour mot, vérifiée automatiquement puis relue "
                   "par un second modèle. ⚠️ = source peu lisible : à vérifier dans le cours.")
    st.download_button("Télécharger (.md)", backend.resume_markdown(), file_name="resume_photosynthese.md",
                       icon=":material/download:")


def podcast_view(nb: backend.NotebookState) -> None:
    lines = backend.podcast_script()
    generate_once(nb, "podcast", ["Plan des segments", "Écriture du dialogue", "Vérification des faits",
                                  "Préparation de l'audio"])
    st.caption("Aperçu avec la voix de votre navigateur. La version finale utilise des voix de synthèse NVIDIA.")
    st.iframe(_tts_player(lines), height=110)
    for line in lines:
        who = "Élève" if line["speaker"] == "A" else "Tuteur"
        avatar = ":material/face:" if line["speaker"] == "A" else ":material/school:"
        with st.chat_message(who, avatar=avatar):
            st.markdown(f"**{who}** · `{line['t']}`  \n{line['text']}")


def _tts_player(lines: list[dict]) -> str:
    # Script text will be model-generated (Phase 6): escape "</" so it can't close the <script> tag.
    data = json.dumps([{"s": l["speaker"], "t": l["text"]} for l in lines], ensure_ascii=False).replace("</", "<\\/")
    return f"""
<div style="font-family: sans-serif; color: #e8eaed; display:flex; gap:12px; align-items:center; flex-wrap:wrap">
  <button id="play" style="padding:10px 18px; border-radius:999px; border:none; background:#8ab4f8; color:#111; font-weight:600; cursor:pointer">▶ Écouter le podcast</button>
  <button id="stop" style="padding:10px 18px; border-radius:999px; border:1px solid #5f6368; background:transparent; color:#e8eaed; cursor:pointer">■ Arrêter</button>
  <span id="now" style="font-size:14px; color:#9aa0a6"></span>
</div>
<script>
const lines = {data};
const synth = window.speechSynthesis;
function voices() {{
  const fr = synth.getVoices().filter(v => v.lang && v.lang.toLowerCase().startsWith('fr'));
  return [fr[0] || null, fr[1] || fr[0] || null];
}}
function play(i) {{
  if (i >= lines.length) {{ document.getElementById('now').textContent = 'Terminé'; return; }}
  const [va, vb] = voices();
  const u = new SpeechSynthesisUtterance(lines[i].t);
  u.lang = 'fr-FR';
  const isA = lines[i].s === 'A';
  u.voice = isA ? va : vb;
  u.pitch = isA ? 1.15 : 0.9;
  u.rate = 1.02;
  document.getElementById('now').textContent = (isA ? 'Élève' : 'Tuteur') + ' · ' + (i + 1) + '/' + lines.length;
  u.onend = () => play(i + 1);
  synth.speak(u);
}}
document.getElementById('play').onclick = () => {{ synth.cancel(); play(0); }};
document.getElementById('stop').onclick = () => {{ synth.cancel(); document.getElementById('now').textContent = ''; }};
</script>"""


def quiz_view(nb: backend.NotebookState) -> None:
    questions = backend.quiz()
    answers = st.session_state.setdefault("quiz_answers", {})
    for i, q in enumerate(questions):
        with st.container(border=True):
            st.markdown(f"**{i + 1}. {q['q']}**")
            done = i in answers
            choice = st.radio("Réponse", range(len(q["options"])), format_func=lambda k, q=q: q["options"][k],
                              key=f"quiz_{i}", index=answers.get(i), disabled=done, label_visibility="collapsed")
            if not done and st.button("Valider", key=f"quiz_ok_{i}", disabled=choice is None):
                answers[i] = choice
                backend.record_answer(nb, q["concept"], choice == q["answer"])
                st.rerun()
            if done:
                if answers[i] == q["answer"]:
                    st.success(f"Correct. {q['explanation']}", icon=":material/check_circle:")
                else:
                    st.error(f"{q['why_wrong'].get(answers[i], 'Incorrect.')}  \n"
                             f"Bonne réponse : **{q['options'][q['answer']]}**. {q['explanation']}",
                             icon=":material/cancel:")
    if len(answers) == len(questions):
        score = sum(answers[i] == q["answer"] for i, q in enumerate(questions))
        st.metric("Score", f"{score}/{len(questions)}")
        st.caption("Tes réponses ont mis à jour ta progression (onglet « Ma progression »).")
        if st.button("Recommencer", icon=":material/restart_alt:"):
            st.session_state.quiz_answers = {}
            for i in range(len(questions)):
                st.session_state.pop(f"quiz_{i}", None)
            st.rerun()


def flashcards_view(nb: backend.NotebookState) -> None:
    cards = backend.flashcards()
    i = st.session_state.setdefault("fc_index", 0) % len(cards)
    flipped = st.session_state.setdefault("fc_flipped", False)
    front, back = cards[i]
    st.caption(f"Carte {i + 1}/{len(cards)}")
    with st.container(border=True):
        st.markdown(back if flipped else f"#### {front}")
    c1, c2, c3 = st.columns(3)
    if c1.button("Retourner", icon=":material/flip:", width="stretch"):
        st.session_state.fc_flipped = not flipped
        st.rerun()
    if c2.button("À revoir", icon=":material/replay:", width="stretch", disabled=not flipped):
        st.session_state.fc_index, st.session_state.fc_flipped = i + 1, False
        st.rerun()
    if c3.button("Je savais", icon=":material/done:", width="stretch", disabled=not flipped):
        st.session_state.fc_index, st.session_state.fc_flipped = i + 1, False
        st.rerun()
    st.caption("La version finale planifie les cartes avec la répétition espacée (FSRS).")


def mindmap_view(nb: backend.NotebookState) -> None:
    concepts, edges = backend.concept_graph()
    lines = ['digraph G {', 'rankdir=LR; bgcolor="transparent";',
             'node [shape=box, style="rounded,filled", fontname="Helvetica", fontcolor="#111111", color="#5f6368"];',
             'edge [color="#9aa0a6"];']
    for c in concepts:
        lines.append(f'"{c}" [fillcolor="{_mastery_color(nb.mastery.get(c))}"];')
    lines += [f'"{a}" -> "{b}";' for a, b in edges]
    lines.append("}")
    st.graphviz_chart("\n".join(lines), width="stretch")
    st.caption("Couleur = maîtrise : vert maîtrisé · orange à consolider · rouge à revoir · gris pas encore pratiqué. "
               "Flèches : notions nécessaires pour comprendre la suivante.")


def _mastery_color(m: float | None) -> str:
    if m is None:
        return "#c4c7c5"
    return "#81c995" if m >= 0.8 else "#fcc934" if m >= 0.5 else "#f28b82"


def progress_view(nb: backend.NotebookState) -> None:
    practiced = {c: m for c, m in nb.mastery.items() if m is not None}
    c1, c2, c3 = st.columns(3)
    c1.metric("Maîtrisées", sum(m >= 0.8 for m in practiced.values()))
    c2.metric("À revoir", sum(m < 0.5 for m in practiced.values()))
    c3.metric("Pas encore pratiquées", sum(m is None for m in nb.mastery.values()))
    for concept, m in sorted(nb.mastery.items(), key=lambda kv: (kv[1] is None, kv[1] or 0)):
        cols = st.columns([0.35, 0.5, 0.15], vertical_alignment="center")
        cols[0].markdown(concept)
        if m is None:
            cols[1].caption("pas encore pratiquée")
        else:
            cols[1].progress(m)
            cols[2].markdown("maîtrisé" if m >= 0.8 else "à consolider" if m >= 0.5 else "**à revoir**")
    weakest = [c for c, m in sorted(practiced.items(), key=lambda kv: kv[1]) if m < 0.5][:2]
    if weakest:
        st.info(f"Conseil : commence ta prochaine séance par **{' et '.join(weakest)}**.", icon=":material/lightbulb:")


VIEWS = {"resume": resume_view, "podcast": podcast_view, "quiz": quiz_view, "flashcards": flashcards_view,
         "mindmap": mindmap_view, "progress": progress_view}


def center_panel(nb: backend.NotebookState) -> None:
    with st.container(border=True, height=740):
        view = st.session_state.view
        if view == "chat":
            st.markdown('<p class="panel-title">Discussion</p>', unsafe_allow_html=True)
            chat_view(nb)
            return
        top = st.columns([0.75, 0.25], vertical_alignment="center")
        top[0].markdown(f'<p class="panel-title">{VIEW_TITLES[view]}</p>', unsafe_allow_html=True)
        top[1].button("Retour à la discussion", icon=":material/arrow_back:", on_click=open_view, args=("chat",),
                      width="stretch")
        with st.container(height=660, border=False):
            VIEWS[view](nb)


# ---- studio panel ----------------------------------------------------------------------------------

def studio_panel(nb: backend.NotebookState) -> None:
    with st.container(border=True, height=740):
        st.markdown('<p class="panel-title">Studio</p>', unsafe_allow_html=True)
        for row in range(0, len(STUDIO), 2):
            cols = st.columns(2)
            for col, (key, title, icon) in zip(cols, STUDIO[row:row + 2]):
                col.button(title, icon=icon, key=f"studio_{key}", on_click=open_view, args=(key,),
                           width="stretch",
                           type="primary" if st.session_state.view == key else "secondary")
        st.divider()
        if nb.generated:
            st.caption("Générés")
            for key in nb.generated:
                st.button(VIEW_TITLES[key], icon=":material/history:", key=f"gen_{key}", on_click=open_view,
                          args=(key,), width="stretch", type="tertiary")
        else:
            st.markdown('<p class="muted" style="text-align:center; margin-top:2rem">Les résultats du Studio '
                        'apparaîtront ici. Clique sur Résumé, Podcast, Quiz… pour les créer à partir de tes '
                        'sources.</p>', unsafe_allow_html=True)


# ---- page ------------------------------------------------------------------------------------------

_init_runtime()
st.markdown(CSS, unsafe_allow_html=True)
nb = state()
header(nb)
left, center, right = st.columns([1.05, 2.2, 1.05], gap="small")
with left:
    sources_panel(nb)
with center:
    center_panel(nb)
with right:
    studio_panel(nb)
