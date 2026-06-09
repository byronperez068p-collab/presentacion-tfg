
import os
import json
import logging
import tempfile
import urllib.request
# import html  <-- No longer needed for Markdown
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode, ChatAction

from src.config import ADMIN_ID, ODOO_URL, TELEGRAM_TOKEN
from src.bot_state import BotState

logger = logging.getLogger("SuperBot2.Handlers")

# Inicializar Estado
bot_state = BotState()

# --- UTILS ---
def escape_markdown_v2(text: str) -> str:
    """Escapa texto para Telegram Markdown (Legacy)."""
    if not text:
        return ""
    text = str(text)
    # En Markdown Legacy NO escapamos casi nada para mantenerlo limpio
    # Solo escapamos el asterisco si es necesario, pero para logs y texto normal
    # es mejor dejarlo pasar si no queremos formato.
    return text.replace("*", "\\*").replace("_", "\\_").replace("`", "\\`")

def escape_code_block(text: str) -> str:
    """Escapa texto para Telegram MarkdownV2 dentro de bloques de código."""
    if not text:
        return ""
    return str(text).replace("\\", "\\\\").replace("`", "\\`")

def truncate_msg(text: str, max_length: int = 4000) -> str:
    """Trunca el mensaje para evitar límites de Telegram."""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "... (truncado)"

