"""Конфиденциальность: размытие номеров и лиц.

Номера НЕ распознаются. Мы просто сильно размываем зону, где номер находится
у любой машины (нижняя часть рамки), а у людей — голову (верх рамки).
Размытие делается ДО сохранения любого кадра, вырезки или видео.
"""
import cv2


def blur_region(img, x1, y1, x2, y2):
    """Сильно размывает прямоугольник (на месте)."""
    h, w = img.shape[:2]
    x1, y1, x2, y2 = max(0, int(x1)), max(0, int(y1)), min(w, int(x2)), min(h, int(y2))
    if x2 - x1 < 3 or y2 - y1 < 3:
        return
    w, h = x2 - x1, y2 - y1
    # Уменьшаем в 16 раз и растягиваем обратно: номер шириной 100 px превращается
    # в 6 px — прочитать невозможно. Это в десятки раз быстрее большого GaussianBlur.
    small = cv2.resize(img[y1:y2, x1:x2], (max(1, w // 16), max(1, h // 16)), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (3, 3), 0)
    img[y1:y2, x1:x2] = cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)


def _plate_zone(x1, y1, x2, y2, p):
    """Зона номера внутри рамки машины (доли из config.privacy)."""
    w, h = x2 - x1, y2 - y1
    (fy1, fy2), (fx1, fx2) = p["plate_band"], p["plate_band_width"]
    return x1 + fx1 * w, y1 + fy1 * h, x1 + fx2 * w, y1 + fy2 * h


def blur_frame(frame, dets, p):
    """Копия кадра с размытыми номерами машин и головами людей."""
    img = frame.copy()
    for d in dets:
        x1, y1, x2, y2 = d["box"]
        if d["cls"] == "person":
            if p.get("blur_faces", True):
                blur_region(img, x1, y1, x2, y1 + p["head_fraction"] * (y2 - y1))
        elif p.get("blur_plates", True):
            blur_region(img, *_plate_zone(x1, y1, x2, y2, p))
    return img


def blur_crop(crop, p):
    """Вырезка одной машины: размываем зону номера."""
    if crop is None or crop.size == 0:
        return crop
    h, w = crop.shape[:2]
    if p.get("blur_plates", True):
        blur_region(crop, *_plate_zone(0, 0, w, h, p))
    return crop
