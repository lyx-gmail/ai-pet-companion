# Third-party components

此项目复用以下上游能力；不宣称自行研发基础语音栈或完整记忆引擎。精确版本见[锁定清单](backend/upstream-lock.json)。

| Component | Source | License | Use |
|---|---|---|---|
| MemoryConstellations | https://github.com/ClaraShafiq/MemoryConstellations | MIT | 复用部分SQLite、字段加密、证据协议及检索管线；虚构资料的确认、召回、更正和删除有独立进程实测 |
| xiaozhi-esp32-server | https://github.com/xinnan-tech/xiaozhi-esp32-server | MIT | 语音服务及记忆provider扩展；实机WebSocket/MCP与程序化记忆确认已有证据，完整声学体验待验收 |
| xiaozhi-esp32 | https://github.com/78/xiaozhi-esp32 | MIT | 已购设备的板级驱动、语音与显示；目标板显示及启动更新行为已有适配 |
| Otto GIF | https://github.com/txp666/otto-emoji-gif-component | MIT | 原始21个GIF已用于独立浏览器预览，完整许可附在web/animation-preview/OTTO-LICENSE.txt；尚未写入设备 |
| SenseVoice int8 model | https://github.com/k2-fsa/sherpa-onnx/releases/tag/asr-models | 权重许可独立；原包LICENSE指向FunASR模型许可说明 | 固定发布包及SHA-256见backend/locks/speech-models.json；仅项目本地下载和推理，不提交权重 |
| Windows Opus / FFmpeg | https://conda-forge.org/ / https://github.com/imageio/imageio-ffmpeg | 各二进制原始许可随安装包保留 | 便携语音依赖，仅保存在忽略的.tools中；固定来源及校验记录随安装生成 |

RoboEyes已引入固件适配层：运动内核及完整GPL-3.0许可位于`firmware/vendor/RoboEyes/`，版本、原始校验值及本地初始化顺序修复见其中`UPSTREAM.md`；链接该内核的固件模块遵守GPL-3.0-or-later。固件已实际写入并读回，用户曾确认全屏双眼的眨眼和转动；最新镜像的完整视觉与听感仍待最终验收。各记录绑定镜像版本，不将早期确认自动继承给新镜像。

Grobot_Animations（MIT）、robo_eyes_esphome（README标MIT，完整许可待核）、roboeyes-image-editor（GPL-3.0）及lvgl_kawaii_face（MIT）目前仅在忽略的研究目录用于选型，未引入固件。

上游源码保留在本地`.tools/upstream/`，原始LICENSE随下载保留。公开分发任何复用源码或资源时须附其完整许可与版权；本文件仅为归属索引，不能替代许可原文。Node、SQLite及npm间接依赖的许可随各安装包保留。

供源码审阅的MIT许可原文已按本地固定版本逐字复制：[MemoryConstellations](licenses/MemoryConstellations-LICENSE.txt)、[xiaozhi-esp32](licenses/xiaozhi-esp32-LICENSE.txt)、[xiaozhi-esp32-server](licenses/xiaozhi-esp32-server-LICENSE.txt)。RoboEyes与Otto的完整许可仍分别位于其资源目录。项目自有代码采用根目录 GPL-3.0-or-later，保留上游独立许可；预览版不表示所有功能已完成验收。

模型许可来源说明：https://github.com/modelscope/FunASR#license 。不能将工具仓库MIT许可直接套用于模型权重；当前只发布安装脚本、来源记录与推理检查结果。
