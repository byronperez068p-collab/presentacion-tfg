
import json
import os
import logging
from datetime import datetime

logger = logging.getLogger("SuperBot2.State")

class BotState:
    def __init__(self, filename="bot_state.json"):
        self.filename = filename
        self._user_states = self.load()

    def load(self):
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r') as f:
                    return json.load(f)
            except: return {}
        return {}

    def save(self):
        try:
            with open(self.filename, 'w') as f:
                json.dump(self._user_states, f)
        except Exception as e:
            logger.error(f"State Save Error: {e}")

    def set_state(self, user_id, state, data=None):
        # Convertir user_id a str para compatibilidad JSON
        user_id = str(user_id)
        self._user_states[user_id] = {
            'state': state, 
            'data': data or {}, 
            'timestamp': datetime.now().isoformat()
        }
        self.save()

    def get_state(self, user_id):
        user_id = str(user_id)
        state = self._user_states.get(user_id, {})
        # Opcional: Verificar expiración de timestamp aquí si es necesario
        return state

    def clear_state(self, user_id):
        user_id = str(user_id)
        if user_id in self._user_states:
            # Mantener el 'last_record' incluso al limpiar el estado de confirmación
            last_record = self._user_states[user_id].get('last_record')
            self._user_states[user_id] = {'state': 'IDLE', 'last_record': last_record}
            self.save()

    def set_last_record(self, user_id, model, rec_id, name):
        user_id = str(user_id)
        if user_id not in self._user_states:
             self._user_states[user_id] = {}
        self._user_states[user_id]['last_record'] = {
            'model': model,
            'id': rec_id,
            'name': name,
            'timestamp': datetime.now().isoformat()
        }
        self.save()

    def get_last_record(self, user_id):
        user_id = str(user_id)
        return self._user_states.get(user_id, {}).get('last_record')
