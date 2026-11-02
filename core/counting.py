"""Подсчёт машин по видео: YOLO + ByteTrack, пересечение линии.

Основа — count.py из проекта TCounter (геометрия линии, голосование класса,
кадр для стенда), переделано в функцию для сайта:
  - прогресс передаётся через callback,
  - для каждой посчитанной машины сохраняется лучшая (самая крупная) вырезка,
  - номера и лица размываются ДО сохранения любого кадра или вырезки.

Запуск из командной строки (для проверки):
  python -m core.counting ../videos/kokshetau_01.mov --line 100 600 1800 600
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw

from core.common import CLASS_ORDER, ROOT, class_kz, font, load_config, results_dir
from core.privacy import blur_crop, blur_frame

PERSON_CLASS = 0

# Цвет рамки для каждого класса (B, G, R)
COLORS = {"car": (214, 120, 42), "bus": (52, 104, 235), "truck": (182, 89, 155),
          "motorcycle": (91, 158, 46), "person": (200, 200, 200)}
SHORT_KZ = {"car": "жеңіл", "bus": "автобус", "truck": "жүк", "motorcycle": "мото", "person": "адам"}


# ---------- Геометрия линии (из TCounter) ----------

def side_of_line(p, a, b):
    """С какой стороны линии AB лежит точка P (векторное произведение)."""
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])


def anchor(box):
    """Точка, по которой считаем пересечение: середина НИЖНЕЙ стороны рамки (где колёса касаются дороги).
    Раньше брали центр рамки — у высоких автобусов и грузовиков рядом с камерой центр уже выше
    линии, когда они появляются в кадре, и такие машины не засчитывались."""
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2, y2)


def signed_dist(p, a, b):
    """Расстояние (в пикселях) от точки до линии AB со знаком стороны."""
    return side_of_line(p, a, b) / max(1e-6, ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5)


def along(p, a, b):
    """Положение проекции точки на отрезок AB: 0 — у A, 1 — у B."""
    vx, vy = b[0] - a[0], b[1] - a[1]
    return ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / max(1e-6, vx * vx + vy * vy)


def full_speed():
    """Windows 11 переводит фоновые/скрытые процессы в «режим эффективности» (EcoQoS) —
    обработка шла почти в 2 раза медленнее. Отключаем это для нашего процесса и повышаем приоритет."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        class PowerThrottling(ctypes.Structure):
            _fields_ = [("Version", wintypes.ULONG), ("ControlMask", wintypes.ULONG),
                        ("StateMask", wintypes.ULONG)]

        k32 = ctypes.windll.kernel32
        h = k32.GetCurrentProcess()
        # ProcessPowerThrottling = 4; EXECUTION_SPEED = 1; StateMask = 0 → «не экономить»
        st = PowerThrottling(1, 1, 0)
        k32.SetProcessInformation(h, 4, ctypes.byref(st), ctypes.sizeof(st))
        k32.SetPriorityClass(h, 0x00008000)      # ABOVE_NORMAL_PRIORITY_CLASS
    except Exception:
        pass


def crossing_step(tr, box, a, b, margin, H):
    """Обновляет состояние трека и возвращает True, если машина ТОЛЬКО ЧТО пересекла линию.

    Правила (чтобы считать честно и не давать ложных срабатываний):
    1. Точка — середина нижней стороны рамки (колёса), а не центр рамки.
    2. Мёртвая зона margin у линии: дрожание рамки на линии не считается.
    3. Кадр, где рамка резко стала ниже (низ машины закрыла другая машина), пропускается.
    4. Новая сторона должна держаться 2 кадра подряд.
    5. Точка пересечения лежит в пределах отрезка AB.
    """
    x1, y1, x2, y2 = box
    h = y2 - y1
    hs = tr["heights"]
    occluded = len(hs) >= 3 and h < 0.75 * float(np.median(hs[-8:])) and y2 < H - 3
    hs.append(h)
    if occluded:
        return False
    p = anchor(box)
    last = tr.get("last_pt")
    tr["last_pt"] = p
    dist = signed_dist(p, a, b)
    side = 1 if dist > 0 else -1
    # 6. «Скачок» точки больше 12% высоты кадра за один шаг — трекер перепутал машины
    #    (ID перешёл на другую машину). Это не пересечение: просто начинаем отсчёт заново.
    if last is not None and ((p[0] - last[0]) ** 2 + (p[1] - last[1]) ** 2) ** 0.5 > 0.12 * H:
        tr["side"], tr["side_pt"], tr["pending"] = (side if abs(dist) >= margin else None), p, 0
        return False
    if abs(dist) < margin:
        return False
    if tr["side"] is None:                       # первая надёжная сторона
        tr["side"], tr["side_pt"] = side, p
        return False
    if side == tr["side"]:
        tr["side_pt"], tr["pending"] = p, 0      # запоминаем последнюю точку на «старой» стороне
        return False
    tr["pending"] += 1
    if tr["pending"] < 2:                        # ждём подтверждения вторым кадром
        return False
    # Подтверждено: проверяем, что машина пересекла линию в пределах отрезка AB
    mid = ((p[0] + tr["side_pt"][0]) / 2, (p[1] + tr["side_pt"][1]) / 2)
    tr["side"], tr["side_pt"], tr["pending"] = side, p, 0
    return -0.05 <= along(mid, a, b) <= 1.05


