"""Sample notebook for the student-interface demo (a short biology course on photosynthesis).

Everything here is demo content standing in for what the real pipelines (phases 1–7) will produce.
"""

NOTEBOOK_TITLE = "Biologie — La photosynthèse"

SOURCES = [
    {
        "id": "s1",
        "name": "cours_photosynthese.pdf",
        "kind": "pdf",
        "meta": "PDF · 12 pages · texte + 4 images analysées",
        "text": """[p.2] La photosynthèse est le processus par lequel les végétaux chlorophylliens transforment l'énergie lumineuse en énergie chimique, en produisant de la matière organique à partir de dioxyde de carbone et d'eau.
[p.4] Équation bilan : 6CO2 + 6H2O → C6H12O6 + 6O2 (en présence de lumière et de chlorophylle).
[p.5] La photosynthèse se déroule dans les chloroplastes. Elle comprend deux phases : la phase photochimique (ou phase lumineuse), dans les thylakoïdes, et la phase chimique (cycle de Calvin), dans le stroma.
[p.6] Phase lumineuse : l'énergie lumineuse captée par la chlorophylle permet la photolyse de l'eau (2H2O → 4H+ + 4e- + O2). Le dioxygène libéré provient donc de l'eau. Cette phase produit de l'ATP et du NADPH.
[p.7, texte extrait d'une image] Schéma du chloroplaste : membrane externe, membrane interne, stroma, thylakoïdes empilés en granums, ADN chloroplastique.
[p.8] Cycle de Calvin : dans le stroma, l'enzyme RuBisCO fixe le CO2 sur le ribulose-1,5-bisphosphate. L'ATP et le NADPH produits par la phase lumineuse sont utilisés pour réduire le carbone et former des trioses phosphates, à partir desquels le glucose est synthétisé.
[p.10] La chlorophylle absorbe surtout les radiations bleues et rouges ; elle réfléchit le vert, ce qui explique la couleur des feuilles.
[p.11] Facteurs limitants : l'intensité lumineuse, la concentration en CO2 et la température. Au-delà d'un certain seuil, augmenter un facteur n'augmente plus le rendement si un autre facteur est limitant.""",
    },
    {
        "id": "s2",
        "name": "td2_scanne.pdf",
        "kind": "scan",
        "meta": "PDF scanné · 3 pages · OCR",
        "text": """[p.1] Exercice 1 : Une plante est placée dans une enceinte éclairée. On mesure le dégagement de O2 en fonction de l'intensité lumineuse. Expliquer pourquoi la courbe atteint un plateau.
[p.1] Correction : au-delà d'une certaine intensité lumineuse, la lumière n'est plus le facteur limitant ; c'est la concentration en CO2 (ou la température) qui limite la vitesse de la photosynthèse.
[p.2] Exercice 2 : Une expérience avec de l'eau marquée à l'oxygène 18 (H2 18O) montre que le O2 dégagé est marqué. Conclusion : le dioxygène produit provient de l'eau et non du CO2.""",
    },
    {
        "id": "s3",
        "name": "notes_tableau.jpg",
        "kind": "image",
        "meta": "Photo · notes manuscrites · transcrites",
        "text": """[photo 1] Phase lumineuse → produit ATP + NADPH + O2 (thylakoïdes).
[photo 1] Phase sombre = cycle de Calvin → utilise ATP + NADPH, fixe le CO2 (stroma).
[photo 1] ⚠ À retenir : le O2 vient de l'EAU !
[photo 1] Rendement : environ 1 à 2 % de l'énergie lumineuse reçue est convertie (formule peu lisible sur la photo).""",
    },
    {
        "id": "s4",
        "name": "cours_12_mars.m4a",
        "kind": "audio",
        "meta": "Audio · 52 min · transcrit",
        "text": """[08:15] Alors, la chlorophylle, elle absorbe le bleu et le rouge, et c'est pour ça que les feuilles sont vertes : le vert, elle le renvoie.
[14:32] Retenez bien l'équation bilan, six CO2 plus six H2O donnent un glucose plus six O2. Ça va tomber à l'examen, je vous le dis.
[27:05] Le cycle de Calvin ne dépend pas directement de la lumière, mais il a besoin de l'ATP et du NADPH de la phase lumineuse. Donc à l'obscurité, il s'arrête rapidement.
[41:50] Attention au piège classique : beaucoup d'entre vous écrivent que l'oxygène vient du CO2. C'est faux, il vient de la photolyse de l'eau.""",
    },
    {
        "id": "s5",
        "name": "photosynthesis_summary_en.md",
        "kind": "markdown",
        "meta": "Markdown · anglais",
        "text": """# Photosynthesis — key points
- Light-dependent reactions take place in the thylakoid membranes and produce ATP, NADPH and O2.
- The Calvin cycle takes place in the stroma; RuBisCO fixes CO2.
- C4 and CAM plants have adaptations that reduce photorespiration in hot, dry climates.""",
    },
]

