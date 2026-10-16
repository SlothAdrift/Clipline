from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "交付" / "Clipline-产品介绍与使用手册.pdf"
FONT = Path("C:/Windows/Fonts")
pdfmetrics.registerFont(TTFont("Deng", str(FONT / "Deng.ttf")))
pdfmetrics.registerFont(TTFont("DengBold", str(FONT / "Dengb.ttf")))
pdfmetrics.registerFontFamily("Deng", normal="Deng", bold="DengBold")

W, H = A4
NAVY = colors.HexColor("#18304B")
INK = colors.HexColor("#24364A")
MUTED = colors.HexColor("#63768B")
TEAL = colors.HexColor("#18A69C")
LIGHT = colors.HexColor("#EAF7F5")
PALE = colors.HexColor("#F3F7FA")
LINE = colors.HexColor("#DCE5EB")
WHITE = colors.white

body_style = ParagraphStyle("body", fontName="Deng", fontSize=10.3, leading=17.3,
                            textColor=INK, spaceAfter=0)
small_style = ParagraphStyle("small", parent=body_style, fontSize=9.2, leading=15)
tip_style = ParagraphStyle("tip", parent=body_style, fontSize=9.6, leading=16)

c = canvas.Canvas(str(OUT), pagesize=A4, pageCompression=1)
c.setTitle("Clipline 1.0.5 - 产品介绍与使用手册")
c.setAuthor("Clipline")
c.setSubject("Windows Clipline 产品介绍、安装、操作与常见问题")
page_no = 0


def para(text, x, top, width, style=body_style):
    p = Paragraph(text, style)
    _, height = p.wrap(width, 1000)
    p.drawOn(c, x, top - height)
    return top - height


def label(text, x, y, size=10, color=INK, bold=False):
    c.setFont("DengBold" if bold else "Deng", size)
    c.setFillColor(color)
    c.drawString(x, y, text)


def page(title, subtitle):
    global page_no
    page_no += 1
    c.setFillColor(WHITE)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFillColor(TEAL)
    c.rect(0, H - 9, W, 9, fill=1, stroke=0)
    label("Clipline  /  使用手册", 48, H - 35, 9, MUTED)
    label(f"{page_no:02d}", W - 70, H - 35, 9, MUTED)
    label(title, 48, H - 85, 24, NAVY, True)
    para(subtitle, 48, H - 101, W - 96, small_style)
    c.setStrokeColor(LINE)
    c.line(48, 42, W - 48, 42)
    label("Clipline 1.0.5  |  Windows 10 / 11", 48, 26, 8, MUTED)
    label(f"{page_no}", W - 55, 26, 8, MUTED)
    return H - 143


def section(text, y):
    c.setFillColor(TEAL)
    c.roundRect(48, y - 15, 4, 18, 2, fill=1, stroke=0)
    label(text, 62, y - 11, 14, NAVY, True)
    return y - 29


def text(text, y, gap=12, style=body_style, x=48, width=W - 96):
    return para(text, x, y, width, style) - gap


def bullet(text_value, y, gap=8):
    c.setFillColor(TEAL)
    c.circle(55, y - 7, 2.3, fill=1, stroke=0)
    return para(text_value, 68, y, W - 116, body_style) - gap


def note(title, content, y, height=66):
    c.setFillColor(LIGHT)
    c.roundRect(48, y - height, W - 96, height, 11, fill=1, stroke=0)
    label(title, 64, y - 22, 10.3, colors.HexColor("#117D76"), True)
    para(content, 64, y - 31, W - 128, tip_style)
    return y - height - 17