def pick_device(name):
    """Видеокарта, если есть, иначе процессор."""
    if name != "auto":
        return name
    import torch
    if torch.cuda.is_available():
        return 0
    return "cpu"


# ---------- Работа с видео ----------

def video_info(path):
    """Длительность, fps и размер кадра."""
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    ok, frame = cap.read()
    cap.release()
    h, w = frame.shape[:2] if ok else (0, 0)
    return {"fps": fps, "frames": n, "duration_s": n / fps if fps else 0, "width": w, "height": h}


def read_frame(path, t_sec=0.0):
    """Кадр видео в момент t_sec (BGR)."""
    cap = cv2.VideoCapture(str(path))
    if t_sec > 0:
        cap.set(cv2.CAP_PROP_POS_MSEC, t_sec * 1000)
    ok, frame = cap.read()
    cap.release()
    return frame if ok else None


def ffmpeg_exe():
    """ffmpeg: системный или из пакета imageio-ffmpeg."""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def to_h264(src, dst):
    """Перекодируем видео в H.264, чтобы оно открывалось в браузере."""
    exe = ffmpeg_exe()
    if exe:
        r = subprocess.run([exe, "-v", "error", "-y", "-i", str(src), "-c:v", "libx264",
                            "-pix_fmt", "yuv420p", "-crf", "26", "-movflags", "+faststart", str(dst)])
        if r.returncode == 0:
            Path(src).unlink()
            return
    Path(src).replace(dst)


# ---------- Рисование ----------

