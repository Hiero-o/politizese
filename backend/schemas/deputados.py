from datetime import date

from pydantic import BaseModel, ConfigDict, Field

# Gabiente

class GabineteDeputado(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    nome: str | None = None
    predio: str | None = None
    sala: str | None = None
    andar: str | None = None
    telefone: str | None = None
    email: str | None = None
    

    # Deputado - Listagem
    
class DeputadoResumo(BaseModel):
    
    #Informações necessárias para exibir um deputado na listagem e nos cards do Politizese..
    
    model_config = ConfigDict(extra="ignore")
    
    id: int
    nome:str
    partido: str | None = None
    uf: str | None = None
    id_legislatura: int | None = None
    foto_url: str | None = None
    email: str | None = None
    fotne_url: str | None = None
    
    
#Deputado - perfil Individual
    
class DeputadoPerfil(DeputadoResumo):
    # Informações adicionais para o perdil indiivual do político.
    
    nome_eleitoral: str | None = None
    situacao: str | None = None
    condicao_eleitoral: str | None = None
    data_inicio_exercicio: str | None = None
    
    gabinete: GabineteDeputado | None = None
    
    redes_sociais: list[str] = Field(default_factory=list)
    
    website: str | None = None
    
    
#Resposta da listagem
    
class ListaDeputadosResponse(BaseModel):
    # Resultado paginado da comsulta de deputados.
    
    dados: list[DeputadoResumo]
    pagina: int
    itens: int
    tem_proxima: bool
    

    