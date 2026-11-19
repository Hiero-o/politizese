"""Interface Gradio do assistente Politize-se (histórico + referências)."""

from __future__ import annotations

from uuid import UUID, uuid4

import gradio as gr

from backend.services.assistente import (
    limpar_sessao,
    responder_mensagem,
)


def formatar_resposta(result) -> str:
    partes = [result.answer]

    if result.sources:
        partes.append("\n\n---\n**Referências consultadas**")
        for source in result.sources:
            if source.kind == "politico":
                partes.append(
                    f"- **{source.title}** — {source.detail or 'Registro do catálogo'} "
                    f"(perfil interno: `{source.id}`)"
                )
            else:
                trecho = f": {source.excerpt}" if source.excerpt else ""
                partes.append(
                    f"- **{source.title}** — `{source.id}`{trecho}"
                )

    if result.trace:
        used = []
        for entry in result.trace:
            if entry.action.startswith("guardrail_"):
                continue
            if entry.action not in used:
                used.append(entry.action)
        if used:
            partes.append(
                "\n\n**Ferramentas utilizadas:** " + ", ".join(used)
            )

    partes.append(
        f"\n\n<sub>Tempo de processamento: "
        f"{result.total_duration_seconds:.1f}s</sub>"
    )
    return "\n".join(partes)


def responder(message: str, history: list[dict], session_id: str):
    if not message or not message.strip():
        return "", history, session_id

    result = responder_mensagem(
        session_id=UUID(session_id),
        message=message.strip(),
    )

    updated_history = list(history or [])
    updated_history.extend(
        [
            {"role": "user", "content": message.strip()},
            {"role": "assistant", "content": formatar_resposta(result)},
        ]
    )
    return "", updated_history, session_id


def nova_conversa(session_id: str):
    try:
        limpar_sessao(UUID(session_id))
    except (ValueError, TypeError):
        pass
    return [], "", str(uuid4())


with gr.Blocks(title="Politize-se AI", theme=gr.themes.Soft()) as demo:
    gr.Markdown(
        "# Politize-se AI\n"
        "Assistente político-constitucional com fontes rastreáveis e modelos locais."
    )

    session_state = gr.State(str(uuid4()))
    chatbot = gr.Chatbot(
        type="messages",
        height=560,
        label="Conversa",
        placeholder="Faça uma pergunta sobre política, Constituição ou representantes.",
    )

    with gr.Row():
        message = gr.Textbox(
            placeholder="Digite sua pergunta...",
            label="Mensagem",
            scale=8,
            lines=2,
        )
        send = gr.Button("Enviar", variant="primary", scale=1)

    clear = gr.Button("Nova conversa", variant="secondary")
    gr.Markdown(
        "As respostas podem conter erros. Confira as referências exibidas e não envie dados pessoais."
    )

    send.click(
        responder,
        inputs=[message, chatbot, session_state],
        outputs=[message, chatbot, session_state],
    )
    message.submit(
        responder,
        inputs=[message, chatbot, session_state],
        outputs=[message, chatbot, session_state],
    )
    clear.click(
        nova_conversa,
        inputs=[session_state],
        outputs=[chatbot, message, session_state],
    )


if __name__ == "__main__":
    demo.queue(default_concurrency_limit=1).launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False,
    )
