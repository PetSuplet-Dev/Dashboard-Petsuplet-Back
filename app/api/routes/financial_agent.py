import json
import os
import asyncio
import uuid
import vertexai

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from uuid import UUID as UUID_T
from typing import List, Dict, Any, Tuple, Optional
from starlette.concurrency import run_in_threadpool
from app.config import settings
from app import models, schemas
from app.database.session import get_db
from app.models.users import Users
from app.api.dependencies import get_current_user
from app.core.gemini_client import get_sql_database
from langchain_google_vertexai import ChatVertexAI
from langchain_community.agent_toolkits import create_sql_agent


# --- Helper Function for SQL Result Parsing ---
def _parse_agent_sql_result(agent_response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parses the raw SQL result from the agent's intermediate steps
    into a structured format with headers and rows.
    """
    if (
        "intermediate_steps" not in agent_response
        or not agent_response["intermediate_steps"]
    ):
        return {"headers": [], "rows": []}

    # The result is often a list of tuples within a string, e.g., "[('John Doe', 1500.00), ...]"
    # Or it could be a list of tuples directly.
    raw_result = agent_response["intermediate_steps"][0].get("tool_output", [])

    # The agent does not consistently return headers. A robust solution for a production
    # system would be to parse the SQL query to get column names. For this implementation,
    # we will assume a simple structure or generate generic headers.

    # Try to evaluate the string if it's a string representation of a list
    if isinstance(raw_result, str):
        try:
            # This is a safe evaluation for list/tuple-like structures
            import ast

            parsed_result = ast.literal_eval(raw_result)
        except (ValueError, SyntaxError):
            # If it's just a simple string result, return it as a single cell table
            return {"headers": ["Result"], "rows": [[raw_result]]}
    elif isinstance(raw_result, list):
        parsed_result = raw_result
    else:
        return {"headers": ["Result"], "rows": [[str(raw_result)]]}

    if not parsed_result or not isinstance(parsed_result, list):
        return {"headers": [], "rows": []}

    num_columns = len(parsed_result[0]) if parsed_result else 0
    headers = [f"Column {i+1}" for i in range(num_columns)]

    # The final result should be a list of lists
    rows = [list(row) for row in parsed_result]

    return {"headers": headers, "rows": rows}


router = APIRouter(prefix="/v1/conversations", tags=["Financial Agent IA"])


@router.get("/", response_model=List[schemas.ConversationMinimalResponse])
def get_conversations(
    db: Session = Depends(get_db), current_user: Users = Depends(get_current_user)
):
    return (
        db.query(models.Conversation)
        .filter(models.Conversation.user_id == current_user.id)
        .order_by(models.Conversation.updated_at.desc())
        .all()
    )


@router.post(
    "/",
    response_model=schemas.ConversationDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    payload: schemas.ConversationCreate,
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    new_conv = models.Conversation(
        title=payload.title,
        selected_db=payload.selected_db,
        user_id=current_user.id,
    )
    db.add(new_conv)
    db.commit()
    db.refresh(new_conv)
    return new_conv


@router.get("/{conversation_id}", response_model=schemas.ConversationDetailResponse)
def get_conversation_detail(
    conversation_id: UUID_T,
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    conv = (
        db.query(models.Conversation)
        .filter(
            models.Conversation.id == conversation_id,
            models.Conversation.user_id == current_user.id,
        )
        .first()
    )
    if not conv:
        raise HTTPException(
            status_code=404, detail="Conversation not found or access denied"
        )
    return conv


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: UUID_T,
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    conv = (
        db.query(models.Conversation)
        .filter(
            models.Conversation.id == conversation_id,
            models.Conversation.user_id == current_user.id,
        )
        .first()
    )
    if not conv:
        raise HTTPException(
            status_code=404, detail="Conversation not found or access denied"
        )
    db.delete(conv)
    db.commit()
    return None


# --- Helper Functions for Offloading Synchronous Operations to Threadpool ---
def _get_conversation_sync(
    db: Session, conversation_id: UUID_T, user_id: UUID_T
) -> Optional[models.Conversation]:
    return (
        db.query(models.Conversation)
        .filter(
            models.Conversation.id == conversation_id,
            models.Conversation.user_id == user_id,
        )
        .first()
    )


def _save_user_message_sync(db: Session, conversation_id: UUID_T, prompt: str) -> models.Message:
    user_msg = models.Message(
        conversation_id=conversation_id, role="user", content=prompt
    )
    db.add(user_msg)
    db.commit()
    return user_msg


def _init_sql_agent_sync(selected_db: str, prefix: str):
    llm = ChatVertexAI(
        model_name="gemini-2.5-flash",
        project=settings.GOOGLE_CLOUD_PROJECT,
        location=settings.GOOGLE_CLOUD_LOCATION,
        temperature=0,
    )
    # Seguridad: El agente solo ve la tabla seleccionada con permisos de solo lectura.
    lc_db = get_sql_database(include_tables=[selected_db])
    return create_sql_agent(
        llm,
        db=lc_db,
        agent_type="openai-tools",
        verbose=True,
        prefix=prefix,
    )


def _save_assistant_message_sync(
    db: Session,
    conversation_id: UUID_T,
    content: str,
    has_artifact: bool,
) -> models.Message:
    assistant_msg = models.Message(
        conversation_id=conversation_id,
        role="assistant",
        content=content,
        has_artifact=bool(has_artifact),
    )
    db.add(assistant_msg)
    db.flush()
    return assistant_msg


def _save_canvas_artifact_sync(
    db: Session,
    message_id: UUID_T,
    title: str,
    table_data: Dict[str, Any],
) -> Dict[str, Any]:
    artifact = models.CanvasArtifact(
        message_id=message_id,
        type="table",
        title=title,
        data=table_data,
    )
    db.add(artifact)
    db.commit()
    return {
        "artifact_id": str(artifact.id),
        "type": artifact.type,
        "title": artifact.title,
        "data": artifact.data,
    }


def _commit_db_sync(db: Session) -> None:
    db.commit()


async def event_generator(
    conversation_id: UUID_T, prompt: str, selected_db: str, db: Session
):
    # 1. Guardar mensaje del usuario (offloaded to threadpool)
    await run_in_threadpool(
        _save_user_message_sync, db, conversation_id, prompt
    )

    # 2. Notificar inicio de la consulta SQL
    yield f"event: status_update\ndata: {json.dumps({'status': 'EXECUTING_SQL_QUERY'})}\n\n"

    # 3. Inicializar LangChain SQL Agent REAL
    AGENT_PREFIX = """Eres un agente financiero experto que consulta bases de datos SQL para responder preguntas.

REGLAS DE FORMATO DE RESPUESTA:
1. Cuando la consulta devuelva múltiples registros con campos repetitivos (como facturas, clientes, transacciones, etc.), SIEMPRE presenta los datos en formato de TABLA MARKDOWN.
2. Usa el formato de tabla Markdown con encabezados claros:
   | Columna 1 | Columna 2 | Columna 3 |
   |-----------|-----------|-----------|
   | dato 1    | dato 2    | dato 3    |
3. Usa nombres de columna descriptivos en español (ej: "Factura ID", "Fecha", "Cliente", "Monto Total", "Estado").
4. Formatea valores monetarios con separador de miles y dos decimales (ej: $1,234,567.89).
5. Para resúmenes numéricos simples (totales, promedios, conteos), usa texto con negritas para los valores clave.
6. Siempre incluye un breve contexto ANTES de la tabla explicando qué datos se muestran.
7. Si hay muchos registros, muestra los más relevantes y menciona el total.
8. Responde siempre en español.
"""
    try:
        agent_executor = await run_in_threadpool(
            _init_sql_agent_sync, selected_db, AGENT_PREFIX
        )
    except Exception as e:
        print(f"Error initializing LangChain agent: {e}")
        yield f"event: done\ndata: {json.dumps({'status': 'error', 'message': 'Could not initialize AI agent.'})}\n\n"
        return

    # 4. Ejecutar el agente para obtener la respuesta y el resultado SQL
    try:
        agent_response = await agent_executor.ainvoke({"input": prompt})
        raw_output = agent_response.get("output", "No se pudo generar una respuesta.")

        # Gemini/VertexAI may return content blocks instead of a plain string.
        # e.g. [{'type': 'text', 'text': '...', 'thought_signature': '...'}]
        if isinstance(raw_output, list):
            text_parts = []
            for block in raw_output:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)
            natural_language_response = "".join(text_parts)
        elif hasattr(raw_output, "content"):
            # Handle AIMessage or similar LangChain message objects
            content = raw_output.content
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif isinstance(block, str):
                        text_parts.append(block)
                natural_language_response = "".join(text_parts)
            else:
                natural_language_response = str(content)
        else:
            natural_language_response = str(raw_output)
    except Exception as e:
        print(f"Error invoking LangChain agent: {e}")
        natural_language_response = f"Lo siento, ocurrió un error al procesar la consulta en la base de datos: {e}"
        agent_response = {}  # Ensure agent_response exists

    # 5. Streamear la respuesta de texto (preservando formato Markdown)
    lines = natural_language_response.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped:
            # Table rows and separator lines must be sent as complete lines
            # to preserve the pipe-delimited markdown table structure
            if stripped.startswith("|") or stripped.startswith("|-"):
                yield f"event: text_delta\ndata: {json.dumps({'text': line})}\n\n"
                await asyncio.sleep(0.03)
            else:
                # Normal text: stream word by word for typing effect
                words = line.split()
                for word in words:
                    yield f"event: text_delta\ndata: {json.dumps({'text': word + ' '})}\n\n"
                    await asyncio.sleep(0.02)
        # Emit newline after each line except the last
        if i < len(lines) - 1:
            yield f"event: text_delta\ndata: {json.dumps({'text': chr(10)})}\n\n"

    # 6. Parsear el resultado SQL y crear el artefacto si hay datos
    has_artifact = (
        "intermediate_steps" in agent_response and agent_response["intermediate_steps"]
    )

    # 7. Crear y persistir el mensaje del asistente y, si aplica, el artefacto (offloaded to threadpool)
    assistant_msg = await run_in_threadpool(
        _save_assistant_message_sync,
        db,
        conversation_id,
        natural_language_response,
        bool(has_artifact),
    )

    if has_artifact:
        yield f"event: status_update\ndata: {json.dumps({'status': 'GENERATING_CANVAS'})}\n\n"

        table_data = _parse_agent_sql_result(agent_response)
        artifact_title = f"Resultado para: {prompt[:40]}..."

        # Guardar artefacto en la base de datos via threadpool
        artifact_response_payload = await run_in_threadpool(
            _save_canvas_artifact_sync,
            db,
            assistant_msg.id,
            artifact_title,
            table_data,
        )
        artifact_response_payload["source_db"] = selected_db

        # 8. Enviar el artefacto generado al frontend
        yield f"event: artifact_generated\ndata: {json.dumps(artifact_response_payload)}\n\n"
    else:
        await run_in_threadpool(_commit_db_sync, db)

    # 9. Finalizar el stream
    yield f"event: done\ndata: {json.dumps({'status': 'completed'})}\n\n"


@router.post("/{conversation_id}/messages")
async def send_message_stream(
    conversation_id: UUID_T,
    payload: schemas.MessageCreatePayload,
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    conv = await run_in_threadpool(
        _get_conversation_sync, db, conversation_id, current_user.id
    )
    if not conv:
        raise HTTPException(
            status_code=404, detail="Conversation not found or access denied"
        )

    selected_db = payload.selected_db or conv.selected_db

    return StreamingResponse(
        event_generator(conversation_id, payload.prompt, selected_db, db),
        media_type="text/event-stream",
    )
