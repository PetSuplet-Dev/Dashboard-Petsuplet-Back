from typing import Optional, List
import os
from google import genai
from sqlalchemy import create_engine
from langchain_community.utilities import SQLDatabase
from app.config import settings

# Read-only database engine configured with effective_readonly_db_url
readonly_engine = create_engine(settings.effective_readonly_db_url)


def get_sql_database(include_tables: Optional[List[str]] = None) -> SQLDatabase:
    """
    Instantiates and returns an SQLDatabase using the read-only database connection
    (READONLY_DATABASE_URL) instead of the admin connection, ensuring the agent
    cannot execute INSERT, UPDATE, DELETE, or DROP statements.
    """
    return SQLDatabase(engine=readonly_engine, include_tables=include_tables)


def get_gemini_client() -> genai.Client:
    """
    Inicializa y retorna el cliente de Google GenAI usando la integración con Vertex AI.
    Toma automáticamente las credenciales de ADC (Application Default Credentials).
    """
    return genai.Client(
        vertexai=True, project="civic-indexer-501220-d4", location="us-central1"
    )


def generate_financial_analysis(
    client: genai.Client, invoices_ctx: str, credit_notes_ctx: str
) -> str:
    """
    Construye el prompt y genera el análisis financiero usando gemini-2.5-flash en Vertex AI.
    """
    prompt = f"""
Eres un analista financiero experto. Tienes dos conjuntos de datos: 
Facturas emitidas: {invoices_ctx}
Devoluciones (Notas de crédito): {credit_notes_ctx}

TAREA:
Realiza el razonamiento matemático paso a paso. Suma el monto total de las facturas (price_cop), luego suma el total de las devoluciones (price_cop) que corresponden a notas de crédito, y calcula el ingreso neto (Facturas - Devoluciones).

RESTRICCIÓN:
Debes responder ESTRICTAMENTE con un objeto JSON válido, sin texto adicional ni formato markdown. Utiliza exactamente esta estructura:
{{
    "razonamiento": "Explica brevemente paso a paso cómo hiciste el cálculo",
    "total_facturas": 0.0,
    "total_devoluciones": 0.0,
    "ingreso_neto": 0.0
}}
"""
    # Se llama al modelo Gemini 2.5 Flash alojado en Vertex AI
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    return response.text