def draw_overlay(frame, dets, line, scale, counts=None, dir_names=None, short=False, cfg=None):
    """Рамки, подписи, линия подсчёта и табличка со счётчиком."""
    a = tuple(int(v * scale) for v in line[0])
    b = tuple(int(v * scale) for v in line[1])
    th = max(2, int(frame.shape[1] / 500))
    cv2.line(frame, a, b, (0, 255, 255), th + 1)
    # Стрелка показывает «1-бағыт»
    mx, my = (a[0] + b[0]) // 2, (a[1] + b[1]) // 2
    nx, ny = -(b[1] - a[1]), (b[0] - a[0])
    n = max(1.0, (nx ** 2 + ny ** 2) ** 0.5)
    L = frame.shape[1] * 0.04
    cv2.arrowedLine(frame, (mx, my), (int(mx + nx / n * L), int(my + ny / n * L)),
                    (0, 255, 255), th, tipLength=0.35)
    for d in dets:
        x1, y1, x2, y2 = [int(v * scale) for v in d["box"]]
        cv2.rectangle(frame, (x1, y1), (x2, y2), COLORS[d["cls"]], th)

    # Казахский текст рисуем через PIL
    img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img)
    fs = max(12, int(frame.shape[1] / 95))
    f_small, f_big = font(fs), font(int(fs * 1.1))
    for d in dets:
        if d["cls"] == "person":
            continue
        x1, y1 = int(d["box"][0] * scale), int(d["box"][1] * scale)
        name = SHORT_KZ[d["cls"]]
        # Номер показываем только у уже посчитанных машин: «№ 12» = 12-я машина, пересёкшая линию.
        # Внутренние ID трекера (#1005 и т.п.) не показываем — они ничего не значат для зрителя.
        text = f"{name} № {d['n']}" if not short and d.get("n") else name
        tw = draw.textlength(text, font=f_small)
        c = COLORS[d["cls"]][::-1]
        draw.rectangle([x1, y1 - fs - 4, x1 + tw + 6, y1], fill=c)
        draw.text((x1 + 3, y1 - fs - 3), text, font=f_small, fill=(255, 255, 255))

    if counts is not None:
        lines = ["EcoAgyn — көлік саны"]
        for c in CLASS_ORDER:
            lines.append(f"{class_kz(cfg, c)}: {counts[c][1]} / {counts[c][2]}")
        t1 = sum(counts[c][1] for c in CLASS_ORDER)
        t2 = sum(counts[c][2] for c in CLASS_ORDER)
        lines.append(f"БАРЛЫҒЫ: {t1} / {t2} (= {t1 + t2})")
        lines.append(f"({dir_names[0]} / {dir_names[1]})")
        h = int(len(lines) * fs * 1.45) + 12
        w = int(max(draw.textlength(s, font=f_big) for s in lines)) + 20
        draw.rectangle([8, 8, 8 + w, 8 + h], fill=(0, 0, 0))
        for i, s in enumerate(lines):
            draw.text((18, 14 + i * fs * 1.45), s, font=f_big, fill=(255, 255, 255))
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def make_stand_frame(frame, dets, line, cfg):
    """Кадр для стенда: сначала размываем номера и лица, потом рисуем рамки."""
    img = blur_frame(frame, dets, cfg["privacy"])
    clear = [d for d in dets if d["conf"] >= 0.4]
    return draw_overlay(img, clear, line, 1.0, short=True, cfg=cfg)


# ---------- Главная функция ----------

