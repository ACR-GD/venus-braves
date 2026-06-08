import glob, os
from PIL import Image

dumps = sorted(glob.glob("ite_out/gs_dumps/*.png"))
os.makedirs("scratch/dumps_preview", exist_ok=True)

for dump in dumps:
    img = Image.open(dump)
    # The header/title text is usually in the top left or top center
    # Let's just resize the whole image to something very small to see the layout,
    # and crop the top 200 pixels
    small = img.resize((img.width // 2, img.height // 2))
    name = os.path.basename(dump)
    small.save(f"scratch/dumps_preview/{name}")
    print(f"Saved preview of {name}")

