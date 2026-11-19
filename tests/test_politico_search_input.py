import pytest
from pydantic import ValidationError

from src.agents.tool_schemas import PoliticoSearchInput


def test_search_by_name_is_valid():
    data = PoliticoSearchInput(nome="Marina Silva")
    assert data.nome == "Marina Silva"
    assert data.limite == 5


def test_search_by_office_and_state_is_valid():
    data = PoliticoSearchInput(cargo="senador", uf="SP")
    assert data.cargo == "senador"
    assert data.uf == "SP"


def test_search_requires_a_narrowing_filter():
    with pytest.raises(ValidationError):
        PoliticoSearchInput(uf="SP")


def test_search_rejects_unknown_office():
    with pytest.raises(ValidationError):
        PoliticoSearchInput(nome="Pessoa", cargo="ministro")


def test_search_limits_results_to_eight():
    with pytest.raises(ValidationError):
        PoliticoSearchInput(nome="Pessoa", limite=20)


def test_search_normalizes_plural_and_state_name():
    data = PoliticoSearchInput(
        cargo="Senadores",
        uf="São Paulo",
        fase_mandato="Em exercício",
    )
    assert data.cargo == "senador"
    assert data.uf == "SP"
    assert data.fase_mandato == "em_exercicio"
