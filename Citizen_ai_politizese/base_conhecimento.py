
import json
import unicodedata
from pathlib import Path

from orientacao import Orientacao



class No:
    """Nó da lista: armazena um objeto e a referência ao próximo nó."""
    def __init__(self, dado):
        self.dado = dado
        self.proximo = None


class ListaEncadeada:
    """Lista simplesmente encadeada com referências para início e fim."""
    def __init__(self):
        self.inicio = None
        self.fim = None
        self.tamanho = 0

    def __len__(self):
        return self.tamanho

    def esta_vazia(self):
        return self.inicio is None

    def inserir_fim(self, dado):
        novo = No(dado)
        if self.esta_vazia():
            self.inicio = self.fim = novo
        else:
            self.fim.proximo = novo
            self.fim = novo
        self.tamanho += 1

    def percorrer(self):
        atual = self.inicio
        while atual is not None:
            yield atual.dado
            atual = atual.proximo

    def buscar(self, criterio):
        atual = self.inicio
        while atual is not None:
            if criterio(atual.dado):
                return atual.dado
            atual = atual.proximo
        return None

    def remover(self, criterio):
        anterior = None
        atual = self.inicio
        while atual is not None:
            if criterio(atual.dado):
                if anterior is None:
                    self.inicio = atual.proximo
                else:
                    anterior.proximo = atual.proximo
                if atual is self.fim:
                    self.fim = anterior
                self.tamanho -= 1
                if self.tamanho == 0:
                    self.inicio = self.fim = None
                atual.proximo = None
                return atual.dado
            anterior, atual = atual, atual.proximo
        return None

    def insertion_sort(self, chave):
        """Insertion Sort nos próprios nós, sem converter a lista em array."""
        ordenada = None
        atual = self.inicio
        while atual is not None:
            proximo_original = atual.proximo
            atual.proximo = None
            if ordenada is None or chave(atual.dado) < chave(ordenada.dado):
                atual.proximo = ordenada
                ordenada = atual
            else:
                cursor = ordenada
                while cursor.proximo is not None and chave(cursor.proximo.dado) <= chave(atual.dado):
                    cursor = cursor.proximo
                atual.proximo = cursor.proximo
                cursor.proximo = atual
            atual = proximo_original
        self.inicio = ordenada
        self.fim = None
        cursor = self.inicio
        while cursor is not None:
            self.fim = cursor
            cursor = cursor.proximo

    def substituir_todos(self, dados):
        self.inicio = self.fim = None
        self.tamanho = 0
        for dado in dados:
            self.inserir_fim(dado)


def normalizar(texto):
    """Minúsculas, sem acentos e com pontuação convertida em espaços."""
    texto = unicodedata.normalize("NFD", str(texto).lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return " ".join("".join(c if c.isalnum() else " " for c in texto).split())


class BaseConhecimento:
    def __init__(self, caminho):
        self.caminho = Path(caminho)
        self.orientacoes = ListaEncadeada()

    def carregar(self):
        """Lê o JSON e insere objetos Orientacao na lista encadeada."""
        self.orientacoes = ListaEncadeada()
        try:
            with self.caminho.open("r", encoding="utf-8") as arquivo:
                dados = json.load(arquivo)
            if not isinstance(dados, list):
                raise ValueError("A raiz do JSON precisa ser uma lista.")
            ids = set()
            for item in dados:
                orientacao = Orientacao(item)
                if orientacao.id in ids:
                    raise ValueError(f"ID duplicado na base: {orientacao.id}")
                ids.add(orientacao.id)
                self.orientacoes.inserir_fim(orientacao)
            return True
        except FileNotFoundError:
            print(f"Aviso: arquivo não encontrado: {self.caminho}")
        except (json.JSONDecodeError, ValueError, TypeError) as erro:
            print(f"Aviso: não foi possível carregar a base: {erro}")
        self.orientacoes = ListaEncadeada()
        return False

    def salvar(self):
        """Persiste os registros atuais em JSON."""
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        temporario = self.caminho.with_suffix(".tmp")
        with temporario.open("w", encoding="utf-8") as arquivo:
            json.dump([o.para_dict() for o in self.orientacoes.percorrer()],
                      arquivo, ensure_ascii=False, indent=4)
        temporario.replace(self.caminho)

    def categorias(self):
        return sorted({o.categoria for o in self.orientacoes.percorrer()})

    def por_categoria(self, categoria):
        alvo = normalizar(categoria)
        return [o for o in self.orientacoes.percorrer()
                if normalizar(o.categoria) == alvo]

    def por_id(self, identificador):
        return self.orientacoes.buscar(lambda o: o.id == identificador)

    def pesquisar_atributo(self, termo):
        alvo = normalizar(termo)
        if not alvo:
            return []
        return [o for o in self.orientacoes.percorrer()
                if alvo in normalizar(o.titulo)
                or alvo in normalizar(o.categoria)
                or any(alvo in normalizar(p) for p in o.palavras_chave)]

    def adicionar(self, orientacao):
        if self.por_id(orientacao.id) is not None:
            return False
        self.orientacoes.inserir_fim(orientacao)
        self.salvar()
        return True

    def atualizar(self, identificador, novos_dados):
        atual = self.por_id(identificador)
        if atual is None:
            return False
        novos_dados["id"] = identificador
        substituta = Orientacao(novos_dados)
        # Remove o registro antigo e insere a versão atualizada.
        self.orientacoes.remover(lambda o: o.id == identificador)
        self.orientacoes.inserir_fim(substituta)
        self.salvar()
        return True

    def excluir(self, identificador):
        removida = self.orientacoes.remover(lambda o: o.id == identificador)
        if removida is not None:
            self.salvar()
            return True
        return False

    def ordenar_por_titulo(self):
        self.orientacoes.insertion_sort(lambda o: normalizar(o.titulo))
        self.salvar()

    def pontuar(self, pergunta, orientacao):
        """Pontuação PCP: +3 por palavra-chave presente; +1 por palavra do título."""
        pergunta_n = f" {normalizar(pergunta)} "
        pontos = 0
        for palavra in orientacao.palavras_chave:
            chave = normalizar(palavra)
            if chave and f" {chave} " in pergunta_n:
                pontos += 3

        palavras_pergunta = set(normalizar(pergunta).split())
        palavras_titulo = set(normalizar(orientacao.titulo).split())
        pontos += sum(1 for palavra in palavras_pergunta
                      if len(palavra) >= 4 and palavra in palavras_titulo)
        return pontos

    def buscar(self, pergunta):
        """Devolve lista de tuplas (pontos, orientacao), da maior para a menor."""
        resultados = [(self.pontuar(pergunta, o), o)
                      for o in self.orientacoes.percorrer()]
        # Ordenação por inserção para manter a solução didática sem depender de sort().
        ordenados = []
        for item in resultados:
            indice = 0
            while indice < len(ordenados) and ordenados[indice][0] >= item[0]:
                indice += 1
            ordenados.insert(indice, item)
        return ordenados