OVERVIEW = (
    "Ce notebook couvre la **photosynthèse** : son équation bilan, ses deux phases (phase lumineuse dans "
    "les thylakoïdes, cycle de Calvin dans le stroma), le rôle de la chlorophylle et les facteurs limitants. "
    "Il réunit le cours, un TD scanné, une photo du tableau, l'enregistrement du cours du 12 mars et un "
    "résumé en anglais."
)

SUGGESTED_QUESTIONS = [
    "Quelle est l'équation bilan de la photosynthèse ?",
    "D'où vient le dioxygène produit par la photosynthèse ?",
    "What is the role of the Calvin cycle?",
]

# Prepared answers used when no NVIDIA API key is configured. Citation numbers follow SOURCES order (1-based).
FALLBACK_ANSWERS = [
    (("bilan", "équation", "equation", "formule"),
     "L'équation bilan de la photosynthèse est :\n\n$$6CO_2 + 6H_2O \\rightarrow C_6H_{12}O_6 + 6O_2$$\n\n"
     "Elle se fait en présence de lumière et de chlorophylle [1]. Le professeur a insisté : *« ça va tomber à "
     "l'examen »* (cours du 12 mars, 14:32) [4]."),
    (("dioxygène", "oxygène", "o2", "oxygen"),
     "Le dioxygène produit provient de **l'eau**, par la photolyse de l'eau pendant la phase lumineuse : "
     "$2H_2O \\rightarrow 4H^+ + 4e^- + O_2$ [1].\n\nL'expérience avec de l'eau marquée à l'oxygène 18 le "
     "démontre : le O₂ dégagé est marqué [2]. ⚠️ Piège classique signalé par le professeur : écrire que "
     "l'oxygène vient du CO₂ est faux [4]."),
    (("calvin", "sombre", "stroma", "rubisco"),
     "The Calvin cycle takes place in the **stroma** of the chloroplast [1]. The enzyme **RuBisCO** fixes CO₂, "
     "and the ATP and NADPH produced by the light-dependent phase are used to build triose phosphates, from "
     "which glucose is made [1][5].\n\nIt doesn't use light directly, but it stops quickly in the dark because "
     "it needs ATP and NADPH from the light phase [4]."),
    (("chlorophylle", "vert", "couleur", "chlorophyll"),
     "La chlorophylle absorbe surtout les radiations **bleues et rouges** et réfléchit le **vert**, d'où la "
     "couleur des feuilles [1][4]."),
    (("facteur", "limitant", "plateau"),
     "Les facteurs limitants sont l'intensité lumineuse, la concentration en CO₂ et la température [1]. Dans "
     "le TD, la courbe atteint un plateau car au-delà d'une certaine intensité, la lumière n'est plus "
     "limitante : c'est le CO₂ ou la température qui limite [2]."),
]

FALLBACK_NOT_FOUND = (
    "Je ne trouve pas cette information dans tes documents. Essaie une question sur l'équation bilan, l'origine "
    "du dioxygène, le cycle de Calvin, la chlorophylle ou les facteurs limitants.\n\n"
    "*Mode démo : sans clé API, l'assistant utilise des réponses préparées.*"
)

