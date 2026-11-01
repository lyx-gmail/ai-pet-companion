# 开源资源选型

核对日期：2026-10-30。最新决策：用户补充「优先成熟实现、尽可能灵动」后，主脸改为优先验证成熟实时眼睛引擎的LVGL适配；Otto用于可视化对照和兼容回退。详见[表情动画实现选型](表情动画_实现选型.md)。下文原先GIF优先的顺序已由该决策更新。FUMI仍只参考机制，不直接移植整机固件。

## 1. 首选：Otto GIF

- [仓库](https://github.com/txp666/otto-emoji-gif-component)；[MIT许可原文](https://github.com/txp666/otto-emoji-gif-component/blob/main/LICENSE)。当前查到的 HEAD：`4a666924e8e4e2bb55fb9d3167211bb936224abf`。
- README说明资源为240×240、黑底灰白几何脸、21种动态表情，适用于ESP-IDF及LVGL9；最新说明的循环约3.2–4秒，帧间隔80ms，全包约940KB。这是当前版本资料，不代表本机已安装同一资源。
- 小智 [v2.0.4依赖表](https://github.com/78/xiaozhi-esp32/blob/v2.0.4/main/idf_component.yml) 已列 `txp666/otto-emoji-gif-component: 1.0.2` 及 LVGL `~9.3.0`。因此先核查锁定版实际资源和接口，不能直接把最新1.4系列示例套进旧版。
- 小智同版本 [lcd_display.cc](https://github.com/78/xiaozhi-esp32/blob/v2.0.4/main/display/lcd_display.cc) 存在GIF播放器与`SetEmotion`入口；具备代码适配基础，不等于实机已开启Otto主题或可直接全屏。
- 采用方式：保留已有显示驱动，去掉日常布局的状态栏与文本区域，把表情容器设为全屏；优先用锁定版已有素材，不先升级组件。资源包索引、动画结束事件、未找到表情的回退需逐项核对。
- 许可处理：分发复用代码／资源时保留版权与许可。当前仓库称GIF由脚本生成；正式引入时仍检查具体文件是否另附声明，并记录实际采用的commit／组件版本及文件校验值。

## 2. 备用：LVGL Kawaii Face

- [仓库](https://github.com/0015/lvgl_kawaii_face)；[MIT许可](https://github.com/0015/lvgl_kawaii_face/blob/main/LICENSE)；核对HEAD：`d58e1c8f8e7baa7bc93d5ae0dc18affee7f3ccbb`。
- 基于LVGL9画布绘制眼睛、眉毛、嘴与动态情绪。可参考其参数化脸部动画，方便调整眼睛比例和低帧率状态。
- 优点是无需为每一种过渡准备大批图片；仍需测画布内存和每帧CPU消耗，不能直接声称比GIF更省内存。
- 只有首选资源确实不合适，才投入这个适配；不同时维护两套生产播放器。引入时保留MIT声明并锁版本。

## 3. 机制参考：FUMI

- [仓库](https://github.com/imaaiagent/fumi)；[MIT许可](https://github.com/imaaiagent/fumi/blob/main/LICENSE)；核对HEAD：`a642daf2f9e5043740d0782991a7d10b675c2a85`。
- 可研究养成参数、交互与AI接口的职责划分；自己的数值规则需独立定义和验证。
- 作者标注项目仍属实验阶段，其触摸、板型和固件环境不同。本机不复用触摸交互，不使用其整包固件及分区配置。

## 4. 引入前清单

1. 固定具体版本，检查许可和第三方来源；不自动执行仓库脚本。
2. 用实际采用的GIF核对尺寸、时长、首尾帧、黑底和损坏文件回退；桌面预览只作视觉确认。
3. 先接一个neutral、一个delicious，在现有语音工作时测峰值内存、延迟与音频。
4. 再扩展其余表情；缺少「聆听／说话」专用素材时复用表情并做轻微眼神变化，不虚构音素口型。
5. 明确许可随交付保存的位置。未最终采用资源前不建立虚假的第三方归属清单，也不声称已完成适配。

本轮只做资料核对，未下载执行表情生成脚本、未将资源写入设备。

## 5. 新增记忆候选：Memory Constellations · 记忆星图

- [仓库](https://github.com/ClaraShafiq/MemoryConstellations)；[MIT许可](https://github.com/ClaraShafiq/MemoryConstellations/blob/main/LICENSE)。这是用户描述的相似候选，尚未确认是同一项目。
- 当前 [README](https://github.com/ClaraShafiq/MemoryConstellations/blob/main/README.md) 要求Node.js18+及SQLite构建依赖；Python/ChromaDB仅旧版向量路线需要。新版有观察、证据、实体与叙事、检索投影等层；文档明确真实自然消息到最终角色召回尚未完成最终验收。因此不能照旧搜索缓存直接部署或承诺效果。
- 直接检查 [services/lifecycle.js](https://github.com/ClaraShafiq/MemoryConstellations/blob/main/services/lifecycle.js)：未读活跃碎片创建14天后可冷却，冷却30天后可冻结并删向量，冻结90天后可清空正文；访问后的处理另有状态条件。阶段时长并非全部从创建日起累计。叙事记忆另有成熟降权与归档逻辑。文件存在不代表新版运行路径一定启用它，需要启动与调度追踪。
- 据此只能确认有遗忘／生命周期设计，不能认定精确复刻艾宾浩斯曲线。对本项目而言，优先研究「随时间降权、访问强化、稳定资料保留、可追溯纠错」。
- 运行在电脑／服务器，通过语音后端桥接，不是烧到ESP32的库。最新完整管线较复杂，先固定版本和最小召回路径；不复制其全部演示界面。
- 模型抽取、整理和对话都有可能产生费用；当前文档不保证固定月费。先用虚构资料测调用次数与token，不填写未经核实的「永久免费」。

## 6. 另一相似候选：Constellation Engine

- [仓库](https://github.com/CONSTELLATION-ENGINE/constellation-engine)；仓库标注AGPL-3.0，正式采用需核对具体许可和复用方式。
- 主张以星图连接、激活扩散、强化和衰减组织记忆，包含持久身份锚点。与前一个项目不是同一套系统。
- 目前只核对README方向和许可文件，未审计运行实现，不与「已核对生命周期源码」混写。适合作为用户认领原项目的另一选项，暂不同时部署两套记忆引擎。
