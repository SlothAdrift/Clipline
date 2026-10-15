# 截图晾衣绳源码存档

此文件夹是可独立运行的 Windows 源码副本，用于保存和恢复阶段性版本。包含主程序、窗口绘制代码、测试、依赖声明和运行所需的图标。不包含安装包、构建缓存或用户截图数据。

## 运行与测试

在 Windows 10 1809 及以上或 Windows 11 的 x64 电脑上安装 Python 3.10 及以上版本，在本文件夹打开终端：

```powershell
python -m pip install -r requirements.txt
python clothesline.py
```

运行测试：

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
python -m unittest discover -s . -p test_clothesline.py -q
python test_hotkey_native.py -q
```

程序在系统托盘运行。开启功能后，剪贴板中的图片会显示在屏幕顶部。`Win + Alt + L` 或 `Ctrl + Alt + Shift + L` 可展开晾衣绳。图片和设置保存在 `%LOCALAPPDATA%\ScreenshotClothesline`，不在此源码文件夹中。

## 保存与恢复

此文件夹自身是独立 Git 仓库。先进入此目录，再保存这一份精简源码：

```powershell
cd 'C:\Users\LHY\Documents\ChatGPT\windows 截图晾衣架\git存档'
git add .
git commit -m 'Save working clothesline source'
```

需要返回某个存档时，先用 `git log --oneline` 找到提交号。备份当前未提交的改动后，执行：

```powershell
git restore --source <提交号> -- .
```

此操作只恢复本文件夹，不会修改外层的安装包。确认源码稳定后，再按原流程同步到发布版并重新打包。
