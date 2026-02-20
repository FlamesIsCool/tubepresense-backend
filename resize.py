from PIL import Image
import requests
from io import BytesIO

def get_resized_thumbnail(video_id):
    url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
    res = requests.get(url)

    img = Image.open(BytesIO(res.content)).convert("RGBA")
    img = img.resize((512, 512))

    path = f"thumb_cache/{video_id}.png"
    img.save(path)

    return path