RESUME_MD = r"""# Résumé — Biologie : la photosynthèse

## 🎯 L'essentiel en 6 points
1. La photosynthèse convertit l'énergie lumineuse en énergie chimique (matière organique). <sup>[cours p.2]</sup>
2. Équation bilan : $6CO_2 + 6H_2O \rightarrow C_6H_{12}O_6 + 6O_2$ ✅ <sup>[cours p.4]</sup>
3. Deux phases : lumineuse (thylakoïdes) puis cycle de Calvin (stroma). <sup>[cours p.5]</sup>
4. Le O₂ produit vient de **l'eau** (photolyse), pas du CO₂. <sup>[cours p.6 · TD p.2]</sup>
5. La chlorophylle absorbe le bleu et le rouge, réfléchit le vert. <sup>[cours p.10]</sup>
6. Facteurs limitants : lumière, CO₂, température. <sup>[cours p.11]</sup>

## 📚 Par thème

### 1. Définition et bilan
- **Définition — Photosynthèse** : « processus par lequel les végétaux chlorophylliens transforment l'énergie lumineuse en énergie chimique, en produisant de la matière organique à partir de dioxyde de carbone et d'eau » <sup>[cours p.2]</sup>
  - *En clair* : la plante fabrique son sucre avec de la lumière, du CO₂ et de l'eau.
- **Formule — Équation bilan** : $$6CO_2 + 6H_2O \rightarrow C_6H_{12}O_6 + 6O_2$$ ✅ vérifiée <sup>[cours p.4 · audio 14:32]</sup>

### 2. Phase lumineuse (thylakoïdes)
- **Photolyse de l'eau** : $2H_2O \rightarrow 4H^+ + 4e^- + O_2$ ✅ <sup>[cours p.6]</sup>
- Produit : **ATP**, **NADPH** et **O₂**. <sup>[cours p.6 · notes tableau]</sup>
- ⚠️ **Piège fréquent** : le O₂ ne vient pas du CO₂ mais de l'eau. <sup>[audio 41:50 · TD p.2]</sup>

### 3. Cycle de Calvin (stroma)
- La **RuBisCO** fixe le CO₂ sur le ribulose-1,5-bisphosphate. <sup>[cours p.8]</sup>
- Utilise l'ATP et le NADPH de la phase lumineuse → trioses phosphates → glucose. <sup>[cours p.8]</sup>
- S'arrête vite à l'obscurité (plus d'ATP ni de NADPH). <sup>[audio 27:05]</sup>

### 4. Chlorophylle et facteurs limitants
- Absorbe le **bleu** et le **rouge**, réfléchit le **vert**. <sup>[cours p.10 · audio 08:15]</sup>
- **Facteurs limitants** : intensité lumineuse, CO₂, température ; au-delà d'un seuil, c'est un autre facteur qui limite. <sup>[cours p.11 · TD p.1]</sup>
- ⚠️ **À vérifier dans ton cours** : le rendement « 1 à 2 % » vient d'une photo peu lisible. <sup>[notes tableau]</sup>

## 🗣️ Ce que le prof a souligné
- ▶ **14:32** — « Retenez bien l'équation bilan… ça va tomber à l'examen. »
- ▶ **41:50** — « Attention au piège classique : l'oxygène ne vient pas du CO₂. »

## ❓ Questions probables à l'examen
1. Écrire l'équation bilan de la photosynthèse.
2. Montrer, à partir d'une expérience, que le O₂ dégagé provient de l'eau.
3. Expliquer pourquoi le cycle de Calvin s'arrête à l'obscurité.
4. Interpréter le plateau d'une courbe de dégagement de O₂ en fonction de la lumière.

## ✅ Checklist de révision
- [ ] Équation bilan
- [ ] Phase lumineuse : lieu, produits, photolyse
- [ ] Cycle de Calvin : lieu, RuBisCO, besoins
- [ ] Chlorophylle et spectre d'absorption
- [ ] Facteurs limitants
"""