# --- REPLY HELPERS ---
async def reply_with_voice_and_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, voice_text: str = None, format_args: dict = None, parse_mode=None):
    chat_id = update.effective_chat.id
    if not parse_mode: parse_mode = ParseMode.MARKDOWN
    if format_args is None: format_args = {}
    if reply_markup: format_args['reply_markup'] = reply_markup 
    
    ai = context.bot_data.get('ai')

    # 1. Enviar acción de estado específica (DESHABILITADO POR COSTES)
    # try:
    #     await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.RECORD_VOICE)
    # except Exception: pass # Ignorar timeouts en acciones visuales

    # 2. Generar y Enviar Audio (DESHABILITADO POR COSTES)
    # try:
    #     tts_content = voice_text if voice_text else text
    #     if ai:
    #         logger.info(f"🔊 Intentando enviar voz. Texto TTS: '{tts_content[:50]}...'")
    #         audio_result = await ai.generate_audio(tts_content)
    #         
    #         # Compatibilidad: verificar si es tupla o solo bytes (por si acaso)
    #         audio_wav = None
    #         ext = "voice.wav"
    #         
    #         if isinstance(audio_result, tuple):
    #             audio_wav, ext_str = audio_result
    #             if ext_str: ext = f"voice.{ext_str}"
    #         else:
    #             audio_wav = audio_result
    # 
    #         if audio_wav:
    #             logger.info(f"📤 Enviando nota de voz ({len(audio_wav)} bytes) como {ext}...")
    #             await context.bot.send_voice(
    #                 chat_id=chat_id, 
    #                 voice=audio_wav,
    #                 filename=ext, # Telegram transcodificará WAV -> OGG si el upload no falla
    #                 caption="🔊 Asistente de Voz"
    #             )
    # except Exception as e:
    #     logger.error(f"Error enviando voz: {e}")

    # 3. Enviar Mensaje de Texto (Siempre habilitar previsualización de enlaces ahora)
    # desactivar disable_web_page_preview por defecto a False a menos que se especifique
    if 'disable_web_page_preview' not in format_args:
        format_args['disable_web_page_preview'] = False

    if len(text) > 4000:
        for x in range(0, len(text), 4000):
            try:
                await context.bot.send_message(
                    chat_id=chat_id, 
                    text=text[x:x+4000], 
                    parse_mode=parse_mode,
                    **format_args
                )
            except Exception as e:
                # Fallback to plain text if parse error occurs
                await context.bot.send_message(
                    chat_id=chat_id, 
                    text=text[x:x+4000], 
                    parse_mode=None,
                    **format_args
                )
    else:
        try:
            await context.bot.send_message(
                chat_id=chat_id, 
                text=text, 
                parse_mode=parse_mode,
                **format_args
            )
        except Exception as e:
            await context.bot.send_message(
                chat_id=chat_id, 
                text=text, 
                parse_mode=None,
                **format_args
            )

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with open("last_chat_id.txt", "w") as f:
        f.write(str(update.effective_chat.id))
    # Usar Markdown estándar para evitar barras invertidas
    await update.message.reply_text("🤖 *Super Bot 2.0*\n\nControl total de Odoo por voz.\nPrueba: _'Crear una oportunidad para Microsoft...'_", parse_mode=ParseMode.MARKDOWN)

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = None, voice_file = None):
    user = update.effective_user
    ai = context.bot_data.get('ai')
    odoo = context.bot_data.get('odoo')
    
    # --- MODO CHIVATO (Logging en Consola) ---
    print("\n" + "="*30)
    print(f"🕵️  ACTIVIDAD DETECTADA")
    print(f"👤  Nombre:   {user.first_name}")
    print(f"📧  Alias:    @{user.username}")
    print(f"🔑  ID:       {user.id}")
    print("="*30 + "\n")

    if not ai or not odoo:
        await update.message.reply_text("⚠️ Error: Servicios no inicializados.")
        return

    # Modo Espía (Notificar Admin)
    if ADMIN_ID and user.id != int(ADMIN_ID):
        try:
            spy_msg = f"🕵️ *Actividad Detectada*\n👤 {escape_markdown_v2(user.first_name)} (@{escape_markdown_v2(str(user.username))})\n🆔 `{user.id}`\n"
            if text:
                spy_msg += f"💬 *Dijo:* {escape_markdown_v2(text)}"
            elif voice_file:
                spy_msg += f"🎤 *Envió Audio*"
            await context.bot.send_message(chat_id=ADMIN_ID, text=spy_msg, parse_mode=ParseMode.MARKDOWN, disable_notification=True)
        except Exception as e:
            logger.error(f"Spy Error: {e}")

    if voice_file:
        await update.message.reply_text("🎧 Escuchando...", disable_notification=True) 
        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
                temp_path = f.name
                file_obj = await voice_file.get_file()
                await file_obj.download_to_drive(custom_path=temp_path)
            
            text = await ai.transcribe(temp_path)
            
            if os.path.exists(temp_path):
                os.remove(temp_path)
            
            if not text:
                await update.message.reply_text("⚠️ No pude escuchar nada.")
                return
            
            safe_text = truncate_msg(text)
            await update.message.reply_text(f"👤 *Transcripción:*\n_{escape_markdown_v2(safe_text)}_", parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"Voice Error: {e}")
            await update.message.reply_text("💥 Error procesando audio.")
            return

    if not text:
        return

    # 1. Intención (Pasar contexto para referencias relativas)
    last_context = bot_state.get_last_record(user.id)
    intent = await ai.understand_intent(text, last_context=last_context)
    action = intent.get('action')
    model = intent.get('model')
    
    if intent.get('error') == 'quota_exceeded':
        await reply_with_voice_and_text(update, context, "⏳ He agotado mi cuota de consultas gratuita (20/min). Por favor espera un momento.")
        return

    if action == 'unknown' or not model or model == 'unknown':
        await reply_with_voice_and_text(update, context, "🤔 No entendí qué quieres hacer o sobre qué modelo actuar.")
        return

    # 2. Extracción (Fix Batching: No trunques la lista)
    raw_data = await ai.extract_structured_data(text, model, action)
    if isinstance(raw_data, dict) and raw_data.get('error') == 'quota_exceeded':
        await reply_with_voice_and_text(update, context, "⏳ He agotado mi cuota de consultas gratuita. Inténtalo de nuevo en unos segundos.")
        return

    # Si es lista y NO es búsqueda, mantién la lista para procesamiento por lotes
    is_batch = isinstance(raw_data, list) and action != 'search'
    
    # Normalización para búsqueda
    if isinstance(raw_data, list) and action == 'search':
         raw_data = {'domain': raw_data}
         is_batch = False
    
    # 3. Procesamiento
    logs = []
    final_data = [] # Ahora siempre lista
    
    # 3.1. ACTION: ANALYZE
    if action == 'analyze':
        # ... (Mantener lógica de analyze)
        await reply_with_voice_and_text(update, context, "📊 Analizando datos en Odoo...")
        query_config = await ai.generate_analytics_query(text, model)
        
        if not query_config or 'method' not in query_config:
            await reply_with_voice_and_text(update, context, "⚠️ No pude formular una consulta válida para tu análisis.")
            return

        method = query_config['method']
        domain = query_config.get('domain', [])
        
        try:
            if method == 'read_group':
                results = await odoo.execute(model, 'read_group', domain, query_config.get('fields'), query_config.get('groupby'), limit=query_config.get('limit', 10))
            elif method == 'search_read':
                results = await odoo.execute(model, 'search_read', domain, query_config.get('fields'), limit=query_config.get('limit', 10), order=query_config.get('order'))
            else:
                results = []
                
            if not results:
                await reply_with_voice_and_text(update, context, "📭 El análisis no arrojó resultados.")
                return

            summary = await ai.summarize_analytics_results(text, results, model)
            
            msg = f"📊 *INFORME GENERADO*\n"
            msg += f"────────────────────\n"
            msg += f"🔎 _{escape_markdown_v2(text)}_\n"
            msg += f"────────────────────\n\n"
            msg += f"{summary}\n"
            
            await reply_with_voice_and_text(update, context, msg, voice_text=summary, parse_mode=ParseMode.MARKDOWN)
            return
        except Exception as e:
            logger.error(f"Analytics Execution Error: {e}")
            await reply_with_voice_and_text(update, context, f"💥 Error: {e}", voice_text="Hubo un error al generar el reporte.")
            return

    # 3.2. ACTION: CREATE/UPDATE/EXECUTE
    if action in ['create', 'update', 'execute']:
        # Normalizar a lista para bucle único
        items_to_process = raw_data if is_batch else [raw_data]
        batch_final_data = []
        
        for item in items_to_process:
            item_data = {}
            if action == 'execute':
                # (Misma lógica execute)
                search_term = intent.get('search_term')
                method = intent.get('method')
                if not search_term:
                     # Fallback simple
                     search_term = text
                
                rec_id = await odoo.search_id(model, search_term)
                if not rec_id:
                    logs.append(f"❌ '{search_term}': No encontrado.")
                    continue
                    
                item_data = {'_execute_method': method, '_execute_id': rec_id, '_execute_display_name': search_term}
                logs.append(f"⚡ Método detectado: {method} para {search_term}")

            elif action == 'update':
                search_term = item.pop('search_term', None)
                values = item.get('values', item)
                item_data, item_logs = await ai.process_odoo_values(model, values, logs)
                logs.extend(item_logs) # Merge logs
                
                if search_term:
                    rec_id = await odoo.search_id(model, search_term)
                    if not rec_id:
                        logs.append(f"❌ '{search_term}': No encontrado.")
                        continue
                    item_data['_update_display_name'] = search_term 
                    item_data['_update_id'] = rec_id
                else:
                    logs.append("⚠️ Falta término de búsqueda para update.")
                    continue

            else: # Create
                item_data, item_logs = await ai.process_odoo_values(model, item, logs)
                logs.extend(item_logs)

            batch_final_data.append(item_data)

        if not batch_final_data:
             await reply_with_voice_and_text(update, context, "❌ No se pudieron preparar datos válidos (revisa logs/IDs).")
             return

        # GUARDAR ESTADO
        bot_state.set_state(user.id, 'WAITING_CONFIRMATION', {
            'action': action, 'model': model, 'data': batch_final_data, 'logs': logs, 'original_text': text, 'is_batch': is_batch
        })
        
        preview_text = f"🚀 *Confirmar Acción" + (" Múltiple" if len(batch_final_data) > 1 else "") + "*\n"
        preview_text += f"────────────────────\n"
        preview_text += f"👤 _{escape_markdown_v2(text)}_\n"
        preview_text += f"────────────────────\n"
        preview_text += f"📌 *Acción:* {escape_markdown_v2(action.upper())}\n"
        
        if action == 'execute':
             # Mostrar resumen del primero o genérico
             method = batch_final_data[0].get('_execute_method')
             preview_text += f"⚡ *Método:* {escape_markdown_v2(method)}\n"
             preview_text += f"📦 *Registros:* {len(batch_final_data)}\n"
        else:
             preview_text += f"📂 *Modelo:* {escape_markdown_v2(model)}\n"
             preview_text += f"📦 *Cantidad:* {len(batch_final_data)}\n"
        
        if logs:
            preview_text += f"\n📋 *Ajustes IA:*\n"
            # Mostrar solo últimos 5 logs para no saturar
            for log in logs[-5:]:
                preview_text += f"{escape_markdown_v2(log)}\n"

        # Preview JSON del primero con encoding correcto
        json_str = json.dumps(batch_final_data[0], indent=2, default=str, ensure_ascii=False)
        if len(json_str) > 500: json_str = json_str[:1000] + "\n... (truncado)"
              
        if action != 'execute':
             preview_text += f"\n📋 *Datos a Enviar:*\n```json\n{escape_code_block(json_str)}\n```"
             if len(batch_final_data) > 1:
                 preview_text += f"\n_... y {len(batch_final_data)-1} más._"
        
        keyboard = [[InlineKeyboardButton("✅ Confirmar", callback_data="confirm"), InlineKeyboardButton("❌ Cancelar", callback_data="cancel")]]
        
        await reply_with_voice_and_text(update, context, preview_text, format_args={"reply_markup": InlineKeyboardMarkup(keyboard)})

    elif action == 'search':
        # ... (Search logic remains same but ensuring raw_data is handled correctly)
        if 'domain' in raw_data:
             domain = raw_data['domain']
        else:
             domain = []
             # If it was a list of dicts, it's not supported for search here usually, assume simple dict
             if isinstance(raw_data, list): raw_data = {} 
             for k, v in raw_data.items():
                 domain.append((k, 'ilike', v))
        
        if domain:
            domain = [tuple(item) if isinstance(item, list) else item for item in domain]
        
        try:
            results = await odoo.execute(model, 'search_read', domain, limit=5)
            if results:
                names_found = []
                msg = f"🔎 *RESULTADOS ENCONTRADOS*\n"
                msg += f"────────────────────\n"
                msg += f"👤 _{escape_markdown_v2(text)}_\n"
                msg += f"────────────────────\n\n"
                
                for r in results:
                    name = r.get('name') or r.get('display_name') or f"ID {r['id']}"
                    names_found.append(name)
                    url = f"{ODOO_URL}/web#id={r['id']}&model={model}&view_type=form"
                    msg += f"📦 *{escape_markdown_v2(name)}*\n"
                    msg += f"🆔 {r['id']}\n"
                    
                    # Mejoras: Mostrar Stock y Precio si están disponibles
                    if 'qty_available' in r:
                         msg += f"📉 *Stock:* {r['qty_available']}\n"
                    if 'quantity' in r:
                         msg += f"📉 *Stock Real:* {r['quantity']}\n"
                    if 'inventory_quantity' in r:
                         msg += f"📝 *Contado:* {r['inventory_quantity']}\n"
                    if 'list_price' in r:
                         msg += f"💰 *Precio: €* {r['list_price']}\n"
                    if 'virtual_available' in r:
                         msg += f"🔮 *Previsto:* {r['virtual_available']}\n"

                    if 'email' in r: msg += f"📧 {escape_markdown_v2(str(r['email']))}\n"
                    if 'phone' in r: msg += f"📞 {escape_markdown_v2(str(r['phone']))}\n"
                    msg += f"🔗 [Ver en Odoo]({url})\n\n"
                
                speakable_summary = f"Encontrado: {names_found[0]}." if len(names_found) == 1 else f"Encontrados {len(results)} registros."
                await reply_with_voice_and_text(update, context, msg, voice_text=speakable_summary, parse_mode=ParseMode.MARKDOWN)
            else:
                await reply_with_voice_and_text(update, context, "📭 No se encontraron resultados.", voice_text="Sin resultados.")
        except Exception as e:
             await reply_with_voice_and_text(update, context, f"❌ Error Búsqueda: {e}")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    state = bot_state.get_state(user_id)
    odoo = context.bot_data.get('odoo')
    
    if not state or state.get('state') != 'WAITING_CONFIRMATION':
        await query.edit_message_text("⚠️ Sesión expirada.")
        return

    data = state['data']
    action = data['action']
    model = data['model']
    batch_payload = data['data'] # Now always a list
    original_text = data.get('original_text', 'Solicitud original desconocida')
    
    if query.data == "confirm":
        await query.edit_message_reply_markup(reply_markup=None)
        await query.edit_message_text(text=f"⏳ Procesando {len(batch_payload)} operaciones...")
        
        success_count = 0
        error_count = 0
        last_success_name = ""
        last_success_id = None
        
        # BUCLE DE EJECUCIÓN POR LOTES
        for payload in batch_payload:
            try:
                if action == 'create':
                    new_id = await odoo.execute(model, 'create', payload)
                    rec_name = f"ID {new_id}"
                    try:
                        recs = await odoo.execute(model, 'read', [new_id], ['display_name', 'name'])
                        if recs:
                             rec_name = recs[0].get('display_name') or recs[0].get('name') or f"ID {new_id}"
                    except: pass
                    last_success_name = rec_name
                    last_success_id = new_id
                    success_count += 1
                    bot_state.set_last_record(user_id, model, new_id, rec_name)
                    
                elif action == 'update':
                    rec_id = payload.pop('_update_id')
                    rec_display_name = payload.pop('_update_display_name', f"ID {rec_id}")
                    await odoo.execute(model, 'write', [rec_id], payload)
                    last_success_name = rec_display_name
                    last_success_id = rec_id
                    success_count += 1
                    bot_state.set_last_record(user_id, model, rec_id, rec_display_name)
                
                elif action == 'execute':
                    rec_id = payload.get('_execute_id')
                    method = payload.get('_execute_method')
                    rec_name = payload.get('_execute_display_name') or f"ID {rec_id}"
                    
                    try:
                        await odoo.execute(model, method, [rec_id])
                    except Exception as e:
                        # HACK: Ignorar error de Marshalling de Odoo si la acción retornó None
                        if "cannot marshal None" in str(e):
                            logger.info(f"Ignored Marshal None Error for {method}")
                        else:
                            raise e 
                            
                    last_success_name = rec_name
                    last_success_id = rec_id
                    success_count += 1
                    bot_state.set_last_record(user_id, model, rec_id, rec_name)
                    
            except Exception as e:
                logger.error(f"Batch Error: {e}")
                error_count += 1
        
        # RESUMEN FINAL
        msg = f"✅ *PROCESO COMPLETADO*\n"
        if error_count > 0:
             msg = f"⚠️ *PROCESO CON ERRORES*\n"
             
        msg += f"────────────────────\n"
        msg += f"👤 _{escape_markdown_v2(original_text)}_\n"
        msg += f"────────────────────\n"
        msg += f"📊 *Resumen:*\n"
        msg += f"✅ Éxitos: {success_count}\n"
        if error_count > 0:
            msg += f"❌ Fallos: {error_count}\n"
            
        if success_count == 1 and last_success_id:
             msg += f"📦 Registro: {escape_markdown_v2(last_success_name)}\n"
             url = f"{ODOO_URL}/web#id={last_success_id}&model={model}&view_type=form"
             msg += f"🔗 [Ver en Odoo]({url})\n"
        
        voice_msg = f"Proceso terminado. {success_count} éxitos."
        if error_count > 0: voice_msg += f" Y {error_count} errores."
        
        await reply_with_voice_and_text(update, context, msg, voice_text=voice_msg, parse_mode=ParseMode.MARKDOWN)

    else:
        await query.edit_message_text("❌ Cancelado.")
    
    bot_state.clear_state(user_id)
async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_input(update, context, voice_file=update.message.voice)

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_input(update, context, text=update.message.text)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Exception while handling an update:", exc_info=context.error)
    if update and isinstance(update, Update) and update.effective_chat:
        try:
            err_msg = escape_markdown_v2(str(context.error)[:1000])
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"⚠️ *Error interno:* `{err_msg}`", parse_mode=ParseMode.MARKDOWN)
        except: pass