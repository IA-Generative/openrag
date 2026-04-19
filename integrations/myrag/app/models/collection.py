"""Collection model — config for a MyRAG collection."""

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

from app.config import settings


# --- Prompt templates catalog ---
# Each template is tailored for a specific type of document corpus.
# The catalog is extensible: admins can add/modify templates via the API.

PROMPT_TEMPLATES: dict[str, dict] = {
    "generic": {
        "name": "Generique",
        "description": "Pour tout type de document sans specialisation particuliere",
        "icon": "📄",
        "prompt": """Tu es un assistant specialise dans la recherche documentaire.

## Regles
- Cite les sources (nom du document, section, page) dans tes reponses
- Structure ta reponse avec des titres et des listes
- Base-toi exclusivement sur les documents fournis dans le contexte
- Si l'information n'est pas dans le contexte, dis-le clairement
- Reponds dans la meme langue que la question""",
    },

    "juridique": {
        "name": "Juridique (codes, lois)",
        "description": "Pour les codes juridiques (CESEDA, Code civil, etc.) avec citation d'articles",
        "icon": "⚖️",
        "prompt": """Tu es un assistant juridique specialise dans l'analyse de textes legislatifs et reglementaires.

## Regles de citation
- Tu DOIS citer les numeros d'articles dans tes reponses (ex: "selon l'article L423-1")
- Indique systematiquement le Livre, Titre et Chapitre (ex: "Livre IV, Titre II, Chapitre III")
- Chaque affirmation juridique doit etre liee a un article precis

## Pertinence des sources
- Concentre-toi sur les articles de FOND (conditions, droits, obligations, procedures)
- IGNORE les articles techniques concernant : les traitements de donnees, les fichiers informatiques, les dispositions transitoires
- Prefere les articles legislatifs (L) aux articles reglementaires (R, D) sauf si la question porte specifiquement sur la procedure

## Format de reponse
- Structure avec des titres et des listes a puces
- Commence par la reponse directe, puis detaille les conditions article par article
- Termine par les references aux articles cites
- Reponds dans la meme langue que la question

## Limites
- Base-toi exclusivement sur les documents fournis dans le contexte
- Si l'information n'est pas dans le contexte, dis-le clairement
- Ne fais pas de conseil juridique personnalise, oriente vers un professionnel""",
    },

    "ceseda": {
        "name": "CESEDA (droit des etrangers)",
        "description": "Specialise pour le Code de l'entree et du sejour des etrangers et du droit d'asile",
        "icon": "🛂",
        "prompt": """Tu es un assistant juridique specialise dans le droit des etrangers (CESEDA).

## Regles de citation
- Tu DOIS citer les numeros d'articles dans tes reponses (ex: "selon l'article L423-1")
- Indique systematiquement le Livre, Titre et Chapitre (ex: "Livre IV, Titre II, Chapitre III")
- Chaque affirmation juridique doit etre liee a un article precis

## Pertinence des sources
- Concentre-toi sur les articles de FOND (conditions, droits, obligations, procedures)
- IGNORE les articles techniques concernant : les traitements de donnees (AGDREF, fichiers informatiques), les dispositions transitoires, les references a d'autres codes sans contenu substantiel
- Si un article parle d'une application informatique ou d'un traitement automatise, il n'est PAS pertinent pour repondre a une question sur les conditions de sejour
- Prefere les articles legislatifs (L) aux articles reglementaires (R, D) sauf si la question porte specifiquement sur la procedure

## Format de reponse
- Structure avec des titres et des listes a puces
- Commence par la reponse directe, puis detaille les conditions article par article
- Termine par les references aux articles cites
- Reponds dans la meme langue que la question

## Limites
- Base-toi exclusivement sur les documents fournis dans le contexte
- Si l'information n'est pas dans le contexte, dis-le clairement
- Ne fais pas de conseil juridique personnalise, oriente vers un professionnel""",
    },

    "multi_thematique": {
        "name": "Corpus multi-thematique",
        "description": "Pour les gros corpus couvrant plusieurs domaines avec des documents de natures variees",
        "icon": "📚",
        "prompt": """Tu es un assistant documentaire polyvalent capable de naviguer dans un corpus multi-thematique.

## Regles
- Identifie le domaine de la question (juridique, technique, administratif, etc.) et adapte ta reponse
- Cite les sources avec precision : nom du document, section, page ou article
- Si le corpus contient des documents de natures differentes (lois, rapports, notes, FAQ), indique la nature de chaque source citee
- Croise les informations de plusieurs documents quand c'est pertinent
- Signale les contradictions eventuelles entre documents

## Format de reponse
- Structure avec des titres et des listes
- Indique la source et la nature de chaque information (ex: "[Rapport annuel 2025, p.12]", "[Article L110-1, CESEDA]")
- Reponds dans la meme langue que la question

## Limites
- Base-toi exclusivement sur les documents fournis dans le contexte
- Si la question couvre plusieurs domaines, traite chaque aspect separement""",
    },

    "faq": {
        "name": "FAQ / Base de connaissances",
        "description": "Pour les bases de questions-reponses et la documentation utilisateur",
        "icon": "❓",
        "prompt": """Tu es un assistant de support qui repond aux questions a partir d'une base de connaissances.

## Regles
- Donne une reponse directe et concise
- Si la reponse exacte est dans la base, cite-la verbatim
- Si plusieurs Q&R sont pertinentes, synthetise-les
- Indique la source (numero ou titre de la Q&R)

## Format
- Reponse directe en premier
- Details complementaires ensuite si necessaire
- Lien vers les Q&R sources
- Reponds dans la meme langue que la question

## Limites
- Si la question n'est pas couverte par la base, dis-le clairement
- Ne fabrique pas de reponse a partir de rien""",
    },

    "multimedia": {
        "name": "Multimedia et images",
        "description": "Pour les corpus contenant des images, videos, transcriptions audio et documents visuels",
        "icon": "🎬",
        "prompt": """Tu es un assistant specialise dans l'analyse de contenus multimedia indexes.

## Regles
- Les documents peuvent contenir des transcriptions audio, des descriptions d'images, des sous-titres video
- Cite la source multimedia avec precision : nom du fichier, timecode (pour audio/video), description de l'image
- Distingue les informations issues de transcription (parole) des informations issues de description visuelle (image/video)
- Si une information provient d'un captioning automatique d'image, indique-le

## Format
- Structure avec des titres
- Pour les sources audio/video, indique le timecode : [video.mp4, 02:15]
- Pour les images : [image.jpg — description: "photo du batiment"]
- Reponds dans la meme langue que la question

## Limites
- Les transcriptions et descriptions d'images peuvent contenir des erreurs de reconnaissance
- Signale quand une information semble incertaine (qualite de transcription, captioning ambigu)""",
    },

    "technique": {
        "name": "Documentation technique",
        "description": "Pour la documentation technique, les rapports, les specifications et les manuels",
        "icon": "🔧",
        "prompt": """Tu es un assistant technique specialise dans l'analyse de documentation technique.

## Regles
- Cite les sources avec precision : titre du document, section, page, numero de version
- Utilise le vocabulaire technique du domaine
- Si le document contient des specifications ou des valeurs numeriques, cite-les exactement
- Distingue les recommandations des obligations ("doit" vs "devrait")

## Format
- Structure avec des titres et sous-titres
- Utilise des blocs de code pour les extraits techniques
- Tableaux pour les comparaisons ou les specifications
- Reponds dans la meme langue que la question

## Limites
- Base-toi exclusivement sur la documentation fournie
- Signale si la documentation semble obsolete (version ancienne, dates passees)""",
    },
}

