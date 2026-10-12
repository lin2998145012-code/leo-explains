# Leo 讲开源

由 Leo（黑色羽绒服、领子遮住半张脸的 Q 版角色）出镜讲解开源项目的短片，每集出竖版和横版两个版本。

| 集数 | 项目 | 成片 |
| --- | --- | --- |
| EP.01 | [morluto/rea](https://github.com/morluto/rea)：REA，逆向一切 | 竖版 `out/leo-explains-rea-portrait.mp4`（1080×1920，抖音）<br>横版 `out/leo-explains-rea-landscape.mp4`（1920×1080，X 文章） |

## 制作流程

所有素材都在本地生成：配音用离线语音模型（可以克隆你的声音），背景音乐和音效由代码合成，画面是 HTML 动画逐帧截图。
同一套时间轴和音轨渲染两次，分别得到竖版和横版。

```
assets/leo.webp ──cutout.py──▶ leo.png / leo_blink.png / leo_happy.png
video/script.json ──tts.py──▶ build/vo/*.wav + build/timeline.json
video/index.html ──render.mjs --cues──▶ build/cues.json（音效触发点）
timeline + vo + cues ──mix.py──▶ build/soundtrack.wav（人声 + lo-fi 配乐 + 音效）
video/index.html ──render.mjs --layout portrait|landscape──▶ out/*.mp4
```

- **角色**：`tools/cutout.py` 把原图抠成透明 PNG，并画出眨眼和笑眼两种表情。
  Leo 的嘴藏在领子里，所以说话时不做口型，而是用身体轻微摇摆、跳跃和眨眼来表现。
- **配音**：[sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) 离线运行。
  - 克隆声音：把 10–20 秒干净的录音放到 `voice/ref.wav`，逐字稿放到 `voice/ref.txt`，用 ZipVoice 零样本克隆。
    `voice/` 不进 git：一段干净录音就足够复刻一个人的声音。
  - 没有参考录音时用 Kokoro v1.1-zh 男声（sid 58）。
  - 加 `--asr` 时每句生成后会用 SenseVoice 转写回来，和台词对不上就重录（最多 4 次取最好的一次），
    结果写到 `build/asr_report.txt`。
  - `script.json` 里的 `text` 是字幕，`tts` 是给模型读的写法（比如 `REA` 读成 `R E A`）。
- **时间轴**：每句台词的实际时长决定镜头节奏；`index.html` 用 `at(场景, 句, "关键词")`
  把动画对齐到说出该关键词的时刻，改台词后不用手动调时间。
- **渲染**：页面暴露 `seek(t)`，Playwright 逐帧截图后通过管道交给 ffmpeg，渲染结果和机器速度无关。
  横版是同一个页面加 `?layout=landscape`：Leo 和对话气泡在左，讲解内容在右。

## 运行

```bash
npm install
pip install sherpa-onnx soundfile numpy pillow
# 模型放在同一个目录（都在 https://github.com/k2-fsa/sherpa-onnx/releases ）：
#   tts-models/sherpa-onnx-zipvoice-distill-int8-zh-en-emilia   克隆声音
#   vocoder-models/vocos_24khz.onnx                             克隆声音
#   asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17   校对
#   tts-models/kokoro-multi-lang-v1_1                           默认声音
tools/build.sh /path/to/models
```

改画面后可以先出几张静帧检查：`node tools/render.mjs --layout landscape --stills 3,18,40`（输出到 `build/stills/`）。

## 素材与许可

- Leo 角色形象归作者所有。
- `assets/rea/` 里的截图和案例插图来自 [morluto/rea](https://github.com/morluto/rea)（MIT，见 `assets/rea/LICENSE`）。
- 字体：Noto Sans SC、ZCOOL KuaiLe、JetBrains Mono（均为 OFL，通过 npm 的 `@fontsource` 包引入）。
