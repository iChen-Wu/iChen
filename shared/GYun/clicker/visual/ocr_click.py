"""OCR文字识别点击 预留实现"""

class OcrClick:
    def __init__(self, tesseract_path: str, lang="eng"):
        self.tesseract_path = tesseract_path
        self.lang = lang

    def click_by_text(self, target_text: str, region=None, match_mode="contain"):
        raise NotImplementedError("OCR识别功能暂未开发")