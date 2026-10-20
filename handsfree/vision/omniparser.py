"""Screen element perception using OmniParser / YOLO and local OCR bounding boxes."""

import csv
import io
import logging
import os
import shutil
import subprocess
from typing import List, Optional
from handsfree.domain.models import BoundingBox

logger = logging.getLogger(__name__)


class OmniParserDetector:
    """Detects interactive GUI elements (buttons, inputs, labels) from screen captures."""

    def __init__(self, weights_path: Optional[str] = None, tesseract_bin: str = "tesseract"):
        self.weights_path = weights_path
        self.tesseract_bin = shutil.which(tesseract_bin) or tesseract_bin
        self._yolo_model = None

    def detect_elements(self, image_bytes_or_path: bytes | str) -> List[BoundingBox]:
        """Parses image and returns list of interactive BoundingBoxes."""
        if not image_bytes_or_path:
            return []

        # If custom YOLO model is loaded, use it
        if self._yolo_model is not None:
            try:
                boxes = self._run_yolo_inference(image_bytes_or_path)
                if boxes:
                    return boxes
            except Exception as e:
                logger.warning(f"YOLO inference failed: {e}")

        # Local OCR element detection via tesseract TSV
        return self._detect_via_tesseract_tsv(image_bytes_or_path)

    def extract_screen_text(self, image_bytes_or_path: bytes | str) -> str:
        """Extracts all visible text on screen as clean plain text."""
        if not image_bytes_or_path:
            return ""

        try:
            image_data = self._get_image_bytes(image_bytes_or_path)
            if not image_data:
                return ""

            proc = subprocess.run(
                [self.tesseract_bin, "stdin", "stdout", "--oem", "1", "-l", "eng"],
                input=image_data,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=True,
                timeout=3.0,
            )
            raw = proc.stdout.decode("utf-8", errors="ignore")
            # Deduplicate multiple empty lines and strip noise
            lines = [line.strip() for line in raw.splitlines() if line.strip()]
            return " | ".join(lines)
        except Exception as e:
            logger.debug(f"Screen text extraction error: {e}")
            return ""

    def _get_image_bytes(self, image_bytes_or_path: bytes | str) -> bytes:
        if isinstance(image_bytes_or_path, str):
            if os.path.isfile(image_bytes_or_path):
                with open(image_bytes_or_path, "rb") as f:
                    return f.read()
            return b""
        return image_bytes_or_path

    def _detect_via_tesseract_tsv(self, image_bytes_or_path: bytes | str) -> List[BoundingBox]:
        """Pipes image bytes to tesseract TSV and builds line and word BoundingBoxes."""
        image_data = self._get_image_bytes(image_bytes_or_path)
        if not image_data or not shutil.which(self.tesseract_bin):
            return []

        try:
            proc = subprocess.run(
                [self.tesseract_bin, "stdin", "stdout", "tsv", "--oem", "1", "-l", "eng"],
                input=image_data,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=True,
                timeout=4.0,
            )
            tsv_text = proc.stdout.decode("utf-8", errors="ignore")
            reader = csv.DictReader(io.StringIO(tsv_text), delimiter="\t")

            boxes: List[BoundingBox] = []
            box_id = 1
            lines_dict = {}

            for row in reader:
                text = row.get("text", "").strip()
                try:
                    conf = float(row.get("conf", -1))
                    left = int(row.get("left", 0))
                    top = int(row.get("top", 0))
                    width = int(row.get("width", 0))
                    height = int(row.get("height", 0))
                    b_num = row.get("block_num", "0")
                    p_num = row.get("par_num", "0")
                    l_num = row.get("line_num", "0")
                except (ValueError, TypeError):
                    continue

                if text and conf >= 25.0:
                    # Single word bounding box
                    boxes.append(
                        BoundingBox(
                            id=box_id,
                            label=text,
                            x_min=left,
                            y_min=top,
                            x_max=left + width,
                            y_max=top + height,
                            confidence=conf / 100.0,
                        )
                    )
                    box_id += 1

                    line_key = (b_num, p_num, l_num)
                    if line_key not in lines_dict:
                        lines_dict[line_key] = []
                    lines_dict[line_key].append((text, left, top, left + width, top + height, conf))

            # Group adjacent words on the same line into composite phrase bounding boxes
            for words in lines_dict.values():
                if len(words) > 1:
                    phrase = " ".join(w[0] for w in words)
                    x1 = min(w[1] for w in words)
                    y1 = min(w[2] for w in words)
                    x2 = max(w[3] for w in words)
                    y2 = max(w[4] for w in words)
                    avg_conf = (sum(w[5] for w in words) / len(words)) / 100.0
                    boxes.append(
                        BoundingBox(
                            id=box_id,
                            label=phrase,
                            x_min=x1,
                            y_min=y1,
                            x_max=x2,
                            y_max=y2,
                            confidence=avg_conf,
                        )
                    )
                    box_id += 1

            return boxes

        except Exception as e:
            logger.warning(f"Tesseract TSV element detection failed: {e}")
            return []

    def _run_yolo_inference(self, image: bytes | str) -> List[BoundingBox]:
        """Runs underlying YOLO model on image."""
        return []
