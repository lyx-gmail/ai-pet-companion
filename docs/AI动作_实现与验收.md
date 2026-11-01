# AI照顾动作：实现与验收

2026-10-31。当前完成源码、编译和软件桥接验证，尚未完成实体语音验收。

## 真实执行路径

```mermaid
flowchart LR
  A[明确的用户请求] --> B[模型选择设备工具]
  B --> C[服务端绑定语音轮次与动作编号]
  C --> D[MCP元数据传输]
  D --> E[固件校验当前通道与忙碌状态]
  E --> F[养成reducer执行并提交存档]
  F --> G[实际增量与存档结果]
  G --> H[模型据实简短回应]
```

已注册`self.pet.feed`、`self.pet.pet`与`self.pet.set_sleep`，没有模型可指定的奖励参数。照顾工具与实体键使用同一养成reducer和冷却字段。`self.pet.get_state`仍为只读工具，并返回`sleep_pending`。

照顾工具在当前有效语音通道的Listening阶段允许执行，设置/暂停输入、已取消通道、Speaking或其它状态拒绝。Listening包含等待模型处理的阶段；实际收音/TTS时序尚需实体验证，不能据此宣称所有抢话竞态已解决。

成功动作立即提交独立宠物快照，返回`delta`、当前数值、`revision`、`persisted_revision`和`durable`。提交失败返回`STORAGE_ERROR`并进入存档故障状态；RAM中已变化的值不冒充已持久化。成功照顾请求可在Listening阶段触发短反馈，说话开始仍优先切回语音表情。

## 去重边界

- 服务端按“语音轮次＋动作类型”分配稳定编号；即使模型在同一轮生成多个调用ID，也不会执行第二次同类动作。提供方调用ID不能跨动作改写。
- JSON-RPC传输ID保持每次请求不同，稳定动作编号放在`params._meta.pet_request_id`。模型arguments中的同名字段不能覆盖它。
- 固件调度层注入动作编号及当前通道代次，不将其暴露为模型工具参数。缺失或非法元数据返回`INVALID`。
- 固件保留最近64个编号的结果，更旧编号拒绝，不因缓存淘汰重新执行。重复返回`DUPLICATE`、本次`delta=0`和原结果码。
- 服务端每通道最多256个轮次动作身份、512个提供方调用身份；到上限拒绝新增动作，重连后建立新通道，不淘汰旧身份来腾位置。
- 这是当前通道内去重，不是跨断电事务日志。重启后冷却由已有快照恢复；完整断电/延后校时验收仍未通过。

## 晚安后入睡

`self.pet.set_sleep(sleeping=true)`先将待睡意图提交到V3宠物快照，再返回`OK`、`sleep_pending=true`及实际`sleeping`值。模型只需说一句晚安，不能把等待状态说成已经闭眼。

固件观察本通道经过校验的TTS stop序号，并检查解码/播放队列与正在处理的音频；结束后保留至少200ms尾音缓冲再入睡。待睡期间每100ms检查，正常状态仍每秒结算。没有有效stop、取消/换通道、TTS失败或音频持续未完成时，5秒截止条件仍会触发睡眠。重复指令不延长截止时间。计时策略有编译期断言，真实播放尾音和调度延迟尚未测量，不能声称已实现毫秒级期限保证。

取消语音不撤回已保存的睡眠意图；明确`set_sleep(false)`可撤回待睡。实体键唤醒已睡着的宠物也会清理残留待睡状态。设置页保持前台和语音输入暂停，后台完成入睡后退出设置才恢复闭眼/低亮度。待睡期间拒绝新的喂食、抚摸。

V3快照92字节，保留V1（84字节）、V2（88字节）严格迁移；未知未来版本或非法布尔值拒绝读取，不覆盖旧数据。重启读到待睡意图时完成入睡，之后通过正常存档流程清除意图。真实断电及恢复仍待实机测试。

服务端按“轮次＋睡眠目标”区分入睡与明确唤醒；布尔参数必须是JSON boolean，字符串和数字均在发往设备前拒绝。去重、重试及固件侧门禁继续适用。

## 已取得的证据

| 检查 | 覆盖 | 不代表什么 |
|---|---|---|
| `pet_action_checks.cc`三组、`pet_sleep_checks.cc`两组目标编译期断言 | 实际reducer增量、冷却后重试、跨动作重复、旧编号拒绝、新通道编号复用、等待音频、取消后仍超时入睡 | 不是实体键/真实音频测试 |
| `backend/test_pet_identity.py`四项测试 | 并发重复、同轮不同调用ID、取消/过期轮次、上下文隔离、容量不淘汰、睡眠目标与严格布尔校验 | 不包含LLM选工具能力 |
| `evaluation/care-bridge-check.json` | 真实上游handler→executor→MCP发送及响应解析；软件设备收到不同RPC ID和同一动作编号；非法调用不发往设备，无遗留future | 软件设备只回执，不模拟ESP32执行成功 |
| `evaluation/firmware-overlay-check.json` | 固定固件原始文件上叠加补丁，重复应用结果一致 | 不是运行时竞态测试 |
| `evaluation/voice-overlay-check.json` | 固定服务端原始文件上叠加补丁，重复应用结果一致 | 不是干净电脑全安装验收 |
| `evaluation/voice-protocol-check.json` | 认证拒绝/成功及16kHz、60ms音频协商回归 | 没有真实收音、TTS或大模型请求 |

复查命令：

```powershell
./.tools/voice-venv/Scripts/python.exe backend/test_pet_identity.py
./.tools/voice-venv/Scripts/python.exe scripts/check-care-bridge.py
./.tools/voice-venv/Scripts/python.exe scripts/check-voice-overlay.py
./.tools/espressif/python_env/idf5.5_py3.12_env/Scripts/python.exe scripts/check-firmware-overlay.py
./scripts/build-firmware.ps1
```

## 仍需完成

已建立真实设备的认证连接；实际模型通过设备工具读取饱食度，并在明确的调试文本请求后执行一次喂食：74→89、delta=15、durable=true。独立 USB 状态读回确认饱食度89、冷却60秒、revision和persisted_revision均为4730。见 `evaluation/device-care-voice-check.json`。服务端会在工具求值前发送TTS start，因此当前有效会话的Listening与Speaking均可执行工具；连接代次、取消、输入暂停、设置和记忆确认页的限制仍保留。此前误报BUSY的回执保留在 `evaluation/device-care-before-speaking-fix.json`。

输入为协议调试文本；不把这次结果称为声学ASR、完整播放听感或真实按键触点验收。独立记忆确认、取消与超时联调也已通过，见 `docs/记忆确认_实机联调.md`。

仍需完成：抚摸/睡眠及截止时间的实机体验、重复请求实机演示、有效语音互动计入关系、完整记忆管理及删除后的语音上下文清理、发布与实机视频。已有刷写和读回证据，不再沿用早期“未刷写”的状态。