RESUME_REPORT = [
    {"Section": "Définition et bilan", "Éléments": 3, "Inclus": 3, "Vérifiés": 3, "À vérifier": 0, "Manquants": 0},
    {"Section": "Phase lumineuse", "Éléments": 4, "Inclus": 4, "Vérifiés": 4, "À vérifier": 0, "Manquants": 0},
    {"Section": "Cycle de Calvin", "Éléments": 3, "Inclus": 3, "Vérifiés": 3, "À vérifier": 0, "Manquants": 0},
    {"Section": "Chlorophylle et facteurs", "Éléments": 4, "Inclus": 4, "Vérifiés": 3, "À vérifier": 1, "Manquants": 0},
]

RESUME_STEPS = [
    "Inventaire des éléments obligatoires (définitions, formules, emphase du prof)",
    "Extraction avec citations exactes",
    "Vérification automatique des citations, formules et nombres",
    "Relecture section par section par un second modèle",
    "Assemblage et rapport de couverture",
]

PODCAST = [
    {"t": "00:00", "speaker": "A", "text": "Salut ! Aujourd'hui on révise la photosynthèse. Franchement, il y a beaucoup de choses à retenir…"},
    {"t": "00:06", "speaker": "B", "text": "Pas de panique, on va aller à l'essentiel. D'abord, l'idée générale : la plante transforme l'énergie lumineuse en énergie chimique."},
    {"t": "00:15", "speaker": "A", "text": "Et l'équation bilan, celle que le prof a dit qui tombe à l'examen ?"},
    {"t": "00:20", "speaker": "B", "text": "Six CO2 plus six H2O donnent un glucose, C6H12O6, plus six O2. En présence de lumière et de chlorophylle."},
    {"t": "00:31", "speaker": "A", "text": "D'accord. Et ça se passe en une seule étape ?"},
    {"t": "00:34", "speaker": "B", "text": "Non, en deux phases. La phase lumineuse, dans les thylakoïdes, puis le cycle de Calvin, dans le stroma."},
    {"t": "00:43", "speaker": "A", "text": "La phase lumineuse, elle produit quoi exactement ?"},
    {"t": "00:46", "speaker": "B", "text": "De l'ATP, du NADPH et du dioxygène. Et attention au piège : ce dioxygène vient de l'eau, grâce à la photolyse, pas du CO2."},
    {"t": "00:57", "speaker": "A", "text": "Ah, c'est l'expérience avec l'oxygène 18 du TD !"},
    {"t": "01:01", "speaker": "B", "text": "Exactement. L'eau marquée donne un dioxygène marqué. Ensuite, le cycle de Calvin utilise l'ATP et le NADPH pour fixer le CO2, grâce à la RuBisCO."},
    {"t": "01:13", "speaker": "A", "text": "Et si on éteint la lumière ?"},
    {"t": "01:15", "speaker": "B", "text": "Le cycle de Calvin s'arrête vite, parce qu'il n'a plus d'ATP ni de NADPH."},
    {"t": "01:22", "speaker": "A", "text": "Dernière question : pourquoi les feuilles sont vertes ?"},
    {"t": "01:25", "speaker": "B", "text": "La chlorophylle absorbe le bleu et le rouge, et renvoie le vert. Voilà, tu as l'essentiel. Bonne révision !"},
]

