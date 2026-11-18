from fastapi import APIRouter, HTTPException, Query, Path

from backend.schemas.deputados import(
    DeputadoPerfil,
    ListaDeputadosResponse,
)

from backend.services.camara import (
    CamaraAPIError,
    DeputadoNotFoundError,
    listar_deputados as service_listar_deputados,
    obter_deputado as service_obter_deputado,
)




# Configuração

router = APIRouter(
    prefix="/api/deputados",
    tags=["Deputados"],
    
)


# Listar e pesquisar deputados


@router.get(
    "",
    response_model=ListaDeputadosResponse,
    summary="Listar deputado federais",
    
)

def listar_deputafos(
    nome: str | None = Query(default=None),
    sigla_uf: str | None = Query(default=None),
    sigla_partido: str | None = Query(default=None),
    pagina: int = Query(default=1, ge=1),
    itens: int = Query(default=20, ge=1, le=100),
):
    """Lista deputados federais em exercício. Permite pesquisar por nome, estado e partido"""
    
    try:
        return service_listar_deputados(
            nome=nome,
            sigla_uf=sigla_uf,
            sigla_partido=sigla_partido,
            pagina=pagina,
            itens=itens,
        )
    except CamaraAPIError as erro:
        raise HTTPException(
            status_code=502,
            detail=str(erro),
            
        ) from erro
        

#Consultar perfil individual


@router.get(
    "/{deputado_id}",
    response_model=DeputadoPerfil,
    summary="Consultar perfil de um deputado",  
    
)

def obter_deputado(
    deputado_id: int = Path(gt=0),
):
    """Consulta o perfil público de um estado utilizando seu identificador oficial."""
    
    try:
        return service_obter_deputado(deputado_id)
    
    except DeputadoNotFoundError as erro:
        raise HTTPException(
            status_code=404,
            detail=str(erro),
        ) from erro
        
    except CamaraAPIError as erro:
        raise HTTPException(
            status_code=502,
            detail=str(erro),
        ) from erro
        
    