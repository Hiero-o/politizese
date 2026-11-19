import json
import logging
import tempfile

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from backend.schemas.politicos import (
    FonteStatus,
    ListaPoliticosResponse,
    PoliticoResumo,
)

from backend.services.camara import (
    CamaraAPIError,
    listar_deputados,
)

from backend.services.senado import (
    SenadoAPIError,
    listar_senadores,
)

from backend.services.presidencia import (
    listar_autoridades_presidenciais,
)

from backend.services.tse import (
    TSEAPIError,
    listar_eleitos_2026,
)

from backend.services.tse_municipal import (
    TSEMunicipalAPIError,
    listar_eleitos_municipais_2024,
)


logger = logging.getLogger(__name__)


# CONFIGURAÇÕES

PROJECT_ROOT = Path(__file__).resolve().parents[2]

CACHE_DIR = (
    PROJECT_ROOT
    / "data"
    / "cache"
    / "politicos"
)

# Validade de cada fonte, em segundos.
CACHE_TTL = {
    "camara": 300,       # 5 minutos
    "senado": 300,       # 5 minutos
    "tse": 21600,        # 6 horas
    "tse_municipal": 21600,
}

ITENS_POR_REQUISICAO = 100

MAX_PAGINAS_CAMARA = 100



# EXCEÇÕES


class CatalogoPoliticosError(Exception):
    """Erro geral ao construir o catálogo de políticos."""



# CAMINHOS DOS SNAPSHOTS


def _caminho_snapshot(fonte: str) -> Path:
    return CACHE_DIR / f"{fonte}.json"



# LEITURA DO SNAPSHOT LOCAL


def _ler_snapshot(
    fonte: str,
) -> tuple[list[PoliticoResumo], datetime] | None:

    caminho = _caminho_snapshot(fonte)

    if not caminho.is_file():
        return None

    try:
        conteudo = json.loads(
            caminho.read_text(encoding="utf-8")
        )

        if not isinstance(conteudo, dict):
            raise ValueError("Snapshot inválido.")

        data_atualizacao = conteudo.get("atualizado_em")
        registros = conteudo.get("dados")

        if not isinstance(data_atualizacao, str):
            raise ValueError(
                "Data de atualização ausente no snapshot."
            )

        if not isinstance(registros, list):
            raise ValueError(
                "Lista de dados inválida no snapshot."
            )

        atualizado_em = datetime.fromisoformat(
            data_atualizacao.replace("Z", "+00:00")
        )

        if atualizado_em.tzinfo is None:
            atualizado_em = atualizado_em.replace(
                tzinfo=timezone.utc
            )

        politicos = [
            PoliticoResumo.model_validate(registro)
            for registro in registros
        ]

        return politicos, atualizado_em

    except (
        OSError,
        ValueError,
        TypeError,
        ValidationError,
    ) as erro:
        logger.warning(
            "Snapshot da fonte %s inválido: %s",
            fonte,
            erro,
        )

        return None



# GRAVAÇÃO SEGURA DO SNAPSHOT


def _salvar_snapshot(
    fonte: str,
    dados: list[PoliticoResumo],
    atualizado_em: datetime,
) -> None:

    CACHE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    caminho = _caminho_snapshot(fonte)

    conteudo = {
        "versao": 1,
        "fonte": fonte,
        "atualizado_em": atualizado_em.isoformat(),
        "quantidade": len(dados),
        "dados": [
            politico.model_dump(mode="json")
            for politico in dados
        ],
    }

    caminho_temporario = None

    try:
        # Criar arquivo temporário no mesmo diretório.
        # O replace evita deixar um JSON parcialmente gravado.
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".tmp",
            prefix=f"{fonte}_",
            dir=CACHE_DIR,
            delete=False,
        ) as arquivo:

            json.dump(
                conteudo,
                arquivo,
                ensure_ascii=False,
                indent=2,
            )

            caminho_temporario = Path(arquivo.name)

        caminho_temporario.replace(caminho)

    except OSError:
        if caminho_temporario and caminho_temporario.exists():
            caminho_temporario.unlink(missing_ok=True)

        raise



# CONSULTA COM CACHE INDEPENDENTE


