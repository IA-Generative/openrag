"""Collection model — config for a MyRAG collection."""

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path

from app.config import settings


DEFAULT_SYSTEM_PROMPT = """Tu es un assistant juridique specialise dans le droit des etrangers (CESEDA).

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
- Ne fais pas de conseil juridique personnalise, oriente vers un professionnel"""


@dataclass
class CollectionConfig:
    name: str
    description: str = ""
    strategy: str = "auto"
    sensitivity: str = "public"
    system_prompt: str = field(default_factory=lambda: DEFAULT_SYSTEM_PROMPT)
    graph_enabled: bool = False
    legifrance_source_id: str = ""
    legifrance_refresh_mode: str = "manual"
    scope: str = "group"  # public, group, private
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

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
                config_file = d / "metadata.json"
                if config_file.exists():
                    configs.append(cls.from_dict(json.loads(config_file.read_text())))
        return configs


def _config_path(name: str) -> Path:
    return Path(settings.data_dir) / name / "metadata.json"
