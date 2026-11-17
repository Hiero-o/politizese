from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

# Configurações

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data"

app = FastAPI(
    title="Politizese API",
    description="API de dados geográficos do projeto politizese.",
    version="0.1.0",
)


# CORS

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


# Registro das camadas geográficas

LAYERS = {
    "obras": {
        "name": "Obras públicas",
        "description": "Obras e intervenções públicas da cidade de São Paulo.",
        "category": "infraestrutura",
        "geometry": "Point",
        "path": DATA_DIR / "obras" / "processed" / "obras_sp.geojson",
    },

    "risco_hidrologico": {
        "name": "Áreas de risco hidrológico",
        "description": "Áreas mapeadas com risco hidrológico.",
        "category": "risco_ambiental",
        "geometry": "Polygon",
        "path": (
            DATA_DIR
            / "geosampa"
            / "processed"
            / "risco_hidrologico_wfs.geojson"
        ),
    },

    "risco_geologico": {
        "name": "Áreas de risco geológico",
        "description": "Setores mapeados com risco geológico.",
        "category": "risco_ambiental",
        "geometry": "Polygon",
        "path": (
            DATA_DIR
            / "geosampa"
            / "processed"
            / "risco_geologico_wfs.geojson"
        ),
    },

    "alagamentos": {
        "name": "Ocorrências de alagamento",
        "description": "Registros de ocorrências de alagamento.",
        "category": "ocorrencias",
        "geometry": "Point",
        "path": (
            DATA_DIR
            / "geosampa"
            / "processed"
            / "ocorrencias_alagamento.geojson"
        ),
    },

    "inundacoes": {
        "name": "Ocorrências de inundação",
        "description": "Registros de ocorrências de inundação.",
        "category": "ocorrencias",
        "geometry": "Point",
        "path": (
            DATA_DIR
            / "geosampa"
            / "processed"
            / "ocorrencias_inundacao.geojson"
        ),
    },

    "deslizamentos": {
        "name": "Ocorrências de deslizamento",
        "description": "Registros de ocorrências de deslizamento.",
        "category": "ocorrencias",
        "geometry": "Point",
        "path": (
            DATA_DIR
            / "geosampa"
            / "processed"
            / "ocorrencias_deslizamento.geojson"
        ),
    },

    "quedas_arvores": {
        "name": "Ocorrências de queda de árvores",
        "description": "Registros de ocorrências de queda de árvores.",
        "category": "ocorrencias",
        "geometry": "Point",
        "path": (
            DATA_DIR
            / "geosampa"
            / "processed"
            / "ocorrencias_queda_arvore.geojson"
        ),
    },
}

@app.get("/")
def home():
    return {
        "project": "Politizese",
        "status": "online",
        "version": "0.1.0",
        "documentation": "/docs",
        
    }
    
    
    
#Verificação de saúde


@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "Politize-se API",
    }
    
#listagem das camadas

@app.get("/api/map/layers")
def list_map_layers():
    layers = []
    
    
    for layer_id, config in LAYERS.items():
        arquivo_existe = config["path"].is_file()
        
        layers.append({
            "id": layer_id,
            "name": config["name"],
            "description": config["description"],
            "category": config["category"],
            "geometry": config["geometry"],
            "available": arquivo_existe,
            "endpoint": (
                f"/api/map/layers/{layer_id}"
                if arquivo_existe
                else None
            ),
        })
    return {
        "total": len(layers),
        "available": sum(
            layer["available"] for layer in layers
        ),
        "layers": layers,
    }
    
# Disponibilização dos geojsons

@app.get("/api/map/layers/{layer_id}")
def get_map_layer(layer_id: str):
    config = LAYERS.get(layer_id)
    
    if config is None:
        raise HTTPException(
            status_code=404,
            detail="Camda geográfica não encontrada.",
        )

    caminho_arquivo = config["path"]
    
    if not caminho_arquivo.is_file():
        raise HTTPException(
            status_code=503,
            detail=(
                f"Arquivo da camada '{layer_id} não está dispomivel."
            ),
        )
        
    return FileResponse(
        path=caminho_arquivo,
        media_type="application/get+json",
    )