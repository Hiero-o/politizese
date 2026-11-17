import json
import requests

BASE_URL = "https://dadosabertos.camara.leg.br/api/v2"


def consultar_api(url, params= None):
    response = requests.get(
        url,
        params=params,
        headers={
            "Accept": "application/json",
        },
        timeout=30,
    )
    
    response.raise_for_status()
    
    return response.json()



def main():
    print("\n Politizese | Inspeção da api da câmara")
    print("=" * 50)
    
    #Consultar deptuados em exercício 
    
    print("\nConsultando os primeiros deputados")
    
    resposta = consultar_api(
        f"{BASE_URL}/deputados",
        params={
            "pagina": 1,
            "itens": 5,
            "ordem": "ASC",
            "ordenarPor": "nome",
        },
    )
    
    
    deputados = resposta.get("dados", [])
    links = resposta.get("links", [])
    
    print(f"\nDeputados recebidos: {len(deputados)}")

    print("\nEstrutura da resposta:")
    print(f"Campos principais: {list(resposta.keys())}")

    print("\nLinks de paginação:")
    
    
    for link in links:
        print(
            f" {link.get('rel')}: "
            f"{link.get('href')}"
        )
        
        
    #Examinar os campos dos deputados
    
    
    print("\n" + "=" * 60)
    print("DADOS DA LISTAGEM")
    print("=" * 60)
    
    for deputado in deputados:
        print("\nDeputado:")
        
        for campo, valor in deputado.items():
            print(f"    {campo}: {valor}")
            
            
    
    # Consultar o perfil do primeiro candidatos
    
    if not deputados:
        print("\nNenhum deputado retornado")
        return
    
    primeiro = deputados[0]
    
    deputado_id = primeiro.get("id")
    
    if deputado_id is None:
        print("\nIdentificador não encontrado")
        return
    
    print("\n" + "=" * 60)
    print(f"Perfil Individual (ID): {deputado_id}")
    print("=" * 60)
    
    perfil = consultar_api(f"{BASE_URL}/deputados/{deputado_id}")
    
    print(json.dumps(
        perfil,
        indent=2,
        ensure_ascii=False,
    ))
    
    print("\nInspeção Finalizada")
    
    
if __name__ == "__main__":
    main()