QUIZ = [
    {
        "q": "D'où provient le dioxygène libéré par la photosynthèse ?",
        "options": ["Du dioxyde de carbone", "De l'eau", "Du glucose", "De la chlorophylle"],
        "answer": 1,
        "why_wrong": {0: "Piège classique (souligné par le prof à 41:50) : le O₂ vient de la photolyse de l'eau.",
                      2: "Le glucose est un produit, pas une source de O₂.",
                      3: "La chlorophylle capte la lumière ; elle ne fournit pas d'oxygène."},
        "explanation": "Photolyse de l'eau : 2H₂O → 4H⁺ + 4e⁻ + O₂ (cours p.6 ; TD exercice 2).",
        "concept": "Photolyse de l'eau",
    },
    {
        "q": "Où se déroule le cycle de Calvin ?",
        "options": ["Dans les thylakoïdes", "Dans le stroma", "Dans la mitochondrie", "Dans le noyau"],
        "answer": 1,
        "why_wrong": {0: "Les thylakoïdes sont le lieu de la phase lumineuse.",
                      2: "La mitochondrie est le lieu de la respiration cellulaire.",
                      3: "Le noyau n'intervient pas directement."},
        "explanation": "Le cycle de Calvin a lieu dans le stroma du chloroplaste (cours p.5 et p.8).",
        "concept": "Cycle de Calvin",
    },
    {
        "q": "Quelles radiations la chlorophylle absorbe-t-elle surtout ?",
        "options": ["Vertes", "Bleues et rouges", "Infrarouges", "Ultraviolettes"],
        "answer": 1,
        "why_wrong": {0: "Le vert est réfléchi, c'est pourquoi les feuilles paraissent vertes.",
                      2: "Ce n'est pas mentionné dans le cours.",
                      3: "Ce n'est pas mentionné dans le cours."},
        "explanation": "La chlorophylle absorbe le bleu et le rouge et réfléchit le vert (cours p.10).",
        "concept": "Chlorophylle",
    },
    {
        "q": "Pourquoi le cycle de Calvin s'arrête-t-il rapidement à l'obscurité ?",
        "options": ["La RuBisCO est détruite par l'obscurité",
                    "Il n'y a plus d'ATP ni de NADPH produits par la phase lumineuse",
                    "Le CO₂ disparaît de la cellule",
                    "Le glucose bloque la RuBisCO"],
        "answer": 1,
        "why_wrong": {0: "La RuBisCO n'est pas détruite.",
                      2: "Le CO₂ reste disponible.",
                      3: "Ce mécanisme n'est pas dans le cours."},
        "explanation": "Le cycle de Calvin dépend de l'ATP et du NADPH de la phase lumineuse (audio 27:05).",
        "concept": "Cycle de Calvin",
    },
]

FLASHCARDS = [
    ("Définis : photosynthèse", "Processus par lequel les végétaux chlorophylliens transforment l'énergie lumineuse en énergie chimique, en produisant de la matière organique à partir de CO₂ et d'eau. [cours p.2]"),
    ("Équation bilan ?", "$6CO_2 + 6H_2O \\rightarrow C_6H_{12}O_6 + 6O_2$ [cours p.4]"),
    ("Lieu de la phase lumineuse ?", "Les thylakoïdes du chloroplaste. [cours p.5]"),
    ("Produits de la phase lumineuse ?", "ATP, NADPH et O₂. [cours p.6]"),
    ("Rôle de la RuBisCO ?", "Fixer le CO₂ sur le ribulose-1,5-bisphosphate dans le cycle de Calvin. [cours p.8]"),
    ("Facteurs limitants ?", "Intensité lumineuse, concentration en CO₂, température. [cours p.11]"),
]

CONCEPTS = ["Photosynthèse", "Phase lumineuse", "Photolyse de l'eau", "Chlorophylle", "Cycle de Calvin",
            "RuBisCO", "ATP / NADPH", "Facteurs limitants"]

CONCEPT_EDGES = [
    ("Photosynthèse", "Phase lumineuse"), ("Photosynthèse", "Cycle de Calvin"),
    ("Photosynthèse", "Facteurs limitants"), ("Phase lumineuse", "Photolyse de l'eau"),
    ("Chlorophylle", "Phase lumineuse"), ("Phase lumineuse", "ATP / NADPH"),
    ("ATP / NADPH", "Cycle de Calvin"), ("RuBisCO", "Cycle de Calvin"),
]

# None = not practiced yet
INITIAL_MASTERY = {
    "Photosynthèse": 0.85, "Phase lumineuse": 0.6, "Photolyse de l'eau": 0.35, "Chlorophylle": 0.9,
    "Cycle de Calvin": 0.45, "RuBisCO": None, "ATP / NADPH": 0.55, "Facteurs limitants": None,
}
