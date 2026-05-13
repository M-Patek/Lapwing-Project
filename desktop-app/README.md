# Live2D Desktop Application for Lapwing

## 架构

```
Lapwing Desktop/
├── main.py              # Entry point
├── lapwing_widget.py    # Live2D rendering widget
├── api_client.py        # Communication with Lapwing API
├── audio_player.py      # Audio playback + lip sync
├── config.py           # Configuration
├── models/             # Live2D model directory
│   └── hiyori/         # Momose Hiyori model
│       ├── hiyori.model3.json
│       ├── hiyori.moc3
│       ├── textures/
│       └── motions/
└── resources/          # Resource files
```

## Install Dependencies

```bash
pip install PyQt6 PyQt6-WebEngine requests websockets
```

## Get Momose Hiyori Model

1. Download Live2D Cubism SDK for Native:
   https://www.live2d.com/download/cubism-sdk/download-native/

2. Model files are usually at:
   `CubismSdkForNative-4.x.x/Samples/Resources/Hiyori/`

3. Copy to this project's `models/hiyori/` directory

## Run

```bash
python main.py
```

## Shortcuts

- `Ctrl+Shift+S`: Show/Hide
- `Ctrl+Shift+M`: Microphone toggle
- `Ctrl+Shift+Q`: Quit
- Mouse drag: Move window
- Mouse wheel: Zoom

## Features

- [x] Transparent background, always on top
- [x] Voice synthesis (GPT SoVITS)
- [x] Lip sync
- [x] Expression control (based on EII)
- [x] Speech bubble
- [ ] Touch interaction
- [ ] Eye tracking
