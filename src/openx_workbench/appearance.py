"""Shared light/dark colors; system mode follows CSS prefers-color-scheme live."""
import re


DARK = {}
for colors, target in (
    ("#edf1f5 #edf2f5", "#101922"),
    ("#fbfcfe #fdfefe", "#182430"),
    ("#f3f6f9 #f8fafc #f1f4f7 #eef2f5 #e5e9ee #e7edf1 #edf4fb", "#202f3d"),
    ("#10243a #0b2638 #24384a #294655 #31475b #334b5d #34465a #34485d #18364b", "#e4edf5"),
    ("#3e5267 #405765 #41566c #496272 #4e6270 #52687b #5b6570 #29495f #526b7e", "#c0d0de"),
    ("#68798b #7b8da0 #9dafbb #a3afba", "#a7bbcd"),
    ("#0668c5 #075fae #0868bd #275a7a #174e76", "#80c5ff"),
    ("#0876d9 #1687e8", "#238de5"),
    ("#e9f4ff #eaf6ff #eef7fd #dff1ff #e1f0fd #c8e5ff #9fcef5 #e6eef4 #e9f0f5", "#203c53"),
    ("#128044 #146b32", "#7bd5a0"),
    ("#e9f8ee #eaf8ef #c9f0bf", "#183b2c"),
    ("#a36d00 #79560f", "#f0cc78"),
    ("#fff8df #ffe3a1", "#3b321e"),
    ("#bd3e35", "#ffaaa3"),
    ("#fff1f0", "#402a2d"),
    ("#b5c0cb #aebdca #d8e4ee #d4dfe8", "#405669"),
    ("#8dd1a5", "#37704d"), ("#e5c567", "#7b6736"),
    ("#e5aaa6", "#88534f"), ("#9bc3df", "#456981"),
):
    for color in colors.split():
        DARK[color] = target


def theme_colors(css):
    """Convert only CSS colors; never recolor PDF images or simulation frames."""
    css = re.sub(r"#[0-9a-fA-F]{3,8}\b", lambda match:
                 f"light-dark({match[0]},{DARK[match[0].lower()]})"
                 if match[0].lower() in DARK else match[0], css)
    css = css.replace("rgba(18,42,66,.12)", "light-dark(rgba(18,42,66,.12),#344a5d)")
    css = css.replace("rgba(18,42,66,.22)", "light-dark(rgba(18,42,66,.22),#496174)")
    css = css.replace("rgba(18,42,66,.08)", "light-dark(rgba(18,42,66,.08),#304353)")
    return css


