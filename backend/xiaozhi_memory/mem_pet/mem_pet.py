"""Install under core/providers/memory/mem_pet in the pinned voice server."""
import asyncio
import json
from core.providers.memory.base import MemoryProviderBase
from .client import PetMemoryClient, MemoryUnavailable
from .confirmation import confirm_memory, wants_memory, parse_device_result


class MemoryProvider(MemoryProviderBase):
    def __init__(self, config, summary_memory=None):
        super().__init__(config)
        self.connection=None
        self.confirming=False
        self.handled={}
        self.last_revision=None
        self.querying=0
        self.watch_task=None
        self.expected_device_id = str(config.get('expected_device_id', '')).lower()
        self.client = PetMemoryClient(config.get('endpoint', 'http://127.0.0.1:8766'),
                                      config.get('token', ''), config.get('timeout', 3))

    def init_memory(self, role_id, llm, **kwargs):
        if not self.expected_device_id or str(role_id).lower() != self.expected_device_id:
            raise ValueError('PET_DEVICE_NOT_BOUND')
        super().init_memory(role_id, llm, **kwargs)
        self.connection=kwargs.get('pet_connection')

    def for_connection(self, connection):
        return self if self.connection is connection else type(self)(self.config)

    def _clear_history(self, query):
        conn=self.connection
        if conn is None: return
        messages=conn.dialogue.dialogue
        latest=next((m for m in reversed(messages) if m.role=='user'),None)
        # Purge old tool/assistant/user claims together, retaining only this turn.
        keep=[m for m in messages if m.role=='system']
        if latest is not None and latest.content==query: keep.append(latest)
        messages[:]=keep
        tts=getattr(conn,'tts',None)
        cache=getattr(tts,'_sentence_text_map',None)
        if isinstance(cache,dict): cache.clear()

    async def query_pet_memory(self, query, sentence):
        self.querying+=1
        try:
            return await self._query_pet_memory(query,sentence)
        finally:
            self.querying-=1
            if self.watch_task is None and self.connection is not None and not self.connection.stop_event.is_set():
                self.watch_task=asyncio.create_task(self._watch_memory())

    async def stop_memory_watch(self):
        task=self.watch_task
        self.watch_task=None
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task,return_exceptions=True)

    async def _watch_memory(self):
        while not self.connection.stop_event.is_set():
            await asyncio.sleep(.5)
            if await self.check_memory_revision():return

    async def check_memory_revision(self):
        conn=self.connection;baseline=self.last_revision
        if conn is None or conn.stop_event.is_set() or self.querying or self.confirming or baseline is None:return False
        try:
            profile=await asyncio.to_thread(self.client.profile)
            revision=profile.get('revision')
            if type(revision) is not int or not 0<=revision<=9007199254740991:
                raise MemoryUnavailable('MEMORY_REVISION_INVALID')
        except (MemoryUnavailable,ValueError,KeyError,TypeError):
            revision=None  # A failed read cannot authorize continued use of old personal data.
        if (conn.stop_event.is_set() or self.querying or self.confirming or
                baseline!=self.last_revision or revision==baseline):return False
        conn.client_abort=True
        conn.sentence_id=None
        conn.stop_event.set()
        conn.clear_queues()
        self._clear_history(None)
        self.last_revision=None
        await conn.websocket.close(code=1000,reason='Memory context changed')
        return True

    async def _query_pet_memory(self, query, sentence):
        conn=self.connection
        def current():
            return (conn is not None and sentence is not None and conn.sentence_id==sentence
                    and not conn.client_abort and not conn.stop_event.is_set())
        outcome=self.handled.get(sentence,'')
        if wants_memory(query) and sentence not in self.handled:
            if self.confirming:
                outcome='已有记忆等待确认，本轮新请求未保存。'
            else:
                self.confirming=True
                try:
                    async def call(name,args):
                        if not current(): raise MemoryUnavailable('STALE_VOICE_TURN')
                        from core.providers.tools.device_mcp.mcp_handler import call_mcp_tool
                        raw=await call_mcp_tool(conn,conn.mcp_client,name,json.dumps(args,ensure_ascii=False),timeout=3)
                        return parse_device_result(raw)
                    outcome=await confirm_memory(query,self.client.request,call,current)
                    if len(self.handled)>=64: self.handled.clear()
                    self.handled[sentence]=outcome
                finally:
                    self.confirming=False
        if not current(): return ''
        context=await self._query_snapshot(query,current)
        return outcome+'\n'+context if current() else ''

    async def _query_snapshot(self, query, current):
        if not self.role_id: return '记忆服务尚未绑定设备。不要猜测用户的称呼或偏好。'
        try:
            snapshot=await asyncio.to_thread(self.client.recall_snapshot,query)
            if not current(): return ''
            revision=snapshot['profile']['revision']
            if revision!=self.last_revision:
                self._clear_history(query)
                self.last_revision=revision
            return snapshot['context']
        except (MemoryUnavailable,ValueError,KeyError,TypeError):
            if not current(): return ''
            self._clear_history(query)
            self.last_revision=None
            return '记忆服务暂时不可用。请明确告知无法读取记忆，不要猜测用户的称呼或偏好。'

    async def query_memory(self, query):
        if not self.role_id:
            return '记忆服务尚未绑定设备。不要猜测用户的称呼或偏好。'
        try:
            return await asyncio.to_thread(self.client.recall, query)
        except (MemoryUnavailable, ValueError):
            return '记忆服务暂时不可用。请明确告知无法读取记忆，不要猜测用户的称呼或偏好。'

    async def save_memory(self, msgs, session_id=None):
        # Closing a connection does not constitute user confirmation to persist facts.
        return None
