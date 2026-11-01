# 小智本地语音桥接（尚未完成端到端验证）

选择Sherpa-ONNX SenseVoice识别、ONNX Silero VAD、Edge TTS、DeepSeek和受控记忆provider。Windows需要Python 3.12。

```powershell
./scripts/setup-voice.ps1 -Python python
& ./.tools/voice-venv/Scripts/python.exe scripts/check-voice-native.py
```

直接依赖见`requirements-voice.txt`；全部实际版本见`locks/voice-requirements-win-py312.txt`。安装会自动获取锁定提交的语音服务源码；已有固定版本及其本地适配保留不覆盖。安装不会启动服务器、使用密钥或更改系统PATH。干净电脑复现尚未验证。

Opus采用上游推荐的conda-forge libopus 1.6.1固定Windows包及SHA-256；仅提取DLL和许可。FFmpeg来自imageio-ffmpeg 0.6.0的Windows二进制。来源记录与许可保存在忽略的`.tools/voice-native/`。服务启动时须仅在服务进程内设置PATH及Windows DLL目录。

已验证：

- Opus实际编解码16kHz单声道60ms帧、FFmpeg可启动，见`evaluation/voice-native-check.json`。
- 官方固定int8识别模型及已有VAD文件通过哈希核对；公开中文样本实际产出识别文本，VAD对该样本与静音的冒烟检查通过，见`evaluation/speech-model-check.json`。不属于识别准确率评估。
- ASR、VAD、DeepSeek兼容客户端、意图模块及自有记忆provider实际构造成功，未绑定设备被拒绝初始化个人记忆，见`evaluation/voice-import-check.json`。
- 软件客户端在临时回环端口通过认证与hello协商；缺少认证被拒绝，16kHz/60ms回复与本地编码配置一致。无非回环连接尝试，见`evaluation/voice-protocol-check.json`。没有设备参与，也未调用LLM或TTS。

```powershell
& ./.tools/voice-venv/Scripts/python.exe scripts/setup-speech-models.py
& ./.tools/voice-venv/Scripts/python.exe scripts/check-speech-models.py
& ./.tools/voice-venv/Scripts/python.exe scripts/prepare-voice.py
& ./.tools/voice-venv/Scripts/python.exe scripts/check-voice-import.py
& ./.tools/voice-venv/Scripts/python.exe scripts/check-voice-protocol.py
```

`prepare-voice.py`从忽略的`.env`生成忽略的上游`data/.config.yaml`，默认仅127.0.0.1、认证开启且无绕过白名单；自有生成标记以外的既有配置不会被覆盖。它还安装mem_pet provider、定向限制插件导入至两个上游基线插件，避免未启用插件的无关SDK依赖。服务配置和本地认证密钥不得提交。2026-10-31已用三份一致的真实芯片日志设置本地`PET_DEVICE_ID`，模块检查确认匹配身份可初始化记忆、不匹配身份被拒绝；这不是设备联网认证或真实语音验收。

准备局域网配置时，可使用 `scripts/prepare-voice.py --bind-ip <本机WLAN的IPv4地址>`。必须先在本地`.env`填写经过核对的`PET_DEVICE_ID`。地址仅允许RFC1918私有IPv4，且必须能在本机绑定；拒绝全地址监听、公网、代理常用的198.18网段和非本机地址。默认命令恢复127.0.0.1。生成配置不会启动服务、修改防火墙或机器人端点；回环协议检查应在默认配置下运行。当前电脑地址的绑定探测、配置生成与恢复已实际检查，见`evaluation/voice-network-check.json`；可运行约束测试：`python -m unittest discover -s scripts -p test_voice_network.py`。

宠物模板保留上游表情变量，但不含默认定位、天气或远端动态上下文；不会因连接设备自动请求定位。识别模型权重的许可独立于工具代码许可，保留原始LICENSE指向与来源，不将权重提交GitHub。

照顾工具桥接已接入：按语音轮次和动作去重（睡眠区分明确的布尔目标），编号经MCP元数据传输，不接受模型参数覆盖。真实上游handler/executor/MCP路径的软件设备检查通过，`evaluation/care-bridge-check.json`保留证据；没有实体动作或真实LLM调用。详情见`docs/AI动作_实现与验收.md`。

OTA POST和WebSocket入口现均要求配置中绑定的Device-ID及非空Client-ID；WebSocket随后仍执行原有HMAC令牌校验。上游`allowed_devices`具有免认证语义，保持为空。真实固定上游的回环软件测试验证其他设备的OTA请求返回403、即使带另一个有效签名的WebSocket也被关闭，绑定设备由OTA领取令牌后能完成hello。测试不调用模型或TTS；OTA的IP选择在测试中固定为回环。Device-ID过滤不是不可伪造的硬件证明，局域网OTA发现仍采用上游按设备标识领取令牌的机制，不应映射到公网。

启动入口：先在另一个终端运行 `./scripts/start.ps1`（记忆后端），然后运行 `./scripts/start-voice.ps1`。默认回环；显式局域网启动使用 `./scripts/start-voice.ps1 -BindIp <本机WLAN的IPv4地址>`。配置检查失败不会启动服务，原生音频库PATH仅在服务进程范围设置，Ctrl+C停止。脚本不会改防火墙或设备端点。

2026-10-31已实际启动两个服务，核对127.0.0.1上8766、8000、8003监听及记忆health；启动快照见 `evaluation/voice-startup-check.json`。进程可能之后停止，使用前应重新检查；启动成功仍不代表实体语音验收。

后续进展：设备已通过独立 `pet_ws` 配置接入局域网后端，实际 WebSocket/MCP 连接成立；原有网络与云端配置仍保留。记忆草稿→设备确认页→保存/取消/超时已通过真实设备、协议调试文本和 USB 按键派发联调，详见 `docs/记忆确认_实机联调.md`。这不是实际收音、按键触点或完整听感验收。

更正/删除后的下一轮语音上下文清理已接入资料版本号，并通过真实隔离数据库、HTTP Provider和上游消息渲染器验证。旧聊天、工具结果和TTS文本缓存会清除；服务故障不回退旧资料。详见 `docs/记忆更正删除_上下文清理.md`。

仍未完成：完整收音到可听回复、AI 照顾与延迟睡眠的完整体验验收、删除时正在播放回复的即时取消，以及最终展示交付。局域网服务须显式绑定本机私网地址并保持认证；默认回环不供实体设备直接访问。
