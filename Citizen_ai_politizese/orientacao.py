
class Orientacao:
    """Representa uma orientação eleitoral carregada da base JSON."""

    def __init__(self, dados):
        campos = (
            "id", "categoria", "titulo", "palavras_chave", "resposta",
            "documentos", "onde", "fonte", "verificado_em"
        )
        ausentes = [campo for campo in campos if campo not in dados]
        if ausentes:
            raise ValueError(f"Campos obrigatórios ausentes: {', '.join(ausentes)}")

        self.id = int(dados["id"])
        self.categoria = str(dados["categoria"])
        self.titulo = str(dados["titulo"])
        self.palavras_chave = list(dados["palavras_chave"])
        self.resposta = str(dados["resposta"])
        self.documentos = list(dados["documentos"])
        self.onde = str(dados["onde"])
        self.fonte = str(dados["fonte"])
        self.verificado_em = str(dados["verificado_em"])

    def para_dict(self):
        """Converte o objeto para o formato persistido no JSON."""
        return {
            "id": self.id,
            "categoria": self.categoria,
            "titulo": self.titulo,
            "palavras_chave": self.palavras_chave,
            "resposta": self.resposta,
            "documentos": self.documentos,
            "onde": self.onde,
            "fonte": self.fonte,
            "verificado_em": self.verificado_em,
        }

    def exibir(self):
        print(f"\n[{self.id}] {self.titulo} — {self.categoria}")
        print(self.resposta)
        if self.documentos:
            print("Documentos/requisitos:")
            for item in self.documentos:
                print(f"  - {item}")
        print(f"Onde/como: {self.onde}")
        print(f"Fonte oficial: {self.fonte}")
        print(f"Informação verificada em: {self.verificado_em}")
        print("Aviso: este assistente NÃO é um canal oficial da Justiça Eleitoral.")
