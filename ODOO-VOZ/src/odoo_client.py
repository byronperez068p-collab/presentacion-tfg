
import xmlrpc.client
import logging
import re
import asyncio
from typing import Dict, Any, List

# Configuración del logger
logger = logging.getLogger("SuperBot2.Odoo")

class OdooConnector:
    def __init__(self, url, db, user, password):
        self.url = url
        self.db = db
        self.user = user
        self.password = password
        self.common = xmlrpc.client.ServerProxy(f'{self.url}/xmlrpc/2/common', allow_none=True)
        self.models = xmlrpc.client.ServerProxy(f'{self.url}/xmlrpc/2/object', allow_none=True)
        self.uid = None
        self.model_metadata_cache = {}

    async def connect(self):
        """Verificación inicial de conexión."""
        try:
            self.uid = await asyncio.to_thread(self.common.authenticate, self.db, self.user, self.password, {})
            if self.uid:
                logger.info(f"✅ Conectado a Odoo (UID: {self.uid})")
                return True
            else:
                logger.error("❌ Falló la autenticación en Odoo")
                return False
        except Exception as e:
            logger.error(f"❌ Error de conexión Odoo: {e}")
            return False

    async def ensure_connection(self):
        if not self.uid:
            if not await self.connect():
                raise ConnectionError("No se pudo conectar a Odoo.")

    async def get_model_fields(self, model_name: str) -> Dict:
        """
        Recupera información detallada de campos, incluyendo opciones de selección y modelos relacionados.
        """
        await self.ensure_connection()
        if model_name in self.model_metadata_cache:
            return self.model_metadata_cache[model_name]
        
        try:
            # Obtener campos con más atributos para mejor contexto de IA
            fields_info = await asyncio.to_thread(
                self.models.execute_kw,
                self.db, self.uid, self.password, model_name, 'fields_get', 
                [], {'attributes': ['string', 'type', 'relation', 'selection', 'required', 'help']}
            )
            self.model_metadata_cache[model_name] = fields_info
            return fields_info
        except Exception as e:
            logger.error(f"❌ Error getting schema for {model_name}: {e}")
            return {}

    def _clean_term(self, term: str) -> str:
        """Limpia términos de búsqueda de palabras de relleno y sufijos comunes."""
        if not term: return ""
        t = term.strip()
        
        # 1. Eliminar palabras de relleno al inicio (Case insensitive)
        filler_words = r"^(el|la|los|las|un|una|de|del|para|cliente|empresa|contacto|con)\s+"
        t = re.sub(filler_words, "", t, flags=re.IGNORECASE)
        
        # 2. Eliminar sufijos legales comunes al final
        legal_suffixes = r"\s+(s\.?l\.?|s\.?a\.?|s\.?l\.?u\.?|s\.?l\.?n\.?e\.?|s\.?c\.?p\.?)$"
        t = re.sub(legal_suffixes, "", t, flags=re.IGNORECASE)
        
        return t.strip()

    async def search_id(self, model: str, term: str) -> int:
        await self.ensure_connection()
        if not term or not isinstance(term, str): return False
        
        clean_term = self._clean_term(term)
        logger.info(f"🔍 Buscando '{term}' -> Limpio: '{clean_term}' en modelo '{model}'")

        async def _do_search(search_val):
            try:
                # 1. Coincidencia Exacta
                ids = await asyncio.to_thread(
                    self.models.execute_kw,
                    self.db, self.uid, self.password, model, 'search', [[('name', '=', search_val)]], {'limit': 1}
                )
                if ids: return ids[0]

                # 2. Insensible a mayúsculas / Coincidencia Parcial
                domain = ['|', ('name', 'ilike', search_val), ('display_name', 'ilike', search_val)]
                if model == 'res.partner':
                    domain = ['|', '|', '|', ('name', 'ilike', search_val), ('display_name', 'ilike', search_val), 
                             ('email', 'ilike', search_val), ('phone', 'ilike', search_val)]

                ids = await asyncio.to_thread(
                    self.models.execute_kw,
                    self.db, self.uid, self.password, model, 'search', [domain], {'limit': 1}
                )
                return ids[0] if ids else False
            except Exception as e:
                logger.error(f"Search error for {search_val}: {e}")
                return False

        # Intento 1: Término original
        res = await _do_search(term)
        if res: return res

        # Intento 2: Término limpio
        if clean_term != term:
            res = await _do_search(clean_term)
            if res: return res

        # Intento 3: Si tiene varias palabras, probar con la primera (si es larga) o las dos primeras
        words = clean_term.split()
        if len(words) > 1:
            first_word = words[0]
            if len(first_word) > 3:
                res = await _do_search(first_word)
                if res: return res
            
            two_words = " ".join(words[:2])
            res = await _do_search(two_words)
            if res: return res

        return False

    async def execute(self, model: str, method: str, *args, **kwargs):
        await self.ensure_connection()
        try:
            return await asyncio.to_thread(
                self.models.execute_kw,
                self.db, self.uid, self.password, model, method, list(args), kwargs
            )
        except Exception as e:
            logger.error(f"Odoo Execute Error ({model}.{method}): {e}")
            raise