def run_counting(video_path, line, cfg, start_sec=0.0, end_sec=None, dir_names=None,
                 progress=None, out_name=None):
    """Считает машины. line = [[x1, y1], [x2, y2]] в пикселях исходного кадра.
    progress(доля 0..1, текст) — для прогресс-бара.
    Для каждой машины сохраняется размытая вырезка (нужна для проверки точности).
    Возвращает словарь summary и сохраняет все файлы в results/<имя_видео>/."""
    from ultralytics import YOLO
    import torch
    torch.backends.cudnn.benchmark = True
    full_speed()

    det = cfg["detection"]
    video_path = Path(video_path)
    out = results_dir(cfg, out_name or video_path.name)
    crops_dir = out / "crops"
    if crops_dir.exists():
        shutil.rmtree(crops_dir)
    crops_dir.mkdir()
    dir_names = dir_names or ["1-бағыт", "2-бағыт"]
    a, b = line
    step = max(1, int(det.get("frame_step", 1)))
    device = pick_device(det.get("device", "auto"))
    coco = {v["coco_id"]: k for k, v in cfg["classes"].items()}

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Видеоны ашу мүмкін емес: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_len = n_frames / fps
    start = float(start_sec or 0)
    end = min(float(end_sec) if end_sec else video_len, video_len)
    if start > 0:
        cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)

    # Модель YOLO: если файла нет, Ultralytics скачает её сам в папку models/
    models_dir = ROOT / cfg["paths"]["models_dir"]
    models_dir.mkdir(exist_ok=True)
    mpath = models_dir / det["model"]
    model = YOLO(str(mpath) if mpath.exists() else det["model"])
    if not mpath.exists() and Path(det["model"]).exists():
        shutil.move(det["model"], mpath)

    writer, scale, W, H = None, 1.0, 0, 0
    tracks = {}       # ID трека -> история (центр, голоса классов, лучшая вырезка)
    counted = {}      # ID -> запись события
    counts = {c: {1: 0, 2: 0} for c in CLASS_ORDER}
    best_frame = (-1, None, None)
    frame_idx, t_sec, n_done = 0, start, 0
    t0 = time.time()
    tmp_video = out / "_annotated_tmp.mp4"

    while True:
        # Пропущенные кадры только «проматываем» — это быстрее
        if frame_idx % step != 0:
            if not cap.grab():
                break
            frame_idx += 1
            continue
        ok, frame = cap.read()
        if not ok:
            break
        if writer is None:
            H, W = frame.shape[:2]
            margin = max(10.0, H * 0.03)          # мёртвая зона у линии, пикселей (≈32 px для 1080p)
            scale = min(1.0, det.get("annotated_max_width", W) / W)
            writer = cv2.VideoWriter(str(tmp_video), cv2.VideoWriter_fourcc(*"mp4v"), fps / step,
                                     (int(W * scale) // 2 * 2, int(H * scale) // 2 * 2))
        ms = cap.get(cv2.CAP_PROP_POS_MSEC)
        t_sec = ms / 1000 if ms > 0 else start + frame_idx / fps
        if t_sec > end:
            break
        frame_idx += 1

        # YOLO находит объекты, ByteTrack даёт каждому свой ID
        # agnostic_nms: на одну машину — одна рамка (иначе автобус получал рамки «bus» и «truck» сразу)
        res = model.track(frame, persist=True, tracker=det.get("tracker", "bytetrack.yaml"),
                          classes=[PERSON_CLASS, *coco.keys()], conf=det["confidence"], agnostic_nms=True,
                          imgsz=det.get("imgsz", 640), device=device, verbose=False)[0]
        dets = []
        if res.boxes is not None and len(res.boxes):
            ids = res.boxes.id.int().tolist() if res.boxes.id is not None else [None] * len(res.boxes)
            for box, cls, conf, tid in zip(res.boxes.xyxy.tolist(), res.boxes.cls.int().tolist(),
                                           res.boxes.conf.tolist(), ids):
                dets.append({"box": box, "cls": coco.get(cls, "person"), "conf": conf, "id": tid})

        # Кадр с размытыми номерами всех машин и головами людей
        safe = blur_frame(frame, dets, cfg["privacy"])
        for d in dets:
            if d["cls"] == "person" or d["id"] is None:
                continue
            x1, y1, x2, y2 = d["box"]
            tr = tracks.setdefault(d["id"], {"side": None, "side_pt": None, "pending": 0, "heights": [],
                                             "votes": Counter(), "area": 0, "crop": None, "last": t_sec})
            # Класс — «голосованием» по кадрам; голос = уверенность × площадь рамки,
            # т.е. крупные (близкие, чёткие) кадры важнее далёких и мелких
            tr["votes"][d["cls"]] += d["conf"] * (x2 - x1) * (y2 - y1)
            tr["last"] = t_sec
            # Лучшая вырезка — самая крупная рамка (не касающаяся края кадра)
            area = (x2 - x1) * (y2 - y1)
            touches = x1 < 3 or y1 < 3 or x2 > W - 3 or y2 > H - 3
            if area > tr["area"] and not touches:
                xi1, yi1, xi2, yi2 = int(x1), int(y1), int(x2), int(y2)
                tr["area"] = area
                tr["crop"] = blur_crop(safe[yi1:yi2, xi1:xi2].copy(), cfg["privacy"])
            if d["id"] in counted or not crossing_step(tr, d["box"], a, b, margin, H):
                continue
            direction = 1 if tr["side"] > 0 else 2
            cls = tr["votes"].most_common(1)[0][0]
            counts[cls][direction] += 1
            counted[d["id"]] = {"n": len(counted) + 1, "time_s": round(t_sec, 2), "track_id": d["id"], "class": cls,
                                "direction": direction, "direction_name": dir_names[direction - 1],
                                "confidence": round(d["conf"], 3)}
            d["cls"] = cls

        # Машины, которые уже уехали: уточняем класс по всем кадрам трека, сохраняем вырезку, чистим память
        for tid in [k for k, v in tracks.items() if t_sec - v["last"] > 3.0]:
            tr = tracks.pop(tid)
            if tid in counted:
                _final_class(tr, counted[tid], counts)
                _save_crop(tr, counted[tid], crops_dir)

        for d in dets:                               # порядковый номер посчитанных машин для подписи
            if d["id"] in counted:
                d["n"] = counted[d["id"]]["n"]

        # Кадр для видео с разметкой: номера и лица тоже размыты
        small = cv2.resize(safe, (int(W * scale) // 2 * 2, int(H * scale) // 2 * 2))
        writer.write(draw_overlay(small, dets, line, scale, counts, dir_names, cfg=cfg))
        n_veh = sum(d["cls"] != "person" for d in dets)
        if n_veh > best_frame[0]:
            best_frame = (n_veh, frame.copy(), dets)

        n_done += 1
        if progress and n_done % 10 == 0:
            frac = min(1.0, (t_sec - start) / max(1e-6, end - start))
            el = time.time() - t0
            eta = el / max(frac, 1e-3) * (1 - frac)
            progress(frac, f"Өңделді: {frac * 100:.1f}% · саналды: {len(counted)} · "
                           f"қалды ≈ {eta / 60:.1f} мин")

    cap.release()
    for tid, tr in tracks.items():
        if tid in counted:
            _final_class(tr, counted[tid], counts)
            _save_crop(tr, counted[tid], crops_dir)
    for old in ("crops.csv", "labels.csv", "accuracy.json", "manual_counts.json"):
        (out / old).unlink(missing_ok=True)      # старые проверки к новому подсчёту не относятся
    if writer:
        writer.release()
        if progress:
            progress(1.0, "Бейне H.264 форматына түрлендірілуде…")
        to_h264(tmp_video, out / "annotated.mp4")
    duration = max(1e-6, min(end, t_sec) - start)

    # ---------- Сохраняем результаты ----------
    events = pd.DataFrame(sorted(counted.values(), key=lambda e: e["time_s"]),
                          columns=["n", "time_s", "track_id", "class", "direction", "direction_name",
                                   "confidence", "crop", "crop_w", "crop_h"])
    events.to_csv(out / "events.csv", index=False, encoding="utf-8")

    summary = {
        "video": str(video_path), "video_name": video_path.name,
        "fps": fps, "width": W, "height": H,
        "from_s": round(start, 2), "to_s": round(start + duration, 2),
        "duration_s": round(duration, 2), "line": [list(map(int, a)), list(map(int, b))],
        "direction_names": dir_names, "model": det["model"], "confidence": det["confidence"],
        "frame_step": step, "imgsz": det.get("imgsz"),
        "processing_s": round(time.time() - t0, 1),
        "counts": {c: {"1": counts[c][1], "2": counts[c][2]} for c in CLASS_ORDER},
        "total": len(events),
    }
    with open(out / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    from core.analysis import save_count_tables
    save_count_tables(cfg, out)

    if best_frame[1] is not None:
        cv2.imwrite(str(out / "stand_frame.png"), make_stand_frame(best_frame[1], best_frame[2], line, cfg))
    return summary


def _final_class(tr, ev, counts):
    """После того как машина уехала, класс решаем по ВСЕМ её кадрам (в момент пересечения
    линии голосов могло быть ещё мало — например, автобус издалека похож на легковую)."""
    cls = tr["votes"].most_common(1)[0][0]
    if cls != ev["class"]:
        counts[ev["class"]][ev["direction"]] -= 1
        counts[cls][ev["direction"]] += 1
        ev["class"] = cls


def _save_crop(tr, ev, crops_dir):
    """Сохраняет лучшую вырезку (уже размытую) и пишет её имя в событие."""
    if tr["crop"] is None or tr["crop"].size == 0:
        return
    name = f"{ev['track_id']}.jpg"
    cv2.imwrite(str(crops_dir / name), tr["crop"], [cv2.IMWRITE_JPEG_QUALITY, 92])
    ev["crop"] = name
    ev["crop_h"], ev["crop_w"] = tr["crop"].shape[:2]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--line", nargs=4, type=int, required=True)
    ap.add_argument("--start", type=float, default=0)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--imgsz", type=int, default=None)
    ap.add_argument("--step", type=int, default=None)
    args = ap.parse_args()
    cfg = load_config()
    if args.imgsz:
        cfg["detection"]["imgsz"] = args.imgsz
    if args.step:
        cfg["detection"]["frame_step"] = args.step
    s = run_counting(args.video, [args.line[:2], args.line[2:]], cfg, args.start, args.end,
                     progress=lambda f, t: print("\r" + t, end="", flush=True))
    print("\n", json.dumps(s, ensure_ascii=False, indent=1))
