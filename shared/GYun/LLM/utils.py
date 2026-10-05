import base64, os, re
from typing import Union

def image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as f: return base64.b64encode(f.read()).decode("utf-8")

def normalize_image_input(image: Union[str, bytes]) -> str:
    if isinstance(image, bytes):
        return f"data:image/jpeg;base64,{base64.b64encode(image).decode('utf-8')}"
    if isinstance(image, str):
        if image.startswith('data:image/'): return image
        if os.path.isfile(image): return f"data:image/jpeg;base64,{image_to_base64(image)}"
        
        # 修复：纯 Base64 字符串识别
        stripped = image.strip()
        if re.match(r'^[A-Za-z0-9+/=]+$', stripped) and len(stripped) > 100:
            mime = 'jpeg'
            if stripped.startswith('/9j/'): mime = 'jpeg'
            elif stripped.startswith('iVBOR'): mime = 'png'
            elif stripped.startswith('R0lGOD'): mime = 'gif'
            return f"data:image/{mime};base64,{stripped}"
            
        raise ValueError("Invalid image input")
    raise TypeError("image must be str or bytes")