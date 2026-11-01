# AI Pet Implementation Plan

> **For agentic workers:** Use executing-plans to implement this plan task-by-task. 当前会话直接执行；用户已明确授权开始工作，不另设方案确认轮。

**Goal:** 在用户电脑运行可核查的记忆服务并接入实体AI宠物，完成全屏表情、实体照顾、跨会话记忆与GitHub展示。

**Architecture:** 复用锁定版本的MemoryConstellations存储、证据和检索模块，增加受控确认及语音适配。保留同板型小智驱动，本机养成状态为真值，电脑记忆服务为个人资料真值。

**Tech Stack:** Node.js、SQLite、OpenAI兼容模型API、Python兼容小智语音服务、ESP-IDF5.5／LVGL9。

**Spec:** [详细计划书](../../AI宠物_详细计划书.md)

## Global Constraints

- 240×240全屏大眼睛，日常不显示Wi-Fi、时间、电量或聊天文字。
- 关系变淡不死亡，个人资料与关系分离；离线养成继续。
- 电脑后端为主路线；不把固定回答或协议测试冒充AI记忆完成。
- 原始备份、API密钥与真实资料不入仓；不公开无鉴权局域网服务。
- 当前COM4设备有完整只读备份；首轮改写前核对板型、产物与写入区域。

## Review Focus

1. 新会话或进程重启后，实际模型仍可使用已确认资料。
2. 未确认草稿、重复请求、超时不能产生误保存或重复动作。
3. 断网／删除／更正后旧缓存不能复活旧资料。
4. 时间模拟与真实日期分离，不修改系统时钟，不把模拟结果称长期实测。
5. GIF与语音同时运行不能造成音频欠载、死锁和原配置丢失。

## Task 1：锁版与运行基础

Files：`scripts/setup-memory.ps1`、`backend/upstream-lock.json`、`THIRD_PARTY_NOTICES.md`、`.gitignore`。

- [ ] 固定上游SHA、检查依赖安装脚本与运行入口；本地安装依赖。
- [ ] 在独立虚构数据SQLite库运行上游现代管线聚焦测试，保存摘要，明确它不包含真实模型提取。
- [ ] 交付可复现安装脚本和许可声明；不提交下载缓存。

## Task 2：受控记忆与真实模型闭环

Files：`backend/memory-server.cjs`、`backend/memory-store.cjs`、`backend/llm.cjs`、`tests/memory.test.cjs`、`.env.example`。

Interfaces：loopback HTTP，`/health`只返回状态；记忆提案／确认／资料／召回／更正／删除采用token及revision校验。

- [ ] 先写真实临时库测试：提案不保存、确认后保存、重复确认幂等、重启可读、更正／删除不复活、超长UTF-8拒绝。
- [ ] 观察测试因功能未实现失败，增加最小实现，运行同一测试至通过。
- [ ] 接入用户本地私有API配置；执行真实「自然语言提案→确认→新会话召回→模型回答」，不使用假模型宣告完成。
- [ ] 用虚构资料产出可公开证据；无密钥时保留未完成标记，继续独立任务。

## Task 3：小智语音桥接

Files：`backend/xiaozhi_memory/`适配、配置示例、对应HTTP／上游接口集成测试。

Interfaces：上游`MemoryProviderBase.save_memory(msgs,session_id)`和`query_memory(query)`。

- [ ] 以测试HTTP服务验证注入文本、超时和失败不伪造召回；实现适配。
- [ ] 启动真实兼容语音服务，先验证文字消息和工具，再接设备音频。
- [ ] 服务不可达时本地养成继续；不自动切换云端导致双资料源。

## Task 4：设备固件

Files：锁定同版本板型工程、宠物状态reducer、PetDisplay、按键映射、NVS、宠物工具。

- [ ] 原版同板型编译并核对产物大小，逐键确认GPIO。
- [ ] 先测状态规则、冷却、关系窗口和补时；实现养成reducer与持久化。
- [ ] 接全屏Otto脸、三键、系统设置及草稿确认，测显示／音频并发。
- [ ] 核对OTA与资源更新路径；明确写入区域后部署，不擦除网络／绑定配置。
- [ ] 执行计划书设备验收及2小时运行测试，用户可听可见部分需要实物交互验证。

## Task 5：可审阅交付

Files：`README.md`、`evaluation/`、`demo/`、运行说明。

- [ ] 按计划书30条AI评测及36条功能场景逐项记录真实完成度。
- [ ] 生成无硬件可查看的虚构记忆记录和实机视频脚本；真实视频由实物拍摄获得。
- [ ] 首页清楚区分复用／新增、测试／真实模型／实机，检查所有本地链接及秘密文件忽略。
- [ ] 当前会话最终做一次全改动审查；未达到设备与展示要求前不标整项目完成。
