
import csv
import json
import re
import time
from datetime import datetime
from pathlib import Path

from base_conhecimento import normalizar
from orientacao import Orientacao


class Assistente:
    AVISO = "Aviso: este assistente NÃO é um canal oficial da Justiça Eleitoral."

    def __init__(self, nome, base, pasta_dados="data"):
        self.nome = nome
        self.base = base
        self.pasta_dados = Path(pasta_dados)
        self.arquivo_historico = self.pasta_dados / "historico.json"
        self.arquivo_csv = self.pasta_dados / "atendimentos.csv"
        self.historico = self._carregar_historico()

    def _carregar_historico(self):
        try:
            with self.arquivo_historico.open("r", encoding="utf-8") as arquivo:
                dados = json.load(arquivo)
            return dados if isinstance(dados, list) else []
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    @staticmethod
    def contem_dado_pessoal(texto):
        numeros = re.sub(r"\D", "", texto)

        return (
            "@" in texto
            or len(numeros) >= 8
        )

    def registrar(self, origem, pergunta, id_orientacao, encontrou,
                  ajudou, tentativas, tempo_segundos):
        registro = {
            "data": datetime.now().isoformat(timespec="seconds"),
            "origem": origem,
            "pergunta": pergunta,
            "id_orientacao": id_orientacao,
            "encontrou": bool(encontrou),
            "ajudou": bool(ajudou),
            "tentativas": int(tentativas),
            "tempo_segundos": round(float(tempo_segundos), 1),
        }
        self.historico.append(registro)
        self.pasta_dados.mkdir(parents=True, exist_ok=True)
        with self.arquivo_historico.open("w", encoding="utf-8") as arquivo:
            json.dump(self.historico, arquivo, ensure_ascii=False, indent=4)

    def _perguntar_utilidade(self, origem, pergunta, id_orientacao,
                             encontrou, tentativas, inicio):
        while True:
            resposta = input("Essa orientação ajudou? (s/n): ").strip().lower()
            if resposta in ("s", "n"):
                self.registrar(origem, pergunta, id_orientacao, encontrou,
                               resposta == "s", tentativas, time.time() - inicio)
                return
            print("Entrada inválida. Digite apenas 's' ou 'n'.")

    def perguntar(self):
        inicio = time.time()
        tentativas = 1
        pergunta = input("\nDigite sua dúvida (0 para voltar): ").strip()
        if pergunta == "0":
            return
        if not pergunta:
            print("A pergunta não pode ficar vazia.")
            return
        if self.contem_dado_pessoal(pergunta):
            print("Por privacidade, não digite CPF, telefone, e-mail ou sequências longas de números. Reescreva sem dados pessoais.")
            return

        resultados = self.base.buscar(pergunta)
        if not resultados or resultados[0][0] < 3:
            print("\nNão encontrei uma orientação com pontuação suficiente.")
            print("Tente outras palavras ou navegue pelas categorias.")
            self.registrar("pergunta", pergunta, None, False, False,
                           tentativas, time.time() - inicio)
            return

        pontos, melhor = resultados[0]
        confianca = "ALTA" if pontos >= 6 else "MÉDIA"
        print(f"\nConfiança da resposta: {confianca} ({pontos} pontos)")
        melhor.exibir()
        alternativas = [(p, o) for p, o in resultados[1:] if p >= 3][:2]
        for p, alternativa in alternativas:
            print(f"\nAlternativa ({p} pontos): {alternativa.titulo} [{alternativa.categoria}]")
        self._perguntar_utilidade("pergunta", pergunta, melhor.id, True,
                                  tentativas, inicio)

    def navegar(self):
        categorias = self.base.categorias()
        if not categorias:
            print("A base está vazia.")
            return
        while True:
            print("\nCATEGORIAS")
            for indice, categoria in enumerate(categorias, 1):
                print(f"{indice}. {categoria}")
            print("0. Voltar")
            escolha = input("Escolha: ").strip()
            if escolha == "0":
                return
            if not escolha.isdigit() or not (1 <= int(escolha) <= len(categorias)):
                print("Opção inválida.")
                continue
            categoria = categorias[int(escolha) - 1]
            orientacoes = self.base.por_categoria(categoria)
            while True:
                print(f"\n{categoria.upper()}")
                for indice, orientacao in enumerate(orientacoes, 1):
                    print(f"{indice}. {orientacao.titulo}")
                print("0. Voltar")
                opcao = input("Escolha uma orientação: ").strip()
                if opcao == "0":
                    break
                if not opcao.isdigit() or not (1 <= int(opcao) <= len(orientacoes)):
                    print("Opção inválida.")
                    continue
                inicio = time.time()
                selecionada = orientacoes[int(opcao) - 1]
                selecionada.exibir()
                pergunta = selecionada.titulo
                self._perguntar_utilidade("categoria", pergunta, selecionada.id,
                                          True, 1, inicio)

    def menu_dsa(self):
        while True:
            print("\nGERENCIAR ORIENTAÇÕES (DSA)")
            print("1. Cadastrar | 2. Consultar por ID | 3. Pesquisar título/categoria")
            print("4. Atualizar | 5. Excluir | 6. Ordenar por título")
            print("7. Listar todas | 0. Voltar")
            opcao = input("Escolha: ").strip()
            if opcao == "0":
                return
            if opcao == "1":
                self._cadastrar()
            elif opcao == "2":
                self._consultar_id()
            elif opcao == "3":
                termo = input("Termo de pesquisa: ").strip()
                if not termo:
                    print("Pesquisa vazia.")
                    continue
                encontrados = self.base.pesquisar_atributo(termo)
                self._listar(encontrados)
            elif opcao == "4":
                self._atualizar()
            elif opcao == "5":
                self._excluir()
            elif opcao == "6":
                self.base.ordenar_por_titulo()
                print("Lista ordenada por título (Insertion Sort).")
            elif opcao == "7":
                self._listar(list(self.base.orientacoes.percorrer()))
            else:
                print("Opção inválida.")

    def _ler_id(self, mensagem):
        valor = input(mensagem).strip()
        if not valor.isdigit():
            print("ID deve ser um número inteiro positivo.")
            return None
        return int(valor)

    def _coletar_dados(self, identificador):
        print("Use '|' para separar palavras-chave e documentos.")
        categoria = input("Categoria: ").strip()
        titulo = input("Título: ").strip()
        palavras = [x.strip() for x in input("Palavras-chave: ").split("|") if x.strip()]
        resposta = input("Orientação/resposta: ").strip()
        documentos = [x.strip() for x in input("Documentos/requisitos: ").split("|") if x.strip()]
        onde = input("Onde/como: ").strip()
        fonte = input("URL da fonte oficial: ").strip()
        verificado = input("Verificado em (AAAA-MM-DD): ").strip()
        if not all([categoria, titulo, palavras, resposta, onde, fonte, verificado]):
            print("Todos os campos textuais e ao menos uma palavra-chave são obrigatórios.")
            return None
        if len(palavras) < 3:
            print("Cadastre pelo menos 3 palavras-chave.")
            return None
        return {
            "id": identificador, "categoria": categoria, "titulo": titulo,
            "palavras_chave": palavras, "resposta": resposta,
            "documentos": documentos, "onde": onde, "fonte": fonte,
            "verificado_em": verificado
        }

    def _cadastrar(self):
        identificador = self._ler_id("Novo ID: ")
        if identificador is None:
            return
        if self.base.por_id(identificador):
            print("ID duplicado. Cadastro cancelado.")
            return
        dados = self._coletar_dados(identificador)
        if dados and self.base.adicionar(Orientacao(dados)):
            print("Orientação cadastrada e salva.")

    def _consultar_id(self):
        identificador = self._ler_id("ID: ")
        if identificador is None:
            return
        orientacao = self.base.por_id(identificador)
        if orientacao:
            orientacao.exibir()
        else:
            print("Nenhum registro encontrado.")

    def _atualizar(self):
        identificador = self._ler_id("ID a atualizar: ")
        if identificador is None:
            return
        if self.base.por_id(identificador) is None:
            print("Nenhum registro encontrado.")
            return
        dados = self._coletar_dados(identificador)
        if dados and self.base.atualizar(identificador, dados):
            print("Orientação atualizada.")

    def _excluir(self):
        identificador = self._ler_id("ID a excluir: ")
        if identificador is None:
            return
        if self.base.excluir(identificador):
            print("Orientação excluída.")
        else:
            print("Nenhum registro encontrado.")

    @staticmethod
    def _listar(orientacoes):
        if not orientacoes:
            print("Nenhum resultado encontrado.")
            return
        for o in orientacoes:
            print(f"[{o.id}] {o.titulo} — {o.categoria}")

    def indicadores(self):
        total = len(self.historico)
        if total == 0:
            print("\nAinda não existem atendimentos registrados.")
            return
        encontrados = sum(1 for h in self.historico if h["encontrou"])
        ajudaram = sum(1 for h in self.historico if h["ajudou"])
        tempo = sum(h["tempo_segundos"] for h in self.historico) / total
        tentativas = sum(h["tentativas"] for h in self.historico) / total
        notas = [h["facilidade"] for h in self.historico if "facilidade" in h]
        sem_solucao = [h["pergunta"] for h in self.historico if not h["encontrou"]]
        print("\nINDICADORES")
        print(f"Atendimentos registrados: {total}")
        print(f"Respostas encontradas: {encontrados / total * 100:.1f}%")
        print(f"Taxa de acerto percebida (ajudou): {ajudaram / total * 100:.1f}%")
        print(f"Tempo médio: {tempo:.1f} segundos")
        print(f"Tentativas médias: {tentativas:.1f}")
        print(f"Facilidade média (1 a 5): {sum(notas) / len(notas):.2f}" if notas else "Facilidade média: ainda sem notas")
        print("Dúvidas sem solução:")
        for pergunta in sem_solucao:
            print(f"  - {pergunta}")

    def coletar_nota_facilidade(self):
        while True:
            nota = input("Avalie a facilidade de uso (1 a 5): ").strip()
            if nota in ("1", "2", "3", "4", "5"):
                self.historico.append({
                    "data": datetime.now().isoformat(timespec="seconds"),
                    "origem": "avaliacao", "pergunta": "facilidade de uso",
                    "id_orientacao": None, "encontrou": True,
                    "ajudou": False, "tentativas": 1, "tempo_segundos": 0.0,
                    "facilidade": int(nota)
                })
                with self.arquivo_historico.open("w", encoding="utf-8") as arquivo:
                    json.dump(self.historico, arquivo, ensure_ascii=False, indent=4)
                return
            print("Digite uma nota de 1 a 5.")

    def exportar_csv(self):
        campos = ["data", "origem", "pergunta", "id_orientacao", "encontrou",
                  "ajudou", "tentativas", "tempo_segundos", "facilidade"]
        self.pasta_dados.mkdir(parents=True, exist_ok=True)
        with self.arquivo_csv.open("w", newline="", encoding="utf-8-sig") as arquivo:
            escritor = csv.DictWriter(arquivo, fieldnames=campos)
            escritor.writeheader()
            for registro in self.historico:
                escritor.writerow({campo: registro.get(campo, "") for campo in campos})
        print(f"CSV exportado em: {self.arquivo_csv}")