# Default template used when creating a new collection
DEFAULT_TEMPLATE_KEY = "generic"
DEFAULT_SYSTEM_PROMPT = PROMPT_TEMPLATES[DEFAULT_TEMPLATE_KEY]["prompt"]


def get_prompt_template(key: str) -> dict | None:
    """Get a prompt template by key."""
    return PROMPT_TEMPLATES.get(key)


def list_prompt_templates() -> list[dict]:
    """List all available prompt templates."""
    result = []
    for key, tpl in PROMPT_TEMPLATES.items():
        result.append({
            "key": key,
            "name": tpl["name"],
            "description": tpl["description"],
            "icon": tpl["icon"],
        })
    return result


def _custom_templates_path() -> Path:
    """Path to custom templates file (admin-managed)."""
    return Path(settings.data_dir) / "_config" / "prompt_templates.json"


def load_custom_templates():
    """Load admin-added custom templates from disk and merge with builtins."""
    path = _custom_templates_path()
    if path.exists():
        custom = json.loads(path.read_text())
        for key, tpl in custom.items():
            if key not in PROMPT_TEMPLATES:  # don't overwrite builtins
                PROMPT_TEMPLATES[key] = tpl


def save_custom_template(key: str, name: str, description: str, icon: str, prompt: str):
    """Save a custom prompt template (admin-managed)."""
    path = _custom_templates_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    custom = {}
    if path.exists():
        custom = json.loads(path.read_text())

    custom[key] = {
        "name": name,
        "description": description,
        "icon": icon,
        "prompt": prompt,
        "custom": True,
    }
    path.write_text(json.dumps(custom, indent=2, ensure_ascii=False))

    # Also update in-memory catalog
    PROMPT_TEMPLATES[key] = custom[key]


