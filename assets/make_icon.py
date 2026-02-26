from PIL import Image, ImageDraw

def make_icon(path='assets/icon.ico'):
    im = Image.new('RGBA', (256, 256), (10, 132, 255, 255))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([20, 20, 236, 236], radius=32, fill=(10, 132, 255, 255), outline=(255, 255, 255, 255), width=6)
    d.rounded_rectangle([72, 116, 126, 172], radius=14, outline=(255, 255, 255, 255), width=10)
    d.rounded_rectangle([130, 84, 184, 140], radius=14, outline=(255, 255, 255, 255), width=10)
    d.line([(126, 144), (130, 112)], fill=(255, 255, 255, 255), width=10)
    d.polygon([(160, 170), (136, 210), (176, 196), (152, 236)], fill=(255, 255, 255, 230))
    im.save(path)

if __name__ == '__main__':
    make_icon()