def step(number, title, content, y):
    c.setFillColor(TEAL)
    c.circle(63, y - 11, 15, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("DengBold", 12)
    c.drawCentredString(63, y - 15, str(number))
    label(title, 90, y - 4, 11.5, NAVY, True)
    end = para(content, 90, y - 12, W - 140, body_style)
    return end - 19


def finish():
    c.showPage()


# Cover
page_no += 1
c.setFillColor(NAVY)
c.rect(0, 0, W, H, fill=1, stroke=0)
c.setFillColor(colors.HexColor("#234A65"))
c.circle(W + 80, H - 90, 250, fill=1, stroke=0)
c.setFillColor(colors.HexColor("#1D3D58"))
c.circle(-80, 85, 240, fill=1, stroke=0)
c.setStrokeColor(colors.HexColor("#80D4CD"))
c.setLineWidth(3)
path = c.beginPath()
path.moveTo(64, 525)
path.curveTo(220, 480, 380, 480, 532, 525)
c.drawPath(path)
for x, y, tilt in [(145, 500, -4), (285, 489, 2), (425, 503, -3)]:
    c.saveState()
    c.translate(x, y)
    c.rotate(tilt)
    c.setFillColor(colors.HexColor("#D6E9EF"))
    c.roundRect(-2, -20, 4, 24, 2, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.roundRect(-48, -123, 96, 101, 8, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#D5F2EC"))
    c.roundRect(-39, -113, 78, 80, 4, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#A6D7D3"))
    c.circle(0, -72, 21, fill=1, stroke=0)
    c.restoreState()
c.setFillColor(TEAL)
c.roundRect(48, 708, 128, 27, 13, fill=1, stroke=0)
label("WINDOWS 桌面工具", 65, 716, 9, WHITE, True)
label("Clipline", 48, 636, 36, WHITE, True)
label("产品介绍与使用手册", 50, 598, 17, colors.HexColor("#CBE7E5"))
para("把刚截下或复制的图片，暂时挂在桌面顶部。需要时点一下复制、拖出去分享，或者打开画图继续编辑。", 48, 563, W - 96,
     ParagraphStyle("cover", parent=body_style, fontSize=12, leading=21, textColor=WHITE))
c.setFillColor(colors.HexColor("#31536B"))
c.roundRect(48, 145, W - 96, 89, 12, fill=1, stroke=0)
para("<b>一眼看懂</b><br/>最多保存 10 张图片  ·  同时展示 5 张  ·  系统托盘常驻<br/>支持截图、复制图片、复制本地图片文件  ·  无需另装 Python", 67, 213, W - 134,
     ParagraphStyle("coverInfo", parent=body_style, fontSize=10.5, leading=22, textColor=WHITE))
label("版本 1.0.5     2026 年 10 月", 48, 93, 10, colors.HexColor("#C9DDE4"))
label("适用于 Windows 10 1809 及以上 / Windows 11 的 x64 电脑", 48, 70, 9.5, colors.HexColor("#C9DDE4"))
finish()


# Page 2
y = page("认识 Clipline", "一个轻量的本地图片暂存工具，让截图在需要时随手可取。")
y = section("它能做什么", y)
y = text("Clipline 会在开启功能后监听剪贴板中的图片。用 Windows 截图、从应用里复制图片，或在资源管理器和桌面复制常见图片文件时，它会把图片副本挂在屏幕上方的绳子上。您可以在不同软件之间快速重复使用这些图片。", y)
y = bullet("<b>临时收纳：</b>最近的图片最多保留 10 张；绳上每次显示最多 5 张，其余可翻页查看。", y)
y = bullet("<b>快速复用：</b>单击图片即可重新复制到剪贴板，随后在聊天、文档或绘图软件里粘贴。", y)
y = bullet("<b>继续处理：</b>长按可交给 Windows 画图编辑；拖动可向支持文件拖放的应用或文件夹分享副本。", y)
y = bullet("<b>本地保存：</b>图片副本保存在本机，程序不会主动上传。退出后图片和开关状态仍会保留。", y)
y = section("适合的使用场景", y - 3)
y = text("例如整理资料时连续截取多处内容，写文档时反复插入同一张图，或聊天时需要从几张截图中挑选一张发送。晾衣绳收起后仍驻留系统托盘，您可以随时再展开。", y)
y = note("先了解两个概念", "“开启功能”决定是否接收新的图片；“显示/收起”只控制桌面上的绳子是否可见。收起绳子不会清空图片。", y, 76)
y = section("版本范围", y)
y = text("本文对应 1.0.5 安装包。全局快捷键、复制本地图片文件、“已复制”提示，以及画图交互修复均已包含在此版本。", y)
print("page2 end", y)
finish()


# Page 3
y = page("安装与首次使用", "从安装包开始，约一分钟完成第一次挂图。")
y = section("安装前确认", y)
y = bullet("电脑运行 Windows 10 1809 或更新版本、Windows 11，处理器为 Intel/AMD x64。", y)
y = bullet("安装包已带运行所需组件，不需要单独安装 Python。长按编辑功能需要系统已安装 Windows 画图。", y)
y = section("安装步骤", y)
y = step(1, "运行安装包", "双击“Clipline-安装包.exe”，按安装向导完成安装。此安装包没有代码签名，系统可能显示“未知发布者”；请确认文件来自可信来源。", y)
y = step(2, "启动程序", "在开始菜单打开“Clipline”。程序会显示桌面绳子，并在系统托盘放置图标。首次使用时，接收图片的功能默认关闭。", y)
y = step(3, "开启功能", "点击窗口里的“开启 Clipline 功能”，或右键托盘图标勾选同名选项。此后新复制的图片会自动挂上去。", y)
y = step(4, "试挂一张图片", "按 Win + Shift + S 完成一次区域截图。截图进入剪贴板后，图片会出现在绳上。也可以在图片文件上按 Ctrl + C。", y)
y = note("如果已经安装旧版", "使用同名安装包按向导安装即可。程序数据保存在用户目录，卸载或更新程序不会自动清空已保存图片。", y, 75)
print("page3 end", y)
finish()


# Page 4
y = page("让图片挂上去", "功能开启后，只要图片进入剪贴板，程序就会尝试保存一份副本。")
y = section("三种常用输入方式", y)
y = step(1, "Windows 截图", "按 Win + Shift + S，选择截取区域并完成截图。只要图片被放进剪贴板，程序就会自动接收。", y)
y = step(2, "在应用中复制图片", "在浏览器、绘图软件等应用中使用“复制图片”或 Ctrl + C。应用需要把真实图片数据放进剪贴板；只复制网页链接不会挂图。", y)
y = step(3, "复制本地图片文件", "在资源管理器或桌面选中常见图片文件，按 Ctrl + C。程序读取可识别的本地图片文件并保存副本；复制普通文件不会挂图。", y)
y = section("展开与收起", y)
y = bullet("<b>快捷键：</b>按 Win + Alt + L 或 Ctrl + Alt + Shift + L，可从其他程序展开晾衣绳。若某组按键被占用，托盘会提示；另一组仍可尝试。", y)
y = bullet("<b>托盘图标：</b>单击可显示或收起；右键可选择“显示晾衣绳”、切换功能开关或退出程序。", y)
y = bullet("<b>屏幕顶部：</b>功能开启且绳子收起时，把鼠标移到屏幕上方的中间区域，静止约 0.6 秒即可展开。", y)
y = bullet("<b>自动收起：</b>没有图片点击、悬停或翻页等操作约 10 秒后，晾衣绳会自动收起；也可以点中间的向上箭头。", y)
y = note("看不到新图片时", "先确认功能已开启，再确认源应用确实把图片放入剪贴板。有些截图工具只保存文件，不会自动触发挂图；可到文件夹里复制那张图片文件。", y, 75)
print("page4 end", y)
finish()


# Page 5
y = page("认识绳上的操作", "所有常用操作都在图片、左右箭头和猫猫附近。")
y = section("操作速查", y)
items = [
    ("单击图片", "将这张图片复制到剪贴板；图片上会短暂显示“已复制”，然后可以在其他程序粘贴。"),
    ("长按图片", "按住约 0.65 秒，松开鼠标后在 Windows 画图中打开这份副本。保存修改后，晾衣绳会刷新预览。"),
    ("拖动图片", "把图片副本拖到支持文件拖放的应用或文件夹。是否接收取决于目标应用。"),
    ("删除单张图片", "将鼠标移到图片上，单击右上角的×，即可移除这一张程序副本；原始文件不受影响。"),
    ("左右箭头", "查看其余图片，通常每次移动两张；最后不足两张时移动剩余部分。"),
    ("向上箭头", "手动收起绳子；程序继续在系统托盘运行，图片仍保留。"),
    ("退出", "单击向上箭头左侧的×，在“退出应用”确认框中选“是”；程序停止运行，已保存的图片保留。"),
    ("猫猫", "悬停时会抬头并显示图片总数；单击后在清空确认框中选择“是”，删除全部程序副本。"),
]
for title, desc in items:
    c.setFillColor(PALE)
    c.roundRect(48, y - 44, W - 96, 44, 8, fill=1, stroke=0)
    label(title, 62, y - 20, 10.4, NAVY, True)
    para(desc, 157, y - 9, W - 220, small_style)
    y -= 52
y -= 4
y = note("清空时会发生什么", "确认框显示“清空晾衣绳上的图片（共…张）”。选择“是”将删除程序保存的全部图片副本，包括当前未显示的图片；原始文件不受影响。", y, 79)
y = text("双击图片不会执行“打开”；若想编辑，请使用长按。绳上最多同时显示 5 张，但最多可保存 10 张，左右箭头用于查看未显示的图片。", y)
print("page5 end", y)
finish()


# Page 6
y = page("管理图片与隐私", "了解图片保存在哪里，以及关闭、退出和卸载的区别。")
y = section("本地数据位置", y)
y = text("程序会将接收的图片保存为 PNG 副本，并在同一用户目录记录顺序与功能开关状态：", y, 8)
c.setFillColor(PALE)
c.roundRect(48, y - 42, W - 96, 42, 8, fill=1, stroke=0)
label(r"%LOCALAPPDATA%\ScreenshotClothesline", 64, y - 26, 11, NAVY, True)
y -= 58
y = text("Clipline 沿用旧版数据目录，以保留已有图片与设置。", y, 8, small_style)
y = bullet("复制本地图片文件时，程序读取原文件并保存一份副本；取下、清空或超出 10 张上限时，不会删除原文件。", y)
y = bullet("新图会排在前面。超过 10 张时，最旧的程序副本会自动移除。退出后，剩余图片和开关状态会在下次启动时恢复。", y)
y = bullet("程序在本机运行，不会主动把图片上传到网络。若将副本拖入其他应用，后续处理遵循目标应用的规则。", y)
y = section("关闭、退出、卸载", y)
y = bullet("<b>收起：</b>只隐藏桌面绳子；程序仍在托盘运行，仍可继续接收图片。", y)
y = bullet("<b>关闭功能：</b>不再接收新图片；已有图片仍保留，重新开启后可继续使用。", y)
y = bullet("<b>退出：</b>单击绳上的 × 按钮并确认，或从托盘右键菜单选“退出”；程序停止运行，但保存的图片仍在。", y)
y = bullet("<b>卸载：</b>在 Windows“已安装的应用”中卸载“Clipline”。用户目录下的图片和设置会保留。", y)
y = note("需要彻底清理时", "先检查是否还有想保留的截图，再手动删除上面的数据目录。删除后无法从程序副本中恢复图片；如果原文件仍在，原文件不受影响。", y, 78)
print("page6 end", y)
finish()


# Page 7
y = page("常见问题与适用范围", "遇到问题时，先按下面的顺序检查。")
y = section("常见问题", y)
qa = [
    ("截图后没有挂图？", "确认功能已开启、程序仍在托盘运行，再检查截图是否进入剪贴板。有些截图工具仅保存文件；可在资源管理器中复制该文件。"),
    ("快捷键没有反应？", "可能被其他程序占用。查看托盘提示，试用另一组快捷键，或直接单击托盘图标显示。"),
    ("长按无法打开画图？", "确认 Windows 画图已安装并可单独打开。若系统找不到画图，程序会显示提示。"),
    ("找不到晾衣绳？", "先看系统托盘的隐藏图标区域；单击图标，或右键选择“显示晾衣绳”。功能关闭时也可从窗口或托盘重新开启。"),
    ("为什么无法添加第 11 张？", "程序最多保存 10 张。新图加入后，最旧的程序副本会自动移除；请先另存重要图片。"),
]
for q, a in qa:
    label(q, 48, y - 8, 10.5, NAVY, True)
    y = para(a, 48, y - 15, W - 96, small_style) - 14
y = section("系统适用性", y - 2)
y = text("安装程序面向 Windows 10 1809 及以上、Windows 11 的 Intel/AMD x64 电脑。当前安装包在 Windows 11 x64 完成构建；Windows 10 各版本尚需实机验证。32 位 Windows 和更早版本不在安装范围内，Windows ARM 未提供原生安装包。", y, 8, small_style)
y = text("安装包未做代码签名，因此系统可能显示“未知发布者”。请通过可信渠道分享安装包，并可对照交付文件中的 SHA-256 校验值。", y, 8, small_style)
print("page7 end", y)
finish()

c.save()
print(OUT)
