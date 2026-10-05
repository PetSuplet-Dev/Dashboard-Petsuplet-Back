# Backend API / PetSuplet Backend

Este es el repositorio central del Backend para **PetSuplet**, construido en **Python** utilizando un enfoque modular y escalable. Cuenta con integraciones avanzadas de inteligencia artificial (Gemini), gestión de facturación y un sistema seguro de autenticación.

---

## 🚀 Comenzando

Sigue estos pasos para configurar el entorno de desarrollo local.

### Prerrequisitos

- **Python 3.10+** instalado.
- Sistema de gestión de entornos virtuales (`venv` o `conda`).

### Instalación y Configuración

1. **Clonar el repositorio:**
   ```bash
   git clone [https://github.com/PetSuplet-Dev/PetSuplet-Backend.git](https://github.com/PetSuplet-Dev/PetSuplet-Backend.git)
   cd PetSuplet-Backend
   ```

---

1. **Crear y activar un entorno virtual:**
   - En Linux/Mac:
     `python3 -m venv venv`
     `source venv/bin/activate`
   - En Windows:
     `python -m venv venv`
     `venv\Scripts\activate`
2. **Instalar dependencias:**
   `pip install -r requirements.txt`

3. **Configurar las variables de entorno (.env):**
   `cp .env.example .env`

4. **Ejecutar la aplicación:**
   `python manage.py runserver`

   > El servidor estará disponible en http://localhost:8000 y la documentación interactiva (Swagger) en http://localhost:8000/docs.

## 🏗️ Arquitectura y Estructura Modular

El proyecto está estructurado bajo el directorio raíz App, dividiendo las responsabilidades de forma estricta para asegurar que el código sea desacoplado y fácil de testear:

```
├── App/
│   ├── api/                  # Capa de enrutamiento y exposición de la API
│   │   ├── endpoints/        # Controladores individuales por recurso
│   │   │   ├── credit_notes.py  # Rutas para Notas de Crédito
│   │   │   ├── ia_auth.py       # Rutas de autenticación inteligente
│   │   │   └── invoices.py      # Rutas para Facturas
│   │   └── api.py            # Enrutador principal que unifica los endpoints
│   │
│   ├── core/                 # Lógica nuclear, seguridad y servicios externos
│   │   ├── gemini_client.py  # Cliente y wrappers para la API de Google Gemini
│   │   └── security.py       # Encriptación, hashing de contraseñas y manejo de JWT
│   │
│   ├── database/             # Configuración del motor de Base de Datos
│   │   └── session.py        # Gestión del ciclo de vida de la conexión (Sesiones)
│   │
│   ├── models/               # Modelos ORM (Estructura de tablas de la BD)
│   │   ├── credit_note.py    # Modelo de base de datos para Notas de Crédito
│   │   └── invoice.py        # Modelo de base de datos para Facturas
│   │
│   ├── resources/            # Archivos estáticos o datos semilla (Seeds/Mocks)
│   │   ├── creditNotes.json
│   │   └── invoices.json
│   │
│   ├── schemas/              # Modelos de validación de datos (Pydantic)
│   │   ├── credit_note.py    # Esquemas de entrada/salida para Notas de Crédito
│   │   └── invoice.py        # Esquemas de entrada/salida para Facturas
│   │
│   ├── config.py             # Configuración centralizada de variables de entorno
│   └── main.py               # Punto de entrada de la aplicación (Instancia de la App)
│
├── .env.example              # Plantilla de configuración de entorno
├── .gitignore                # Archivos excluidos de Git
├── README.md                 # Esta documentación
└── requirements.txt          # Lista de dependencias del proyecto
```

## 🎨 Buenas Prácticas y Estándares de Código

Para garantizar la consistencia entre el equipo y el mantenimiento del sistema, se deben cumplir las siguientes directrices de diseño:

### Flujo de Datos Estricto (Modularidad)

Para cualquier funcionalidad o endpoint nuevo, debes respetar rigurosamente la separación de capas:

- Model (`models/`): Define cómo se guardan los datos en la BD.
- Schema (`schemas/`): Define cómo se reciben y validan los datos (Request) y cómo se envían al cliente (Response).
- Endpoint (`api/endpoints/`): Maneja la solicitud HTTP, invoca los servicios necesarios y retorna el Schema.

> 🚫 **Regla de oro**: Nunca expongas un Model de la base de datos directamente en un Endpoint. Usa siempre un Schema de Pydantic para filtrar y validar la salida.

### Control de Tipado

- Aprovecha el tipado estático de Python (typing). Todas las funciones deben declarar el tipo de sus argumentos y su tipo de retorno (ej. def get_invoice(id: int) -> InvoiceSchema:).

### Conexiones a Base de Datos

- Toda interacción con la base de datos a nivel de endpoint debe utilizar inyección de dependencias para asegurar que las sesiones se abran y cierren correctamente, evitando fugas de memoria o conexiones colgadas (database/session.py).

### Integraciones de IA

- Cualquier llamada, prompt o procesamiento que use el modelo LLM de Gemini debe centralizarse a través de App/core/gemini_client.py. No se permiten llamadas directas al SDK de Google desde los endpoints.

### 🔒 Seguridad

- **Datos Sensibles**: Nunca subas el archivo .env al repositorio. Asegúrate de añadir cualquier variable nueva al archivo .env.example con valores ficticios.
- **Tokens**: Toda ruta protegida debe validar el token Bearer utilizando los métodos definidos en App/core/security.py.