def _obter_fonte_com_cache(
    fonte: str,
    coletar: Callable[[], list[PoliticoResumo]],
    erros_esperados: tuple[type[Exception], ...],
    forcar_atualizacao: bool = False,
) -> tuple[list[PoliticoResumo], FonteStatus]:

    agora = datetime.now(timezone.utc)

    ttl = CACHE_TTL[fonte]

    snapshot = _ler_snapshot(fonte)

    
    # CACHE AINDA VÁLIDO
    

    if snapshot is not None and not forcar_atualizacao:
        dados_cache, atualizado_em = snapshot

        idade = (
            agora - atualizado_em
        ).total_seconds()

        if idade < ttl:
            return dados_cache, FonteStatus(
                fonte=fonte,
                status="cache_valido",
                atualizado_em=atualizado_em,
                registros=len(dados_cache),
                mensagem="Dados carregados do snapshot local válido.",
            )

    
    # CONSULTAR A FONTE EXTERNA
    

    try:
        dados_novos = coletar()

        if not isinstance(dados_novos, list):
            raise CatalogoPoliticosError(
                f"A fonte {fonte} retornou um formato inválido."
            )

        dados_normalizados = [
            PoliticoResumo.model_validate(registro)
            for registro in dados_novos
        ]

        atualizado_em = datetime.now(timezone.utc)

        try:
            _salvar_snapshot(
                fonte=fonte,
                dados=dados_normalizados,
                atualizado_em=atualizado_em,
            )

        except OSError as erro:
            # A API respondeu. Mesmo que não consigamos salvar
            # o snapshot, ainda podemos entregar os dados atuais.
            logger.warning(
                "Não foi possível salvar o snapshot de %s: %s",
                fonte,
                erro,
            )

        return dados_normalizados, FonteStatus(
            fonte=fonte,
            status="atualizada",
            atualizado_em=atualizado_em,
            registros=len(dados_normalizados),
            mensagem="Dados consultados diretamente na fonte oficial.",
        )

    
    # FALHA NA FONTE EXTERNA
    

    except erros_esperados as erro:

        logger.warning(
            "Fonte %s indisponível: %s",
            fonte,
            erro,
        )

        # Existe snapshot anterior: utilizar dados antigos.
        if snapshot is not None:
            dados_cache, atualizado_em = snapshot

            return dados_cache, FonteStatus(
                fonte=fonte,
                status="cache_desatualizado",
                atualizado_em=atualizado_em,
                registros=len(dados_cache),
                mensagem=(
                    "Fonte indisponível. "
                    "Exibindo o último snapshot local disponível."
                ),
            )

        # Nunca conseguimos salvar dados dessa fonte.
        return [], FonteStatus(
            fonte=fonte,
            status="indisponivel",
            atualizado_em=None,
            registros=0,
            mensagem=(
                "Fonte indisponível e nenhum snapshot local encontrado."
            ),
        )



# CARREGAR DEPUTADOS FEDERAIS


def _carregar_deputados() -> list[PoliticoResumo]:

    deputados_normalizados = []

    pagina = 1

    while True:

        if pagina > MAX_PAGINAS_CAMARA:
            raise CatalogoPoliticosError(
                "O limite de páginas da Câmara foi excedido."
            )

        resultado = listar_deputados(
            pagina=pagina,
            itens=ITENS_POR_REQUISICAO,
        )

        for deputado in resultado.dados:

            politico = PoliticoResumo(
                id=f"camara-{deputado.id}",
                id_origem=deputado.id,
                fonte="camara",

                nome=deputado.nome,
                cargo="Deputado federal",
                cargo_slug="deputado_federal",

                partido=deputado.partido,
                uf=deputado.uf,

                foto_url=deputado.foto_url,
                email=deputado.email,

                situacao="Em exercício",
                fase_mandato="em_exercicio",

                fonte_url=deputado.fonte_url,
            )

            deputados_normalizados.append(politico)

        if not resultado.tem_proxima:
            break

        pagina += 1

    return deputados_normalizados



# OBTER CATÁLOGO E SITUAÇÃO DAS FONTES


def _obter_catalogo_com_status(
    forcar_atualizacao: bool = False,
) -> tuple[list[PoliticoResumo], list[FonteStatus]]:

    
    # CÂMARA
    

    deputados, status_camara = _obter_fonte_com_cache(
        fonte="camara",
        coletar=_carregar_deputados,
        erros_esperados=(
            CamaraAPIError,
            CatalogoPoliticosError,
        ),
        forcar_atualizacao=forcar_atualizacao,
    )

    
    # SENADO
    

    senadores, status_senado = _obter_fonte_com_cache(
        fonte="senado",
        coletar=listar_senadores,
        erros_esperados=(SenadoAPIError,),
        forcar_atualizacao=forcar_atualizacao,
    )

    
    # TSE
    

    eleitos_tse, status_tse = _obter_fonte_com_cache(
        fonte="tse",
        coletar=lambda: listar_eleitos_2026(
            forcar_atualizacao=forcar_atualizacao
        ),
        erros_esperados=(TSEAPIError,),
        forcar_atualizacao=forcar_atualizacao,
    )
    
    
    # TSE — ELEIÇÕES MUNICIPAIS DE 2024
    

    eleitos_municipais, status_tse_municipal = (
        _obter_fonte_com_cache(
            fonte="tse_municipal",
            coletar=listar_eleitos_municipais_2024,
            erros_esperados=(TSEMunicipalAPIError,),
            forcar_atualizacao=forcar_atualizacao,
        )
    )

    
    # PRESIDÊNCIA
    

    autoridades = listar_autoridades_presidenciais()

    status_presidencia = FonteStatus(
        fonte="planalto",
        status="cadastro_local",
        atualizado_em=None,
        registros=len(autoridades),
        mensagem=(
            "Cadastro provisório mantido localmente. "
            "Ainda não existe atualização automática por API."
        ),
    )

    
    # UNIFICAÇÃO
    

    politicos = (
        deputados
        + senadores
        + autoridades
        + eleitos_tse
        + eleitos_municipais
    )

    politicos.sort(
        key=lambda politico: (
            politico.nome.casefold(),
            politico.fonte,
            politico.id,
        )
    )

    fontes = [
        status_camara,
        status_senado,
        status_tse,
        status_presidencia,
        status_tse_municipal,
    ]

    return politicos, fontes



