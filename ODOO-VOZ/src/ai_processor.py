
import json
import logging
import asyncio
from google import genai
from google.genai import types
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple
from src.config import GEMINI_API_KEY, MODEL_NAME, TTS_MODEL, VOICE_NAME, COMMON_MODELS
from src.audio_utils import convert_to_wav

logger = logging.getLogger("SuperBot2.AI")

# Helper para conversión de fechas
def local_to_utc(date_str: str) -> str:
    """Convierte un string de fecha local (YYYY-MM-DD HH:MM:SS) a UTC."""
    try:
        local_dt = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
        aware_dt = local_dt.astimezone() 
        utc_dt = aware_dt.astimezone(timezone.utc)
        return utc_dt.strftime('%Y-%m-%d %H:%M:%S')
    except Exception as e:
        logger.error(f"Date Conversion Error: {e}")
        return date_str

class AIProcessor:
    def __init__(self, odoo_connector):
        self.odoo = odoo_connector
        if not GEMINI_API_KEY:
            logger.error("❌ GOOGLE_GEMINI_API_KEY missing")

    async def transcribe(self, audio_path: str) -> str:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            with open(audio_path, "rb") as f:
                audio_data = f.read()

            response = await client.aio.models.generate_content(
                model=MODEL_NAME,
                contents=[
                    types.Content(
                        parts=[
                            types.Part.from_bytes(data=audio_data, mime_type="audio/ogg")
                        ]
                    ),
                    "Transcribe este audio exactamente como se habla."
                ]
            )
            return response.text.strip() if response.text else ""
        except Exception as e:
            logger.error(f"Transcription Error: {e}")
            return ""

    async def generate_audio(self, text: str) -> bytes:
        """Generates audio from text using Gemini TTS."""
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            safe_text = text[:4000]

            response = await client.aio.models.generate_content(
                model="gemini-2.5-flash-preview-tts",
                contents=safe_text,
                config=types.GenerateContentConfig(
                    response_modalities=["audio"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=VOICE_NAME
                            )
                        )
                    )
                )
            )

            audio_bytes = b""
            mime_type = "audio/pcm"

            if (response.candidates and 
                response.candidates[0].content and 
                response.candidates[0].content.parts):
                part = response.candidates[0].content.parts[0]
                if part.inline_data:
                    audio_bytes = part.inline_data.data
                    mime_type = part.inline_data.mime_type
                    logger.info(f"✅ Audio Generado: {len(audio_bytes)} bytes (Mime: {mime_type})")

            if audio_bytes:
                return convert_to_wav(audio_bytes, mime_type)

            logger.warning("❌ No se recibió inline_data del modelo TTS.")
            return None

        except Exception as e:
            logger.error(f"TTS Error: {e}")
            return None

    async def understand_intent(self, text: str, last_context: Dict = None) -> Dict:
        """
        Determina la acción y el modelo Odoo objetivo usando el mapa COMMON_MODELS.
        Soporta 'execute' para llamadas a métodos (botones).
        """
        model_hints = json.dumps(COMMON_MODELS, indent=2)
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        context_hint = ""
        if last_context:
            context_hint = f"\n[SESSION CONTEXT] Last Record: {json.dumps(last_context)}"
            context_hint += "\nCRITICAL: If the user says 'it', 'this', 'that', 'the one I just made', or similar: "
            context_hint += f"\n1. Set 'model' to '{last_context.get('model')}'."
            context_hint += f"\n2. Set 'search_term' to '{last_context.get('name')}'."

        prompt = f"""
        Current System Time: {current_time}
        {context_hint}
        Analyze the user request: "{text}"
        
        Task:
        1. Identify Action: 'create', 'update', 'search', 'analyze', 'execute'
        2. Identify Target Model. Use this mapping as a guide for common terms:
        {model_hints}
        3. If Action is 'execute' (for buttons like Confirm, Validate, Won, Lost):
           - Identify the Odoo technical method name.
           - CRM Rules: 'Ganar/Won' -> 'action_set_won', 'Perder/Lost' -> 'action_set_lost', 'Convert/Opportunity' -> 'convert_opportunity'.
           - Sales Rules: 'Confirm/Confirmar' -> 'action_confirm', 'Cancel/Cancelar' -> 'action_cancel'.
           - Inventory Rules: 'Validate/Validar' -> 'button_validate'.
           - Account/Invoice: 'Post/Publicar' -> 'action_post'.
           - Manufacturing: 'Mark Done/Hecho' -> 'button_mark_done'.
           - Generic: Try to infer standard Odoo method names (e.g. action_..., button_...).
           - Extract 'search_term': The name/reference of the record to act upon (e.g. "S001", "Google").
        
        If the user mentions a term not in the list, try to infer the technical name (e.g. "Lead" -> "crm.lead").
        
        Return JSON: {{ "action": "...", "model": "...", "method": "..." (if execute), "search_term": "..." }}
        """
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            res = await client.aio.models.generate_content(model=MODEL_NAME, contents=prompt)
            clean_json = res.text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_json)
        except Exception as e:
            logger.error(f"Intent Error: {e}")
            if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
                return {"action": "error", "error": "quota_exceeded"}
            return {"action": "unknown", "model": "unknown"}

    async def extract_structured_data(self, text: str, model_name: str, action: str) -> Dict:
        """
        Extrae datos basados en el esquema dinámico del modelo.
        """
        schema = await self.odoo.get_model_fields(model_name)

        # Build a rich schema hint for the AI
        rich_schema = {}
        for k, v in schema.items():
            if k in ['create_date', 'write_date', '__last_update', 'create_uid', 'write_uid', 'id']:
                continue
            if k.startswith('message_') or k.startswith('activity_'):
                continue

            field_desc = f"{v['type']} - {v['string']}"

            if v['type'] == 'selection' and 'selection' in v:
                options = {item[0]: item[1] for item in v['selection']}
                field_desc += f" | Options: {json.dumps(options)}"

            if v['type'] == 'many2one' and 'relation' in v:
                field_desc += f" | Related to: {v['relation']}"

            rich_schema[k] = field_desc

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        prompt = f"""
        Current System Time: {current_time}
        Extract data for Odoo model '{model_name}' (Action: {action}).
        Input Text: "{text}"
        
        Schema (Field Name: Type - Label | Details):
        {json.dumps(rich_schema, indent=2)[:3500]} 
        
        Rules:
        1. Return JSON compatible with Odoo.
        2. **Selection Fields**: Return the KEY (not the label). If uncertain, return the Label and I will try to map it.
        3. **Many2one**: Return the NAME (string) of the related record to search for.
           - If the model has a contact/partner field (usually `partner_id`), ALWAYS extract the person/company name there.
           - Terms like "para [Nombre]", "del cliente [Nombre]", "con [Nombre]" indicate a partner.
        4. **Many2many/One2many**: Return a LIST of strings (names) or objects.
        5. If action is 'search', return a JSON with a 'domain' key containing a list of Odoo domain tuples:
           {{"domain": [["field", "operator", "value"], ...]}}
           IMPORTANT: Each domain item must be a list of 3 elements [field, operator, value], NOT a dict.
        6. If updating, include 'search_term' (name of record to find) and 'values' (dict of updates).
        7. **General Rules**:
            - Revenue/Money: Use `planned_revenue` for CRM, `amount_total` for Sales/Invoices if applicable.
            - If the user says "for [Client]" or "para [Cliente]", and the model has a `partner_id` field, ALWAYS extract [Client] as `partner_id`.
            - Do not just put the client name in the Name/Title, you MUST set `partner_id` as well.
        """
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            res = await client.aio.models.generate_content(model=MODEL_NAME, contents=prompt)
            clean_json = res.text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_json)
        except Exception as e:
            logger.error(f"Extraction Error: {e}")
            if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
                return {"error": "quota_exceeded"}
            return {}

    async def generate_analytics_query(self, text: str, model_name: str) -> Dict:
        """
        Genera una consulta de agregación para Odoo (read_group o search_read) basada en lenguaje natural.
        """
        schema = await self.odoo.get_model_fields(model_name)
        excluded_fields = ['product_variant_count', 'message_follower_ids', 'activity_ids', 'message_ids']
        simple_schema = {
            k: f"{v['string']} ({v['type']})"
            for k, v in schema.items()
            if v['type'] in ['integer', 'float', 'monetary', 'many2one', 'selection', 'date', 'datetime', 'char']
            and k not in excluded_fields
        }

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        prompt = f"""
        Current System Time: {current_time}
        Role: Data Analyst.
        Task: Convert natural language request into an Odoo 'read_group' or 'search_read' query configuration.
        Model: {model_name}
        Request: "{text}"
        
        Available Fields:
        {json.dumps(simple_schema, indent=2)[:3000]}
        
        Rules:
        1. If the user asks for "totals", "counts", "average", "group by", use 'read_group'.
        2. If the user asks for a "list" or "ranking" of specific records, use 'search_read'.
        3. RETURN JSON ONLY.
        
        Output Format for 'read_group':
        {{
            "method": "read_group",
            "domain": [["field", "operator", "value"]],
            "fields": ["field_to_measure"],
            "groupby": ["field_to_group_by"],
            "limit": 10
        }}
        
        Output Format for 'search_read':
        {{
            "method": "search_read",
            "domain": [["field", "operator", "value"]],
            "fields": ["field1", "field2"],
            "order": "field desc/asc",
            "limit": 10
        }}
        """
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            res = await client.aio.models.generate_content(model=MODEL_NAME, contents=prompt)
            clean_json = res.text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_json)
        except Exception as e:
            logger.error(f"Analytics Query Error: {e}")
            return {}

    async def summarize_analytics_results(self, query_text: str, data: List[Dict], model_name: str) -> str:
        """
        Genera un resumen narrativo de los datos obtenidos.
        """
        prompt = f"""
        Role: Business Analyst.
        Task: Summarize the data results for the user request.
        User Request: "{query_text}"
        Context: Data from Odoo model '{model_name}'.
        
        Data Results:
        {json.dumps(data, indent=2, default=str)}
        
        Instructions:
        1. **BE CONCISE**: Limit response to 3-4 sentences. Direct answer ONLY.
        2. Group raw numbers. Don't read long lists.
        3. **FORMATTING**:
            - Use Telegram Markdown.
            - Use single asterisks for bold: *Example* (NOT **Example**).
            - Use emojis (💰, 📈).
        """
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            res = await client.aio.models.generate_content(model=MODEL_NAME, contents=prompt)
            return res.text.strip()
        except Exception as e:
            logger.error(f"Analytics Summary Error: {e}")
            return "No pude generar el resumen de los datos."

    async def process_odoo_values(self, model_name: str, data: Dict, logs: List[str]) -> Tuple[Dict, List[str]]:
        """
        Post-procesa los datos extraídos por la IA:
        - Resuelve IDs Many2one
        - Convierte fechas a UTC
        - Maneja Many2many/One2many
        """
        schema = await self.odoo.get_model_fields(model_name)
        final_data = {}

        for field_name, value in data.items():
            if field_name not in schema:
                continue
            field_info = schema[field_name]
            f_type = field_info['type']
            relation = field_info.get('relation')

            if f_type == 'datetime' and isinstance(value, str):
                value = local_to_utc(value)
            elif f_type == 'many2one' and isinstance(value, str):
                rec_id = await self.odoo.search_id(relation, value)
                if rec_id:
                    final_data[field_name] = rec_id
                    logs.append(f"✅ {relation}: {value} -> ID {rec_id}")
                else:
                    logs.append(f"⚠️ {relation}: '{value}' no encontrado.")
                continue
            elif f_type in ['many2many', 'one2many'] and isinstance(value, list):
                commands = []
                for item in value:
                    if isinstance(item, str):
                        rid = await self.odoo.search_id(relation, item)
                        if rid:
                            commands.append((4, rid))
                    elif isinstance(item, dict):
                        sub_data, _ = await self.process_odoo_values(relation, item, logs)
                        if sub_data:
                            commands.append((0, 0, sub_data))
                if commands:
                    final_data[field_name] = commands
                continue

            final_data[field_name] = value

        return final_data, logs
