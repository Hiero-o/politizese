import re
import xml.etree.ElementTree as ET
from pathlib import Path

from src.core.config import PROJECT_ROOT


#Diretório principais dos propmpts

PROMPTS_DIRECTORY = PROJECT_ROOT / "prompts"


def _resolve_prompt_path(
    category:str,
    name: str,
) -> Path:
    
    """Localiza um arquivo XML dentro da categoria informada.
    
    Aceita somente identificadores simples, evitando caminhos arbitrários ou acesso a outros diretórios."""
    
    
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", name):
        raise ValueError(f"Identificador de prompt inválido: {name!r}")
    
    
    directory = (
        PROMPTS_DIRECTORY / category
    ).resolve()
    
    prompt_path = (
        directory / f"{name}.xml"
    ).resolve()
    
    if directory not in prompt_path.parents:
        raise ValueError("O caminhoi do prompt está fora do diretório permitido")
    
    return prompt_path


def _load_xml(
    category: str,
    name: str,
    expected_root: str,
) -> ET.Element:
    
    """Carrega e valida um arquivo XML.
    
    Verificando:
    - Existencia do arquivo;
    - Conteúdo não vazio;
    - Sintaxe XML;
    - Elemento raiz esperado."""
    
    
    prompt_path = _resolve_prompt_path(category, name)
    
    if not prompt_path.is_file():
        raise FileNotFoundError(f"Prompt não encotrado: {prompt_path}")
    
    try:
        tree = ET.parse(prompt_path)
        root = tree.getroot()
        
    except ET.ParseError as error:
        raise ValueError(f"XML inválida em {prompt_path}: {error}") from error
    
    except OSError as error:
        raise RuntimeError(f"Não foi possível ler o prompt: {prompt_path}")
    
    if root.tag != expected_root:
        raise ValueError(
            f"Raiz XML inválida em {prompt_path}"
            f"Esperado: <{expected_root}>"
            f"Encontrado: <{root.tag}>"
        )
        
    #Verifica se existe conteúdo textual significativo.
    
    content = "".join(root.itertext())
    
    if not content.strip():
        raise ValueError(f"O prompt está vazio: {prompt_path}")
    
    #Verifica a identificação declarada pela Task ou Style.
    
    declared_name = root.get("name")
    
    if declared_name and declared_name != name:
        raise ValueError(
            f"O nome declarado no XML ({declared_name})"
            f"Não corresponde ao arquivo ({name})"
        )
        
    return root


def load_prompt(
    task:str,
    style:str | None = None
) -> str: 
    """
    Carrega e combina o Core, uma Task e um Style opcional.

    Ordem de composição:
        1. Politize-se Core.
        2. Task solicitada.
        3. Style opcional.

    Args:
        task: identificador do arquivo dentro de prompts/tasks.
        style: identificador opcional dentro de prompts/styles.

    Returns:
        String contendo o documento XML completo.
    """
    
    # 1. Carrega as instruções fundamentais.
    core = _load_xml(
        category="core",
        name="politizese_core",
        expected_root="system",
    )

    # 2. Carrega a tarefa solicitada.
    task_root = _load_xml(
        category="tasks",
        name=task,
        expected_root="task",
    )

    # 3. Cria o documento que reunirá os prompts.
    prompt_bundle = ET.Element(
        "prompt_bundle",
        {
            "application": "Politize-se",
            "version": "1.0",
        },
    )

    prompt_bundle.append(core)
    prompt_bundle.append(task_root)

    # 4. Carrega o estilo somente quando solicitado.
    if style is not None:

        style_root = _load_xml(
            category="styles",
            name=style,
            expected_root="style_profile",
        )

        prompt_bundle.append(style_root)

    # 5. Converte o documento completo para texto XML.
    return ET.tostring(
        prompt_bundle,
        encoding="unicode",
        xml_declaration=True,
    )

    