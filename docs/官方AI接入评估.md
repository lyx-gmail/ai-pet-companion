# 官方 AI 与宠物系统的接入评估

## 已核验的账号能力（2026-10-31）

在用户登录后的官方控制台实际查看：一个智能体，已有一台绑定设备；当前模型为“小智 Lite”，记忆开关开启、条目数量0。角色页提供自定义开关，扩展能力页有MCP接入点，当前状态未连接。没有保存角色、模型或设备设置。

接入点展开提示“每次打开都会生成新地址，旧地址仍然有效”。因此展开属于取得新的访问地址，不能在日志、文档或Git中保存地址及令牌；本轮未连接或部署该接入点，也未记录访问地址。

当前物理设备仍运行本地后端模式，实际模型为用户配置的DeepSeek Flash。账号后台能看到选项，不代表物理设备已经使用官方AI。

## 可以复用与尚需验证的部分

官方项目的设备MCP协议支持发现和调用设备工具，作者也提供外部MCP工具示例：

- https://github.com/78/xiaozhi-esp32/blob/main/docs/mcp-usage_zh.md
- https://github.com/78/mcp-calculator

可先以只读`self.pet.get_state`验证官方AI能否读取真实宠物状态；再验证单次喂食，最后评估外部记忆。官方AI负责语言理解和回复，设备继续负责确定性状态、按键、表情与存档。

现有实现不能直接换个地址就算兼容：

| 部分 | 当前依赖 | 官方接入时需证明 |
|---|---|---|
| 状态读取 | 标准设备MCP、无额外请求元数据 | 工具被发现，返回实际数值且模型正确引用 |
| 喂食、抚摸、睡眠 | 本地适配器生成`pet_request_id`，设备绑定epoch并拒绝重放 | 使用官方可提供的可信调用身份，保留取消、冷却和去重保护 |
| 关系计分 | 本地ASR来源标记、轮次和播放完成条件 | 官方消息能可靠区分真实收音与调试输入，不能伪造来源凑计分 |
| 个人资料 | 本地确认事务、revision及下一轮历史清理 | 外部MCP能取用资料；更正/删除后不复用旧资料；确认仍由实体按键决定 |
| 设备记忆管理HTTP | 当前本地语音服务签发的令牌和设备绑定 | 不能将官方令牌直接当作本地服务的有效令牌，需独立可信桥接 |

官方原生记忆开关不等于项目要求的可管理称呼、四条偏好及经历衰减策略；没有证据说明能替代现有本地记忆服务。是否每轮强制取用记忆、能否删除后立即清除旧上下文，仍待实际验证。

## 启动体验与后端选择分离

用户目标是连网后进入宠物界面。官方模式使用原有合法绑定；本地模式不应等待官方激活，也不应因电脑关机卡在启动检查。去掉启动等待不等于取消服务认证。

本地启动补丁仅在显式配置局域网后端时生效：连网后直接初始化WebSocket并进入idle，再后台发现服务；语音请求前进行一次有超时的本地发现。原官方启动分支保留，当前未切换官方AI、未增加自动双后端回退。

本轮完整构建、重复补丁检查及实际设备验证结果，以`evaluation/firmware-build.json`、`evaluation/device-flash.json`、`evaluation/direct-boot-check.json`为准。日志状态不替代肉眼确认动画效果。

## 官方只读工具闭环已验证（2026-10-31 23:06）

使用这台设备已校验备份中的原UUID和本地配置中已核验的设备身份，向固件原有官方HTTPS发现地址请求会话配置，返回200、无需激活，同时提供WebSocket和MQTT配置。没有下载固件、重绑设备或切换实机后端。凭据仅放在被Git忽略的`.runtime/official-ai`内；公开记录见`evaluation/official-ai-discovery-check.json`。

电脑测试客户端通过官方WSS认证并完成MCP工具发现，只开放`self.pet.get_state`。第一次用detect通道发送长文本被官方明确拒绝：“Detect is only for wake words, do not send long texts.” 该失败记录保留为`evaluation/official-ai-read-state-text-probe.json`，不能将握手成功当作模型调用成功。

随后用现有EdgeTTS生成固定测试问句，转为16kHz单声道、60ms的Opus帧，经标准listen/start、音频帧及listen/stop通道输入。官方AI实际调用一次状态工具，客户端在调用时经原USB开发入口读取真实机器人状态，当时饱食度96；官方回复中含相同数值并正常结束，收到59个回复音频包。见`evaluation/official-ai-read-state-check.json`，包含匿名的实际工具结果快照。输入是合成语音，没有进行实体麦克风或扬声器听感验收。

此闭环证明“官方AI可调用我们的工具并引用真实设备数据”。它不证明实机已经直连官方、喂食等写操作已兼容、外部记忆已接入，或官方回复已经在机器人扬声器播放。电脑客户端仅用于兼容性验证，不能包装为已完成的设备端产品架构。

复查命令（需要这台自有设备的私有身份及会话配置，非通用匿名演示）：

```powershell
& ./.tools/voice-venv/Scripts/python.exe scripts/official-ai-discovery.py
& ./.tools/voice-venv/Scripts/python.exe scripts/test_official_ai_probe.py
& ./.tools/voice-venv/Scripts/python.exe scripts/official_ai_probe.py --audio
```

测试不开放写工具，不给AI任意串口命令能力；读取失败返回明确错误。两个边界测试覆盖未开放工具、额外参数及真实读取故障；原本地记忆和语音服务保持在线。