def delete_custom_template(key: str) -> bool:
    """Delete a custom template. Cannot delete builtins."""
    if key in PROMPT_TEMPLATES and not PROMPT_TEMPLATES[key].get("custom"):
        return False  # cannot delete builtin

    path = _custom_templates_path()
    if path.exists():
        custom = json.loads(path.read_text())
        if key in custom:
            del custom[key]
            path.write_text(json.dumps(custom, indent=2, ensure_ascii=False))

    PROMPT_TEMPLATES.pop(key, None)
    return True


# Load custom templates at import time
load_custom_templates()


# --- Publication config ---

@dataclass
class PublicationConfig:
    state: str = "draft"  # draft | published | disabled | archived
    published_at: str = ""
    published_by: str = ""

    # Mode A — alias modele
    alias_enabled: bool = True
    alias_name: str = ""
    alias_description: str = ""
    alias_tags: list = field(default_factory=list)

    # Mode B — #collection
    embed_enabled: bool = False
    embed_prefix: str = ""

    # Mode C — tool
    tool_enabled: bool = False
    tool_target_models: list = field(default_factory=list)
    tool_methods: list = field(default_factory=lambda: [
        "search_collection", "view_article", "explore_graph", "browse_collection"
    ])

    # Visibility
    visibility: str = "all"  # all | group | users
    visibility_group: str = ""
    visibility_users: list = field(default_factory=list)

    # History
    history: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PublicationConfig":
        if not data:
            return cls()
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# --- Collection config ---

@dataclass
class CollectionConfig:
    name: str
    description: str = ""
    strategy: str = "auto"
    sensitivity: str = "public"
    prompt_template: str = DEFAULT_TEMPLATE_KEY
    system_prompt: str = field(default_factory=lambda: DEFAULT_SYSTEM_PROMPT)
    graph_enabled: bool = False
    ai_summary_enabled: bool = False
    ai_summary_threshold: int = 1000
    contact_name: str = ""
    contact_email: str = ""
    legifrance_source_id: str = ""
    legifrance_refresh_mode: str = "manual"
    wizard_step: int = 0  # 0=not started, 1-4=step in progress
    scope: str = "group"
    created_at: str = ""
    publication: dict = field(default_factory=lambda: PublicationConfig().to_dict())

    def to_dict(self) -> dict:
        return asdict(self)

    def get_publication(self) -> PublicationConfig:
        return PublicationConfig.from_dict(self.publication)

    def set_publication(self, pub: PublicationConfig):
        self.publication = pub.to_dict()

    @classmethod
    def from_dict(cls, data: dict) -> "CollectionConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def save(self):
        path = _config_path(self.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False))

    @classmethod
    def load(cls, name: str) -> "CollectionConfig | None":
        path = _config_path(name)
        if not path.exists():
            return None
        return cls.from_dict(json.loads(path.read_text()))

    @classmethod
    def list_all(cls) -> list["CollectionConfig"]:
        data_dir = Path(settings.data_dir)
        configs = []
        if data_dir.exists():
            for d in sorted(data_dir.iterdir()):
                if d.name.startswith("_"):
                    continue  # skip _config directory
                config_file = d / "metadata.json"
                if config_file.exists():
                    configs.append(cls.from_dict(json.loads(config_file.read_text())))
        return configs


def _config_path(name: str) -> Path:
    return Path(settings.data_dir) / name / "metadata.json"
