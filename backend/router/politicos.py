from math import ceil
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from backend.schemas.politicos import ListaPoliticosResponse

from backend.services.catalogo_politicos import (
    CatalogoPoliticosError,
    listar_politicos as service_listar_politicos,
)

from backend.services.senado import (
    listar_senadores as service_listar_senadores,
    SenadoAPIError,
)


router = APIRouter(
    prefix="/api/politicos",
    tags=["Políticos"],
)


# ============================================================
# CATÁLOGO UNIFICADO
# ============================================================

@router.get(
    "",
    response_model=ListaPoliticosResponse,
    summary="Consultar catálogo geral de políticos",
)
def listar_catalogo_politicos(
    nome: str | None = Query(default=None),

    cargo: str | None = Query(default=None),

    uf: str | None = Query(
        default=None,
        min_length=2,
        max_length=2,
    ),

    municipio: str | None = Query(default=None),

    partido: str | None = Query(default=None),

    fase_mandato: Literal[
        "em_exercicio",
        "eleito_futuro",
        "mandato_em_andamento"
    ] | None = Query(default=None),

    pagina: int = Query(default=1, ge=1),

    itens: int = Query(default=20, ge=1, le=100),
):
    try:
        return service_listar_politicos(
            nome=nome,
            cargo=cargo,
            uf=uf,
            municipio=municipio,
            partido=partido,
            fase_mandato=fase_mandato,
            pagina=pagina,
            itens=itens,
        )

    except CatalogoPoliticosError as erro:
        raise HTTPException(
            status_code=502,
            detail=str(erro),
        ) from erro

    except ValueError as erro:
        raise HTTPException(
            status_code=400,
            detail=str(erro),
        ) from erro


# ============================================================
# LISTAGEM ESPECÍFICA DE SENADORES
# MANTIDA PARA COMPATIBILIDADE
# ============================================================

@router.get(
    "/senadores",
    response_model=ListaPoliticosResponse,
    summary="Listar senadores em exercício",
)
def listar_senadores(
    nome: str | None = Query(default=None),

    sigla_uf: str | None = Query(
        default=None,
        min_length=2,
        max_length=2,
    ),

    sigla_partido: str | None = Query(default=None),

    pagina: int = Query(default=1, ge=1),

    itens: int = Query(default=20, ge=1, le=100),
):
    try:
        senadores = service_listar_senadores()

    except SenadoAPIError as erro:
        raise HTTPException(
            status_code=502,
            detail=str(erro),
        ) from erro

    if nome and nome.strip():
        termo = nome.strip().casefold()

        senadores = [
            senador
            for senador in senadores
            if termo in senador.nome.casefold()
        ]

    if sigla_uf:
        estado = sigla_uf.strip().upper()

        senadores = [
            senador
            for senador in senadores
            if senador.uf == estado
        ]

    if sigla_partido:
        sigla = sigla_partido.strip().upper()

        senadores = [
            senador
            for senador in senadores
            if (senador.partido or "").upper() == sigla
        ]

    total = len(senadores)

    ultima_pagina = max(
        1,
        ceil(total / itens),
    )

    inicio = (pagina - 1) * itens
    fim = inicio + itens

    dados_paginados = senadores[inicio:fim]

    return ListaPoliticosResponse(
        dados=dados_paginados,
        pagina=pagina,
        itens=itens,
        total=total,
        total_paginas=ultima_pagina,
        tem_proxima=pagina < ultima_pagina,
        ultima_pagina=ultima_pagina,
    )