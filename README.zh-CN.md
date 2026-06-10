# Camera Timelapse Controller

[English](README.md) | 简体中文

Camera Timelapse Controller 是一个基于 `gphoto2` 的 Python 命令行工具，用于控制相机进行包围曝光延时拍摄。

它适用于可以先拍摄到相机存储、再把照片下载回电脑的相机。默认模式使用相机自身的 AEB 状态完成每组三张包围曝光，手动模式则会在每次拍摄前切换曝光补偿。

## 功能

- 循环拍摄三张一组的包围曝光照片，适合延时摄影流程。
- 默认使用相机 AEB 模式。
- 在 AEB 不适用时，可使用手动曝光补偿模式。
- 将照片下载为连续编号的输出序列。
- 根据输出目录中的已有文件继续编号。
- `--interval` 使用时间戳计算，拍摄和下载耗时会计入间隔。
- 当单组耗时超过设定间隔时，打印 warning 并立即开始下一组。
- 在 macOS 上运行时，会临时抑制 `PTPCamera` 对相机的占用。
- 提供 `--dry-run` 用于预览命令和检查流程。

## 环境要求

- 推荐使用 Python 3.9 或更新版本。
- 需要安装 `gphoto2`，并确保它可以访问相机。
- 需要一台 `gphoto2` 支持的相机。

在 macOS 上可以用 Homebrew 安装 `gphoto2`：

```bash
brew install gphoto2
```

检查相机是否可见：

```bash
gphoto2 --auto-detect
```

## 快速开始

在项目目录中以 editable 模式安装命令：

```bash
python3 -m pip install -e .
```

如果系统 pip 较旧，建议在虚拟环境中先升级 `pip`、`setuptools` 和 `wheel` 后再安装。

拍摄两组包围曝光，并让每组开始时间之间间隔 5 秒：

```bash
camera-timelapse . --interval 5 --round 2
```

持续拍摄，直到手动中断：

```bash
camera-timelapse . --interval 10
```

等待到今天 21:30 后再开始拍摄：

```bash
camera-timelapse --start-at 21:30 --interval 5 --round 100
```

如果当天该时间已经过去，程序会打印 warning 并立即开始。

在今天 22:00 到达后，拍完当前组就停止：

```bash
camera-timelapse --end-at 22:00 --interval 5
```

如果同时提供 `--round`，则以 `--round` 为准，`--end-at` 会被忽略并打印 warning。

指定输出目录：

```bash
camera-timelapse ./capture --interval 6 --round 100
```

不连接相机，只预览执行流程：

```bash
camera-timelapse . --dry-run --interval 5 --round 2
```

旧的脚本入口仍然可用：

```bash
python3 /path/to/Camera-Timelapse-Controller/bracket_capture.py . --interval 5 --round 2
```

如果没有提供目录，程序会在运行时询问。

## 拍摄模式

### AEB 模式

AEB 是默认模式：

```bash
camera-timelapse . --mode aeb --interval 5 --round 10
```

程序会读取相机当前 AEB 拍摄序号，并完成当前三张一组的包围曝光。如果相机已经处于 AEB 组中间，程序只会拍摄完成这一组所需的剩余张数。

### 手动模式

手动模式会在每次拍摄前切换曝光补偿：

```bash
camera-timelapse . --mode manual --interval 5 --round 10
```

如果程序无法自动识别曝光补偿配置路径，可以手动传入：

```bash
camera-timelapse . --mode manual --config /main/capturesettings/exposurecompensation
```

可以用下面的命令查看相机支持的配置路径：

```bash
gphoto2 --list-config
```

## 间隔逻辑

`--interval` 表示每组拍摄开始时间之间的目标间隔。

例如设置 `--interval 6` 时，如果本组拍摄加下载耗时 3 秒，程序只会再等待 3 秒再开始下一组。

如果本组拍摄加下载耗时超过了设定间隔，程序会打印 warning，并立即开始下一组。

使用 `--interval 0` 可以关闭组间延迟。

## 输出文件

文件会写入你传入的目录，或者你在提示中输入的目录，并按组编号和组内序号命名：

```text
0001_01.jpg
0001_02.jpg
0001_03.jpg
0002_01.jpg
0002_02.jpg
0002_03.jpg
```

如果输出目录中已经存在编号文件，程序会从已有最大组号继续编号。

临时下载缓存会创建在你指定的目录下面，结束后自动删除。

## 参数说明

```text
--mode {aeb,manual}       拍摄模式，默认为 aeb。
output_dir PATH           下载目录，例如 `.`。
--output-dir PATH         同一目录的可选别名。
--config PATH             手动模式下的曝光补偿配置路径。
--gphoto PATH             gphoto2 可执行文件路径。
--dry-run                 只打印命令，不控制相机。
--interval SECONDS        每组开始时间之间的秒数。
--start-at HH:MM          等待到今天的 24 小时时间后再开始。
--end-at HH:MM            到达今天的这个时间后，拍完当前组就停止。
--round COUNT             总拍摄组数，省略时会持续拍摄。
```

## 注意事项

- 使用 AEB 模式前，请先在相机上配置好 AEB 参数。
- 请确保相机存储空间足够。
- 请确保电脑磁盘空间足够保存下载照片。
- 运行中的拍摄任务可以用 `Ctrl-C` 中断。