## 经过本地认证入口的官方转发（2026-10-31 23:28）

新增`backend/pet_official_proxy.py`，复用现有WebSocket服务的设备绑定和HMAC认证。仅在两项认证均通过后，读取显式后端选择；默认仍为local，缺少选择文件也为local，损坏或未知选择会拒绝连接，不会自动调用另一个模型。官方配置每次通过固定HTTPS地址发现，只接受`api.tenclass.net`的WSS端点，HTTPS/WSS均禁止跟随重定向。云端凭据只在电脑内存中使用，不下发设备、不输出日志。

官方模式通过设备原有MCP转发`get_state/feed/pet/set_sleep`四个工具，暂时隐藏未适配的记忆及其他系统工具。喂食、抚摸和睡眠必须在接收实际上传音频并收到非空ASR结果后才能转发；适配器覆盖云端传入的来源标记和动作编号。相同轮次同一动作重用编号，已有RPC编号不能更换动作或跨轮重用；参数、容量、取消及重叠轮次都有拒绝条件。设备端现有epoch、冷却、设置页、睡眠及存档校验保留。取消时关闭云端会话，两端之一断开会终止另一转发任务。

已通过11项软件检查，覆盖真实本地WebSocket收发、取消后云连接关闭、重定向不得携带凭据、重复动作/变更ID/非法参数拒绝、未知工具过滤和中文数值匹配。补丁在固定版本原始源码及重复应用检查均通过。重启正式本地语音服务后，错误HMAC及其他设备身份仍被拒绝，记录见`evaluation/official-proxy-check.json`。

此外，使用真实`WebSocketServer`的认证与路由，在**独立电脑回环监听器**完成一次官方闭环，没有切换正式后端选择。仅跳过该隔离测试不会使用的本地模型初始化。输入88帧合成Opus，官方AI经转发调用只读工具，在调用时USB读取实机饱食度95，回复说“饱食度九十五”，收到223个回复音频包并正常结束。最初数值检查仅识别阿拉伯数字而误报，已增加中文数值测试，并用同一次私有会话记录重新核验，无需重复云端请求。证据见`evaluation/official-ai-proxy-read-state-check.json`。

复查软件边界：

```powershell
& ./.tools/voice-venv/Scripts/python.exe scripts/test_official_proxy.py
& ./.tools/voice-venv/Scripts/python.exe scripts/test_official_ai_probe.py
& ./.tools/voice-venv/Scripts/python.exe scripts/check-voice-overlay.py
# 以下会访问官方服务并只读USB实机；使用独立监听器，不改正式后端选择。
& ./.tools/voice-venv/Scripts/python.exe scripts/official_ai_probe.py --audio --bridge
```

当前正式设备仍使用本地DeepSeek后端。电脑链路测试不等于实体麦克风、扬声器听感或官方AI实机照顾动作验收。外部记忆尚未接到官方AI；未完成记忆适配前不将官方模式设为默认，避免已有称呼、偏好和确认流程失效。官方原生记忆与本地记忆仍不能当作同一套数据。

## 记忆适配验证与主线选择（2026-10-31，后续）

在隔离电脑监听器中，现已将本地已确认记忆合并到`self.pet.get_state`的首个JSON文本结果。最初追加第二个MCP文本段时，官方AI未采用称呼；该失败保存在`evaluation/official-memory-before-single-content.json`。改为单个JSON结果后，独立RAM数据库里的虚构称呼读取、更正、删除三个官方AI测试均通过，见`evaluation/official-memory-check.json`。输入没有说出待查询称呼，状态工具仍在调用时USB读取实机；正式记忆库前后相同。每步使用新的云端会话，不能将其扩展为已验证清除官方服务内部历史。

`pet_official_memory.py`为每轮回复要求新鲜记忆结果，记忆版本变化或服务故障时终止转发；尚未证明能即时清除已排入实机播放队列的旧音频。记忆提案工具`self.pet.remember`只接受空参数，使用实际ASR输入及既有`confirm_memory`流程；内部确认RPC使用保留ID区间，不开放给模型，模型无法通过参数制造按键同意。重复调用复用本轮结果，取消/超时不提交；明确记忆意图的语音在取得确认流程结果前不放行。

独立写入测试中，官方AI实际调用提案工具，软件设备夹具返回一次确认，RAM库保存虚构称呼“小明”，官方回复正确。证据`evaluation/official-memory-write-check.json`明确标注软件同意，不是实体按键验收；正式数据库未变。真实设备端确认UI仍需进一步整体验证。软件边界共20项通过，来源hash、正式本地模式及实时认证拒绝检查见`evaluation/official-proxy-check.json`。

```powershell
# 不调用云端模型，检查软件边界与正在运行的本地认证入口
& ./.tools/voice-venv/Scripts/python.exe scripts/check-official-boundaries.py
# 以下两条会调用官方AI；仅在主动恢复官方适配研究时运行
& ./.tools/voice-venv/Scripts/python.exe scripts/check-official-memory.py
& ./.tools/voice-venv/Scripts/python.exe scripts/check-official-memory.py --write-only
```

**用户后续决定：官方接入先放下，继续用已实现的本地AI。** 正式后端选择固定为`local`，不再扩展官方路线；现有实验代码保留作研究记录。后续主线是设备端记忆查看/删除界面、播放取消、离线关系结算和整体效果验收。没有修改账号角色、模型或记忆开关；检查官方控制台时，原生记忆列表仍显示0条。
