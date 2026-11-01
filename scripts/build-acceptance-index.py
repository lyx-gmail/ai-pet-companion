"""Index all 36 spec cases without promoting narrow/old evidence to full passes."""
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
# evidence, what it proves, what is still missing
EVIDENCE={
 'UI01':('device-visual-smoke','旧版用户确认全屏眼睛','当前固件收音/思考/播放全部页面的实物录像'),
 'UI02':('firmware-overlay-check','固定源码补丁及幂等检查','网络通知期间当前固件的可见布局'),
 'KEY01':('device-care-voice-check','旧版工具喂食成功','真实按键触点、一次性触发与反馈p95'),
 'KEY02':('device-sleep-smoke','用户确认旧版长按入睡','长按释放不补短按的当前硬件验收'),
 'KEY03':('device-settings-smoke','用户曾确认中键设置；映射已在固件固定','当前外壳位置与GPIO映射图及实物标注'),
 'KEY04':('device-audio-cancel-check','旧版静音Opus非空队列清零','当前固件实体中键取消和可听尾音'),
 'CARE01':('device-care-voice-check','当前实际模型工具喂食89→100，封顶且持久化，USB读回一致','标准初态70到85及单次事件号'),
 'CARE02':('care-bridge-check','桥接边界软件检查','当前固件满饱/冷却均无奖励与正确答复'),
 'CARE03':('device-clock-check','当前固件抚摸81到89且写入时间线','从70到78的标准初态及可见开心反馈'),
 'CARE04':('device-wifi-recovery-check','无线断开时心情100抚摸不增长、不进入冷却；睡眠与唤醒仍可存盘','满心情时的可见反馈；各关系字段的完整防刷边界'),
 'SLEEP01':('device-sleep-smoke','旧版用户确认闭眼变暗','当前固件5分钟睡眠数值与无主动发声'),
 'SLEEP02':('device-sleep-smoke','旧版中键唤醒只唤醒','标准用例指定KF键唤醒、不喂食及再次照顾'),
 'SET01':('device-settings-smoke','旧版用户确认长按进入/退出','当前固件编辑回滚和30秒自动退出'),
 'SET02':('firmware-build','当前固件编译且有持久化字段','静音设置、重启、恢复输出的实机闭环'),
 'SAVE01':('device-clock-check','当前固件软件重启保留已提交喂食','真实拔电重启、设置与Wi-Fi保留'),
 'SAVE02':('offline-time-core-check','格式拒绝/迁移编译断言及无时钟重启','实际损坏存档故障注入且原数据保留'),
 'NET01':('device-clock-check','电脑夹具无时间时本地照顾可用','真实Wi-Fi断开下所有照顾与保存'),
 'NET02':('device-wifi-recovery-check','实际软件停止无线20秒时0.437秒返回idle；离线睡眠/唤醒存盘，恢复后语音重连通过','可见/可听故障提示；真实AP消失与其他半断连故障期限'),
 'AI01':('device-care-voice-check','当前真实模型调用设备状态工具并收到真实饱食数值','喂食后特定问句及原话一致性'),
 'AI02':('care-bridge-check','工具拒绝规则的软件检查','当前真实模型遇冷却时的原话与数值'),
 'AI03':('care-bridge-check','桥接重放检查','当前固件同轮重复请求仅改变一次'),
 'AI04':('device-care-voice-check','当前协议文字触发真实模型在思考阶段成功调用喂食','声学语音意图与可见动画'),
 'AI05':('firmware-build','编译含持久化睡眠意图与兜底','当前固件提交后TTS失败仍5秒入睡'),
 'MEM01':('device-memory-flow-check','旧版真实模型+USB确认/取消/超时','当前固件含重启未确认草稿不保存'),
 'MEM02':('live-memory-result','虚构资料进程重启后真实模型召回','当前设备声学输入、新会话及原话'),
 'MEM03':('device-memory-ui-check','旧版隔离RAM库单项/全部删除','当前固件更正/删除后新对话不复活'),
 'MEM04':('device-memory-flow-check','旧版确认流程及取消/超时','静音可读确认和第二草稿BUSY实机验收'),
 'MEM05':('device-memory-ui-check','旧版丢回执重试、重进与断网失效','当前固件新增和删除的完整故障回归'),
 'MEM06':('memory-lifecycle-demo','真实SQLite虚拟0/7/30天降权、重提、稳定资料、删除','不支持声称人类遗忘模型或真实运行30天'),
 'REL01':('offline-time-core-check','固定状态/时间线编译断言','单独保存标准24小时窗口的可审阅数值证据'),
 'REL02':('device-chat-rejection-check','当前固件可计分前置成立时，诊断文字对话未增加互动计分','标准3次间隔互动窗口及防刷分完整证据'),
 'TIME01':('device-clock-check','当前无时间重启保留喂食冷却46秒','独立标准冷却重启用例与更多边界'),
 'TIME02':('device-clock-check','当前延迟校时单次结算并保留照顾；上限有编译断言','真实长离线间隔和24小时/7天硬件边界'),
 'PERF01':(None,'无完整记录','20轮真实对话、100次切换、堆趋势及可听断续'),
 'PERF02':(None,'无完整记录','动画开/关各20轮，同网络首响p50/p95与听感'),
 'SOAK01':('device-runtime-observation','当前固件7200秒/721次健康采样，无异常重启且存档可用','真实断网恢复、状态/设置交互及最终视听'),
}


