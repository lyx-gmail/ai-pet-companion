"""Propose from actual user input; persist only after the matching device decision."""
import asyncio
import json
import re
import time


def wants_memory(text):
    return (isinstance(text,str) and len(text.encode('utf-8'))<=2000
            and bool(re.search(r'记住|记一下|叫我|称呼我|我叫(?!什么|啥|谁)',text))
            and not re.search(r'不要记|不用记|别记',text))


async def confirm_memory(query,request,call,is_current,*,poll_seconds=.5,timeout=24,announce=None):
    draft=None
    committed=False
    commit_attempted=False
    try:
        if not is_current(): return '本轮已结束，记忆未保存。'
        draft=await asyncio.to_thread(request,'remember',{'message':query})
        if draft.get('status')=='NO_PROPOSAL': return ''
        token=draft['id']
        # Do not turn arbitrary experience text into a tiny ambiguous confirmation.
        if (draft.get('status')!='PENDING' or draft.get('field') not in
                ('name','preference0','preference1','preference2','preference3')):
            return '当前实体确认只支持称呼和少量偏好，这条记忆未保存。'
        value=draft['value']
        if not isinstance(value,str) or not value or len(value.encode('utf-8'))>80 or any(ord(c)<32 for c in value):
            return '记忆草稿格式异常，未保存。'
        label=('称呼：' if draft['field']=='name' else '偏好：')+value
        seconds=min(timeout,(draft['expiresAt']-time.time()*1000)/1000-1)
        if seconds<=0 or not is_current(): return '记忆确认已过期，未保存。'
        deadline=asyncio.get_running_loop().time()+seconds
        offered=await call('self_pet_memory_offer',{'id':token,'label':label})
        if not offered.get('ok') or offered.get('id')!=token or offered.get('status')!='pending':
            return '设备无法进入记忆确认，未保存。'
        if announce is not None:
            await announce(f'想记住{label}。按中键保存，按左键取消。')
        while is_current() and asyncio.get_running_loop().time()<deadline:
            decision=await call('self_pet_memory_status',{'id':token})
            if not is_current(): break
            if not decision.get('ok') or decision.get('id')!=token: break
            status=decision.get('status')
            if status=='confirmed':
                if asyncio.get_running_loop().time()>=deadline: break
                commit_attempted=True
                result=await asyncio.to_thread(request,'confirm',{'id':token,'requestId':'device-'+token})
                if result.get('ok') is not True: break
                committed=True
                return '本轮记忆已按键确认并保存；资料只以接下来读取的已确认记忆为准。'
            if status!='pending': break
            await asyncio.sleep(poll_seconds)
        return '没有收到本轮有效的按键确认，记忆未保存。'
    except asyncio.CancelledError:
        raise
    except Exception:
        if commit_attempted: return '已收到按键确认，但保存结果未知；请查询当前已确认资料，不要断言写入结果。'
        return '记忆确认服务暂时不可用，未确认的记忆未保存。'
    finally:
        if isinstance(draft,dict) and draft.get('id') and not committed:
            try: await asyncio.to_thread(request,'cancel',{'id':draft['id']})
            except Exception: pass  # RAM-only draft also expires after 30 seconds.


def parse_device_result(value):
    parsed=json.loads(value) if isinstance(value,str) else value
    if not isinstance(parsed,dict): raise ValueError('MEMORY_DEVICE_RESULT_INVALID')
    return parsed