def appearance_css(mode):
    mode = mode if mode in {"light", "dark", "system"} else "system"
    scheme = "light dark" if mode == "system" else mode
    return f'html{{color-scheme:{scheme}!important}}body,.stApp,[data-testid="stSidebar"]{{color-scheme:inherit!important}}' + """
body{--control:light-dark(#ffffff,#223240);--control-border:light-dark(#cbd8e2,#486071);--muted:light-dark(#526b7e,#a7bbcd);--nav-bg:light-dark(#e8eef4,#143149);--nav-ink:light-dark(#24384a,#e8f0f6);--nav-muted:light-dark(#526b7e,#bdd0de);--nav-border:light-dark(#c5d3df,#355167);--nav-hover:light-dark(#dae5ee,#213f57);--nav-active:light-dark(#d1e6f6,#2b506a);--nav-active-ink:light-dark(#0b4d78,#ffffff);--nav-accent:light-dark(#0876a5,#63cee7)}
[data-testid="stSidebar"]{--ink-1:var(--nav-ink);--ink-2:var(--nav-muted);--muted:var(--nav-muted)}
[data-testid="stMarkdownContainer"],[data-testid="stWidgetLabel"],[data-testid="stMetricLabel"]{color:var(--ink-1)}
[data-testid="stText"],[data-testid="stText"] span{color:var(--ink-1)!important;white-space:pre-wrap;overflow-wrap:anywhere}
[data-testid="stCaptionContainer"],[data-testid="stCaptionContainer"] p{color:var(--muted)!important;opacity:1!important;overflow-wrap:anywhere}
.stTextInput input,.stTextArea textarea,[role="combobox"],[data-testid="stNumberInput"] input{background:var(--control)!important;color:var(--ink-1)!important;border-color:var(--control-border)!important;caret-color:var(--accent)}
input::placeholder,textarea::placeholder{color:var(--muted)!important;opacity:1}
[data-testid="stTextInputRootElement"],[data-testid="stTextArea"]>div{background:var(--control)!important;border-color:var(--control-border)!important}
[data-testid="stNumberInputContainer"],.stMultiSelect .react-aria-ComboBox>[role="group"]{background:var(--control)!important;border-color:var(--control-border)!important;color:var(--ink-1)!important}
[data-testid="stNumberInputContainer"] button,.stMultiSelect .react-aria-ComboBox>button{background:var(--control)!important;color:var(--ink-1)!important}
[data-testid="stNumberInputContainer"] button:disabled{color:var(--muted)!important}
[data-testid="InputInstructions"],[data-testid="InputInstructions"] span{color:var(--muted)!important}
[data-testid="stSelectbox"] button{background:var(--control)!important;color:var(--ink-1)!important}
[data-testid="stSidebar"] [role="combobox"],[data-testid="stSidebar"] [data-testid="stSelectbox"] button{background:var(--nav-hover)!important;color:var(--nav-ink)!important}
[data-testid^="stBaseButton-"]{background:var(--control);color:var(--ink-1);border-color:var(--control-border)}
button[kind^="primary"]{background:var(--accent)!important;color:#fff!important;border-color:var(--accent)!important}
button[kind^="primary"] [data-testid="stMarkdownContainer"]{color:#fff!important}
button[kind]:hover:not(:disabled){border-color:var(--accent);color:var(--accent)}
button[kind^="primary"]:hover:not(:disabled){color:#fff}
button:focus-visible{outline:2px solid var(--accent)!important;outline-offset:2px}
button[kind]:disabled{background:var(--panel-2)!important;color:var(--muted)!important;border-color:var(--control-border)!important;opacity:1}
button[kind]:disabled [data-testid="stMarkdownContainer"]{color:inherit!important}
[role="dialog"],[role="listbox"],[data-testid="stPopoverBody"],[data-testid="stPopoverContent"],[data-testid="stSelectboxVirtualDropdown"]{background:var(--bg)!important;color:var(--ink-1)!important;border-color:var(--control-border)!important}
[role="option"]{color:var(--ink-1)!important;background:var(--bg)}
[role="option"]:hover,[role="option"][aria-selected="true"]{background:var(--panel-2)!important}
[data-testid="stExpander"]{background:transparent!important;border-radius:8px;border-color:var(--control-border)!important}
[data-testid="stExpander"] details{border-radius:8px!important;overflow:hidden;background:var(--bg);border-color:var(--control-border)!important}
[data-testid="stExpander"] details,[data-testid="stExpander"] summary{color:var(--ink-1)}
[data-testid="stExpander"] summary,[data-testid="stExpander"] summary:hover,[data-testid="stExpander"] summary:focus{background:var(--panel-2)!important;color:var(--ink-1)!important}
[data-testid="stFileUploaderDropzone"],[data-testid="stCode"],pre{background:var(--panel-2)!important;color:var(--ink-1)!important;border-color:var(--control-border)!important}
[data-testid="stFileUploaderDropzone"] small,[data-testid="stFileUploaderDropzone"] span{color:var(--ink-2)}
[data-testid="stFileUploader"] [data-testid="stMarkdownContainer"]{color:inherit}
[data-testid="stTooltipIcon"] button{color:var(--muted)!important}
[data-testid="stTooltipContent"]{background:var(--bg)!important;color:var(--ink-1)!important;border-color:var(--control-border)!important}
[data-testid="stCode"] button{background:var(--control)!important;color:var(--ink-1)!important}
[data-testid="stCode"] code,[data-testid="stCode"] span{color:inherit!important}
[data-testid="stAlert"]{background:var(--panel-2)!important;color:var(--ink-1)!important}
[data-testid="stTable"]{background:var(--bg);color:var(--ink-1)}
[data-testid="stTable"] td,[data-testid="stTable"] th{border-color:var(--control-border)!important}
[data-testid="stProgressBarTrack"]{background:var(--control-border)!important}
.ow-section-title span[style]{color:var(--ink-1)!important}
.st-key-workspace_header [data-testid="stMarkdownContainer"]{color:inherit}
.st-key-workspace_nav [data-testid="stMarkdownContainer"]{color:inherit}
.st-key-workspace_nav button[kind="primary"] [data-testid="stMarkdownContainer"]{color:var(--nav-active-ink)!important}
[data-testid="stIconMaterial"]{font-size:19px;flex-shrink:0}
[role="dialog"] button:not([kind^="primary"]){color:var(--ink-1)!important}
::selection{background:var(--accent);color:#fff}
[data-testid="stMain"]{scrollbar-color:var(--control-border) var(--bg)}
"""
