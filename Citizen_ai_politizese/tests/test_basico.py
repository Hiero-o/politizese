
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from base_conhecimento import BaseConhecimento
from assistente import Assistente


def criar_base(tmp_path):
    caminho = tmp_path / "base.json"
    import json
    origem = Path(__file__).resolve().parents[1] / "data" / "base_conhecimento.json"
    caminho.write_text(origem.read_text(encoding="utf-8"), encoding="utf-8")
    base = BaseConhecimento(caminho)
    assert base.carregar()
    return base


def test_base_tem_minimo_de_registros_e_categorias(tmp_path):
    base = criar_base(tmp_path)
    assert len(base.orientacoes) >= 10
    assert len(base.categorias()) >= 3


def test_busca_retorna_tuplas_e_encontra_primeiro_titulo(tmp_path):
    base = criar_base(tmp_path)
    resultados = base.buscar("Como tirar meu primeiro título de eleitor?")
    assert resultados[0][0] >= 3
    assert resultados[0][1].id == 1


def test_lista_encadeada_crud_e_ordenacao(tmp_path):
    base = criar_base(tmp_path)
    base.ordenar_por_titulo()
    from base_conhecimento import normalizar
    titulos = [normalizar(o.titulo) for o in base.orientacoes.percorrer()]
    assert titulos == sorted(titulos)
    assert base.excluir(14)
    assert base.por_id(14) is None


def test_bloqueio_de_dados_pessoais():
    assert Assistente.contem_dado_pessoal("meu documento 12345678")
    assert Assistente.contem_dado_pessoal("contato teste@exemplo.com")
    assert not Assistente.contem_dado_pessoal("como tirar meu título?")
