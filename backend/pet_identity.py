"""Adapter-owned care IDs; never trust model arguments as transaction identity."""
import asyncio
from contextvars import ContextVar
from functools import wraps

_current_call = ContextVar('pet_call',default=None)
CARE_TOOLS = frozenset(('self.pet.feed','self.pet.pet','self.pet.set_sleep'))


def bind_pet_call(function):
    @wraps(function)
    async def wrapped(self,conn,data):
        token = _current_call.set((conn,data.get('_pet_sentence_id'),data.get('id')))
        try:
            return await function(self,conn,data)
        finally:
            _current_call.reset(token)
    return wrapped


async def care_request_id(conn,client,name,arguments=None):
    if name not in CARE_TOOLS:
        return None
    target = None
    if name=='self.pet.set_sleep':
        if not isinstance(arguments,dict) or type(arguments.get('sleeping')) is not bool:
            raise ValueError('Pet sleep requires a boolean sleeping target')
        target = arguments['sleeping']
    action = (name,target)
    context = _current_call.get()
    if not context or context[0] is not conn:
        raise ValueError('Pet action requires an adapter-bound voice turn')
    _,sentence,call_id = context
    if (not isinstance(sentence,str) or not 1<=len(sentence)<=128 or
        not isinstance(call_id,str) or not 1<=len(call_id)<=128 or
        sentence!=getattr(conn,'sentence_id',None) or getattr(conn,'client_abort',True)):
        raise ValueError('Pet action belongs to an invalid or cancelled voice turn')
    if not hasattr(client,'_pet_identity_lock'):
        client._pet_identity_lock = asyncio.Lock()
        client._pet_identities = {}
        client._pet_calls = {}
    async with client._pet_identity_lock:
        call_key = (sentence,call_id)
        original_name = client._pet_calls.get(call_key)
        if original_name is not None and original_name!=action:
            raise ValueError('Pet call identity cannot change action')
        if original_name is None and len(client._pet_calls)>=512:
            raise ValueError('Pet call capacity reached; reconnect voice')
        key = (sentence,action)
        existing = client._pet_identities.get(key)
        if existing is not None:
            client._pet_calls[call_key] = action
            return existing
        # Refuse new actions at the bound; eviction would let an old retry earn
        # a new identity. Reconnect starts a fresh authenticated channel.
        if len(client._pet_identities)>=256:
            raise ValueError('Pet action identity capacity reached; reconnect voice')
        number = len(client._pet_identities)+1
        client._pet_calls[call_key] = action
        client._pet_identities[key] = number
        return number
