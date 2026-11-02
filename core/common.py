"""Общие функции: настройки, пути, названия классов, шрифты для графиков."""
import copy
import json
from pathlib import Path

# Сертификаты Windows для скачивания моделей (иначе антивирус/прокси даёт ошибку SSL)
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from PIL import ImageFont  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent      # папка ekoagyn/
CONFIG_PATH = ROOT / "config.json"

# Порядок классов YOLO, которые мы считаем
CLASS_ORDER = ["car", "bus", "truck", "motorcycle"]
DIR_KZ = {1: "1-бағыт", 2: "2-бағыт"}


def load_config(path=CONFIG_PATH):
    """Читает config.json."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg, path=CONFIG_PATH):
    """Сохраняет настройки обратно в config.json."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def deep_copy(cfg):
    return copy.deepcopy(cfg)


def class_kz(cfg, c):
    """Казахское название класса YOLO."""
    return cfg["classes"].get(c, {}).get("kz", c)


def results_root(cfg):
    p = ROOT / cfg["paths"]["results_dir"]
    p.mkdir(parents=True, exist_ok=True)
    return p


def results_dir(cfg, video_name):
    """Папка результатов: results/<имя_видео>/"""
    p = results_root(cfg) / Path(video_name).stem
    p.mkdir(parents=True, exist_ok=True)
    return p


def processed_videos(cfg):
    """Список уже обработанных видео (есть summary.json)."""
    root = results_root(cfg)
    return sorted(p.name for p in root.iterdir() if (p / "summary.json").exists())


def video_dirs(cfg):
    """Папки, где ищем видео (ekoagyn/videos и ../videos проекта TCounter)."""
    out = []
    for d in cfg["paths"]["video_dirs"]:
        p = (ROOT / d).resolve()
        if p.exists():
            out.append(p)
    return out


def list_videos(cfg):
    vids = []
    for d in video_dirs(cfg):
        for f in sorted(d.iterdir()):
            if f.suffix.lower() in (".mp4", ".mov", ".avi", ".mkv"):
                vids.append(f)
    return vids


# ---------- Шрифт с казахскими буквами ----------
# DejaVu Sans идёт вместе с matplotlib и содержит ә, ғ, қ, ң, ө, ұ, ү, һ, і
FONT_DIR = Path(matplotlib.get_data_path()) / "fonts" / "ttf"


def font(size, bold=True):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(str(FONT_DIR / name), size)
    except OSError:
        return ImageFont.load_default()


# ---------- Оформление графиков ----------
# Единая палитра сайта: глубокий зелёный акцент + спокойные дополнительные цвета
GREEN, AMBER, BLUE, PLUM, GREY = "#167D61", "#B7791F", "#3A6EA5", "#8A5A9E", "#8A9993"
PALETTE = [GREEN, AMBER, BLUE, PLUM, "#4FA88A", GREY, "#C2553F", "#2E8C9E"]
CLASS_COLORS = {"car": GREEN, "bus": AMBER, "truck": BLUE, "motorcycle": PLUM}
TEXT, MUTED, BORDER = "#182522", "#66756F", "#E2E9E5"

# Шрифт графиков: PT Sans (assets/fonts, есть все казахские буквы), запасной — DejaVu Sans
from matplotlib import font_manager  # noqa: E402

CHART_FONT = "DejaVu Sans"
for _f in (ROOT / "assets" / "fonts").glob("*.ttf"):
    font_manager.fontManager.addfont(str(_f))
    CHART_FONT = "PT Sans"

plt.rcParams.update({
    "font.family": [CHART_FONT, "DejaVu Sans"],
    "font.size": 11,
    "text.color": TEXT,
    "axes.labelcolor": TEXT,
    "axes.edgecolor": "#B9C4BF",
    "axes.titleweight": "bold",
    "axes.titlesize": 12.5,
    "axes.titlelocation": "left",
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "axes.axisbelow": True,          # сетка под столбцами, а не поверх
    "grid.color": BORDER,
    "grid.alpha": 1.0,
    "legend.frameon": False,
    "figure.dpi": 110,
    "savefig.dpi": 300,          # высокое качество для стенда
    "savefig.bbox": "tight",
})


def save_fig(fig, path):
    """Сохраняет график в PNG 300 dpi."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=300, facecolor="white")
    return path
