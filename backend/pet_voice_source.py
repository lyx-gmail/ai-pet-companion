"""Adapter-owned ASR provenance; never inferred from text or model output."""
from contextvars import ContextVar
from functools import wraps

_source=ContextVar('pet_voice_source',default=None)

def transcript_metadata(conn):
    source=_source.get()
    if source is None or source[0] is not conn:
        return {'pet_audio':False,'pet_turn':0}
    return {'pet_audio':source[2], 'pet_turn':source[1]}

def voice_source(function):
    @wraps(function)
    async def wrapped(conn,text,*,pet_audio=False):
        turn=getattr(conn,'_pet_input_turn',0)+1
        # Firmware uses positive signed 32-bit request identities, per connection.
        if turn>0x7fffffff: raise ValueError('PET_INPUT_TURN_EXHAUSTED')
        conn._pet_input_turn=turn
        token=_source.set((conn,turn,pet_audio is True))
        try: return await function(conn,text)
        finally: _source.reset(token)
    return wrapped