# CONSULTA DO CATÁLOGO


def obter_catalogo(
    forcar_atualizacao: bool = False,
) -> list[PoliticoResumo]:

    politicos, _ = _obter_catalogo_com_status(
        forcar_atualizacao=forcar_atualizacao,
    )

    return politicos


def obter_politico_por_id(
    politico_id: str,
) -> PoliticoResumo | None:
    """Retorna um político pelo ID, consultando primeiro seu snapshot.

    O perfil é aberto a partir de um card que já veio do catálogo, então
    normalmente o snapshot da origem já existe. Consultá-lo diretamente
    evita reconstruir todo o catálogo (e chamar APIs externas) a cada clique.
    """

    if not politico_id or not politico_id.strip():
        return None

    # A Presidência ainda é um cadastro local, sem snapshot próprio.
    if politico_id.startswith("planalto-"):
        return next(
            (
                politico
                for politico in listar_autoridades_presidenciais()
                if politico.id == politico_id
            ),
            None,
        )

    origens_por_prefixo = (
        ("camara-", "camara"),
        ("senado-", "senado"),
        ("tse-2026-", "tse"),
        ("tse-2024-", "tse_municipal"),
    )

    for prefixo, fonte in origens_por_prefixo:
        if not politico_id.startswith(prefixo):
            continue

        snapshot = _ler_snapshot(fonte)
        if snapshot is None:
            return None

        dados, _ = snapshot
        return next(
            (politico for politico in dados if politico.id == politico_id),
            None,
        )

    return None



# FILTROS E PAGINAÇÃO


def listar_politicos(
    nome: str | None = None,
    cargo: str | None = None,
    uf: str | None = None,
    municipio: str | None = None,
    partido: str | None = None,
    fase_mandato: str | None = None,
    pagina: int = 1,
    itens: int = 20,
) -> ListaPoliticosResponse:

    if pagina < 1:
        raise ValueError(
            "A página deve ser maior que zero."
        )

    if not 1 <= itens <= 100:
        raise ValueError(
            "A quantidade de itens deve estar entre 1 e 100."
        )

    if fase_mandato not in (
        None,
        "em_exercicio",
        "eleito_futuro",
        "mandato_em_andamento",
    ):
        raise ValueError(
            "Fase do mandato inválida."
        )

    politicos, fontes = _obter_catalogo_com_status()

    # FILTRO POR NOME
    if nome and nome.strip():
        termo = nome.strip().casefold()

        politicos = [
            politico
            for politico in politicos
            if termo in politico.nome.casefold()
        ]

    # FILTRO POR CARGO
    if cargo and cargo.strip():
        cargo_normalizado = (
            cargo.strip()
            .casefold()
            .replace(" ", "_")
            .replace("-", "_")
        )

        politicos = [
            politico
            for politico in politicos
            if politico.cargo_slug == cargo_normalizado
        ]

    # FILTRO POR ESTADO
    if uf and uf.strip():
        estado = uf.strip().upper()

        politicos = [
            politico
            for politico in politicos
            if (politico.uf or "").upper() == estado
        ]

    # FILTRO POR MUNICÍPIO
    if municipio and municipio.strip():
        cidade = municipio.strip().casefold()

        politicos = [
            politico
            for politico in politicos
            if cidade in (politico.municipio or "").casefold()
        ]

    # FILTRO POR PARTIDO
    if partido and partido.strip():
        sigla = partido.strip().upper()

        politicos = [
            politico
            for politico in politicos
            if (politico.partido or "").upper() == sigla
        ]

    # FILTRO POR FASE DO MANDATO
    if fase_mandato:
        politicos = [
            politico
            for politico in politicos
            if politico.fase_mandato == fase_mandato
        ]

    # PAGINAÇÃO
    total = len(politicos)

    ultima_pagina = max(
        1,
        (total + itens - 1) // itens,
    )

    inicio = (pagina - 1) * itens
    fim = inicio + itens

    dados_paginados = politicos[inicio:fim]

    return ListaPoliticosResponse(
        dados=dados_paginados,
        pagina=pagina,
        itens=itens,
        total=total,
        total_paginas=ultima_pagina,
        tem_proxima=pagina < ultima_pagina,
        ultima_pagina=ultima_pagina,
        fontes=fontes,
    )