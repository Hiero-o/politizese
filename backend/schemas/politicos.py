from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PoliticoResumo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # Identificação
    id: str
    id_origem: int | str
    fonte: str

    # Dados públicos
    nome: str
    cargo: str
    cargo_slug: str

    # Localização e filiação
    partido: str | None = None
    uf: str | None = None
    municipio: str | None = None

    # Informações complementares
    foto_url: str | None = None
    email: str | None = None
    telefone: str | None = None

    # Situação do cargo
    situacao: str | None = None
    titularidade: str | None = None
    mandato: str | None = None

    fase_mandato: Literal[
        "em_exercicio",
        "eleito_futuro",
        "mandato_em_andamento",
    ] = "em_exercicio"

    # Informações eleitorais
    numero_candidato: str | None = None
    situacao_eleitoral: str | None = None
    turno_eleitoral: int | None = None
    ano_eleicao: int | None = None

    # Rastreabilidade
    fonte_url: str | None = None
    
    codigo_municipio_tse: str | None = None


class FonteStatus(BaseModel):
    fonte: str

    status: Literal[
        "atualizada",
        "cache_valido",
        "cache_desatualizado",
        "indisponivel",
        "cadastro_local",
    ]

    atualizado_em: datetime | None = None
    registros: int = 0
    mensagem: str | None = None


class ListaPoliticosResponse(BaseModel):
    dados: list[PoliticoResumo]

    pagina: int
    itens: int

    total: int
    total_paginas: int

    tem_proxima: bool
    ultima_pagina: int

    # Estado das integrações que alimentam o catálogo.
    fontes: list[FonteStatus] = Field(default_factory=list)