"""
License plate OCR — only invoked on incident-grade events (hit-and-run,
rash driving flagged for review) so it doesn't run on every frame.
"""
import re
import logging

log = logging.getLogger("urbaneye.ocr")

_PLATE_RE = re.compile(r"[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{3,4}")


class PlateReader:
    def __init__(self, mock=False):
        self.mock = mock
        if not mock:
            import easyocr
            self.reader = easyocr.Reader(["en"], gpu=False)

    def read(self, crop):
        """
        crop: HxWx3 numpy array containing (roughly) just the plate region.
        Returns (plate_text_or_None, confidence_float).
        """
        if crop is None or crop.size == 0:
            return None, 0.0
        if self.mock:
            return self._mock_read()

        results = self.reader.readtext(crop)
        if not results:
            return None, 0.0
        # take the highest-confidence line, normalise, validate shape
        text, conf = max(((r[1], r[2]) for r in results), key=lambda t: t[1])
        cleaned = re.sub(r"[^A-Z0-9]", "", text.upper())
        if _PLATE_RE.search(cleaned):
            return cleaned, float(conf)
        return cleaned or None, float(conf) * 0.6  # lower confidence if format looks off

    def _mock_read(self):
        import random
        state = random.choice(["KA03", "KA05", "KA41", "KA51"])
        letters = "".join(random.choice("ABCDEFGH") for _ in range(2))
        digits = "".join(random.choice("0123456789") for _ in range(4))
        return f"{state}{letters}{digits}", round(random.uniform(0.7, 0.96), 2)
