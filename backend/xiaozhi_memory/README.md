# 小智记忆桥接

这是已锁定版本 `xiaozhi-esp32-server` 的自定义 Memory provider。已验证调试输入触发的实机确认及模型回复链路；麦克风识别与实际听感尚未验收。设备端查看、删除菜单尚未接通，新增认证管理通道见[设备端记忆管理](../../docs/设备端记忆管理.md)。

将 `mem_pet` 目录复制到上游 `main/xiaozhi-server/core/providers/memory/`。在私有 `data/.config.yaml` 中合并以下配置，保留原ASR、TTS、LLM等配置：

```yaml
selected_module:
  Memory: PetMemory
Memory:
  PetMemory:
    type: mem_pet
    endpoint: http://127.0.0.1:8766
    token: 在本地填PET_API_TOKEN
    expected_device_id: 在实机日志核实设备ID后填写
    timeout: 3
```

先运行项目根目录 `scripts/start.ps1`，再运行语音服务。设备ID为空或不匹配会拒绝初始化，不允许其他设备共用个人资料。记忆服务仅监听电脑回环地址；设备不直接访问此接口。

每次语音提问前查询已确认资料；掉线时返回明确的记忆不可用说明。断开连接不会自动把整段聊天写入长期记忆。语音提案已连接实体确认；更正或删除后的下一轮会按资料版本清理旧会话历史。正在播放音频的即时取消仍待完成，不能声称全部记忆交互已经验收。

这里只限制了记忆侧访问。将上游语音服务开放到局域网前，仍需配置其鉴权、设备白名单和防火墙；不要直接使用默认无鉴权配置。
