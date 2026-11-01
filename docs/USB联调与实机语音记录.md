# USB 联调与实机语音记录

2026-10-31。用户只负责最终整体体验验收；中间的状态、协议和回归检查由开发侧完成。需要用户判断的视觉灵动度、听感仍不能用日志替代。

## 开发入口

源码默认关闭 USB 调试。私有 `.runtime/device-endpoint.json` 同时配置本地 OTA 地址和 `usb_diagnostics: true` 才启用；公开复现默认不打开此入口。

用 ESP-IDF Python 执行 `scripts/device_command.py`。命令为 `state`、`main`、`main_hold`、`feed`、`feed_hold`、`pet`、`pet_hold`。入口复用实体按键处理逻辑，但不能把 USB 派发称为真实按键触点测试。每次仅派发一次；不存在自动无限重试。状态输出只保留数值和布尔字段，原始日志留在忽略目录中。

## 本次实际证据

- 当前应用 SHA256：`4fe819ced2b72e28104ca40ee0ae84ab0c88d4e527e0a189a2c53bc9472d30f4`。写入、应用读回和非应用区前后校验通过，见 `evaluation/device-flash.json`。
- 原生 USB 返回真实宠物数值、revision、存储和时钟标志，见 `evaluation/device-usb-state.json`。
- USB 打开语音后，真实设备建立 WebSocket session，经历 connecting、listening、speaking；服务端注册 8 个设备工具，其中 4 个是宠物工具。见 `evaluation/device-voice-handshake-check.json`。
- 随后自动进入并退出设置，取消语音并返回宠物页面。取消期间服务端出现连接关闭错误；本次不以此证明完整播音、听感或 AI 养成动作执行成功。

## 真实联调发现的修复

工具初始化的另一条调用路径仍默认导入未启用插件，触发缺少 markitdown。已在共享插件加载器限制默认列表，避免逐个调用点修补；默认导入回归检查通过。

已知 MP3 解码原来隐式调用未安装的 ffprobe。现在为 MP3 显式提供解码器，复用现有 FFmpeg。离线检查真实执行 MP3→PCM→Opus→PCM，并禁止 ffprobe 查询，通过 6 帧、60ms/帧、16kHz 单声道校验，见 `evaluation/voice-audio-conversion-check.json`。其他格式保持原行为。

重启服务后，真实设备复测没有上述两类错误，并观察到服务端首段语音发送记录。离线解码成功与发送记录均不能替代完整声学验收。本次没有受控口语识别、实机工具执行或新版本完整视觉验收结论。