def main():
    spec=(ROOT/'docs/AI宠物_详细计划书.md').read_text(encoding='utf-8')
    ids=re.findall(r'^\| ((?:UI|KEY|CARE|SLEEP|SET|SAVE|NET|AI|MEM|REL|TIME|PERF|SOAK)\d{2}) \|',spec,re.M)
    if len(ids)!=36 or set(ids)!=set(EVIDENCE):raise ValueError('SPEC_COVERAGE_MISMATCH')
    build=json.loads((ROOT/'evaluation/firmware-build.json').read_text(encoding='utf-8'))
    current=build['app_sha256'];rows=[]
    for case in ids:
        name,proves,gap=EVIDENCE[case];data={};relative=None
        if name:
            relative=f'evaluation/{name}.json'
            data=json.loads((ROOT/relative).read_text(encoding='utf-8'))
        sha=data.get('app_sha256')
        if sha and sha!=current:
            proves=proves.replace('当前','该记录中的')
        status='verified_memory_layer' if case=='MEM06' and data.get('ok') else ('partial' if name else 'not_verified')
        rows.append(dict(id=case,status=status,evidence=relative,evidence_ok=data.get('ok'),
            image_scope='current' if sha==current else ('older_image' if sha else 'not_image_bound'),
            proves=proves,remaining=gap))
    report=dict(spec_cases=36,current_app_sha256=current,full_product_acceptance=False,cases=rows)
    (ROOT/'evaluation/acceptance-index.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# 功能验收证据索引','',f'当前固件：`{current}`。','',
        '逐项对应计划书36条用例。关联文件的ok或编译通过不等于整条产品验收通过；旧固件证据不会自动继承到当前固件。MEM06仅在记忆存储层完成，其余仍为部分证据或未验证。','',
        '| 用例 | 状态/镜像范围 | 已有证据 | 剩余验收 |','|---|---|---|---|']
    for row in rows:
        link=f"[{row['proves']}](../{row['evidence']})" if row['evidence'] else row['proves']
        lines.append(f"| {row['id']} | {row['status']} / {row['image_scope']} | {link} | {row['remaining']} |")
    lines+=['','更新索引：`python scripts/build-acceptance-index.py`。此命令检查36条覆盖与证据文件可读性，不重新执行这些用例，也不调用模型。','']
    (ROOT/'docs/功能验收证据索引.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'ok':True,'indexed':len(rows),'fullProductAcceptance':False}))


if __name__=='__main__':main()
