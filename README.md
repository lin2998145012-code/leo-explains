# Leo 讲开源

由 Leo（黑色羽绒服、领子遮住半张脸的 Q 版角色）出镜讲解开源项目的竖屏短片。

| 集数 | 项目 | 成片 |
| --- | --- | --- |
| EP.01 | [morluto/rea](https://github.com/morluto/rea)：REA，逆向一切 | `out/leo-explains-rea.mp4`（1080×1920，30fps，约 98 秒） |

## 制作流程

所有素材都在本地生成：配音用离线 TTS，背景音乐和音效由代码合成，画面是 HTML 动画逐帧截图。

```
assets/leo.webp ──cutout.py──▶ leo.png / leo_blink.png / leo_happy.png
video/script.json ──tts.py──▶ build/vo/*.wav + build/timeline.json
video/index.html ──render.mjs --cues──▶ build/cues.json（音效触发点）
timeline + vo + cues ──mix.py──▶ build/soundtrack.wav（人声 + lo-fi 配乐 + 音效）
video/index.html ──render.mjs──▶ out/*.mp4
```

- **角色**：`tools/cutout.py` 把原图抠成透明 PNG，并画出眨眼和笑眼两种表情。
  Leo 的嘴藏在领子里，所以说话时不做口型，而是用身体轻微摇摆、跳跃和眨眼来表现。
- **配音**：[sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) + Kokoro v1.1-zh 男声（sid 58）。
  `script.json` 里的 `text` 是字幕，`tts` 是给 TTS 读的写法（比如 `REA` 读成 `R E A`）。
- **时间轴**：每句台词的实际时长决定镜头节奏；`index.html` 用 `at(场景, 句, "关键词")`
  把动画对齐到说出该关键词的时刻，改台词后不用手动调时间。
- **渲染**：页面暴露 `seek(t)`，Playwright 逐帧截图后通过管道交给 ffmpeg，渲染结果和机器速度无关。

## 运行

```bash
npm install
pip install sherpa-onnx soundfile numpy pillow
# 模型：https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/kokoro-multi-lang-v1_1.tar.bz2
tools/build.sh /path/to/kokoro-multi-lang-v1_1
```

改画面后可以先出几张静帧检查：`node tools/render.mjs --stills 3,18,40`（输出到 `build/stills/`）。

## 素材与许可

- Leo 角色形象归作者所有。
- `assets/rea/` 里的截图和案例插图来自 [morluto/rea](https://github.com/morluto/rea)（MIT，见 `assets/rea/LICENSE`）。
- 字体：Noto Sans SC、ZCOOL KuaiLe、JetBrains Mono（均为 OFL，通过 npm 的 `@fontsource` 包引入）。
