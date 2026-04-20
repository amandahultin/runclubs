"""Generate story-mandag-v8.png — sunny yellow, no headline, larger fonts.

The user will add copy (Peppad för måndag?! etc) in Instagram with their own
text features. We keep the two club cards, the CTA button and the footer,
and shift everything down so the image reads as one big clean card stack."""

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os

OUT = "/sessions/kind-adoring-shannon/mnt/loparklubbar/instagram/Stories/story-mandag-v8.png"
W, H = 1080, 1920

# Fonts
ARCHIVO_BLACK = "/tmp/fonts/ArchivoBlack.ttf"
DM_SANS = "/tmp/fonts/DMSans.ttf"
DM_SANS_600 = "/tmp/fonts/DMSans-600.ttf"
DM_SANS_500 = "/tmp/fonts/DMSans-500.ttf"

# Colors
SUN_YELLOW_TOP = (255, 214, 64)     # warm sunny yellow
SUN_YELLOW_BOT = (255, 178, 38)     # deeper mango toward bottom
INK = (30, 28, 24)                  # near-black for crispness
CARD_BG = (255, 255, 255)
CARD_SHADOW = (180, 120, 0)
CORAL = (255, 107, 87)              # existing brand accent, used sparingly
RED_TIME = (229, 57, 53)            # the red used for times on cards

# ---------- background: sunny gradient ----------
bg = Image.new("RGB", (W, H), SUN_YELLOW_TOP)
px = bg.load()
for y in range(H):
    t = y / (H - 1)
    r = int(SUN_YELLOW_TOP[0] * (1 - t) + SUN_YELLOW_BOT[0] * t)
    g = int(SUN_YELLOW_TOP[1] * (1 - t) + SUN_YELLOW_BOT[1] * t)
    b = int(SUN_YELLOW_TOP[2] * (1 - t) + SUN_YELLOW_BOT[2] * t)
    for x in range(W):
        px[x, y] = (r, g, b)

# subtle sun glow top-right
glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
gd = ImageDraw.Draw(glow)
cx, cy, R = 900, 260, 520
for rr in range(R, 0, -6):
    a = int(80 * (1 - rr / R))
    gd.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=(255, 240, 160, a))
glow = glow.filter(ImageFilter.GaussianBlur(40))
bg = Image.alpha_composite(bg.convert("RGBA"), glow).convert("RGB")

draw = ImageDraw.Draw(bg)

# ---------- top wordmark ----------
wm = ImageFont.truetype(ARCHIVO_BLACK, 28)
wm_text = "SWEDISH RUN CLUBS"
tw = draw.textlength(wm_text, font=wm)
draw.text((W / 2 - tw / 2, 70), wm_text, font=wm, fill=INK)

# small pill under wordmark — a crisp coral dot + "MÅNDAG"
# Actually: user removes the headline text entirely. So we leave the top clean,
# just the wordmark, and place a small sun-dot motif as a visual anchor.
# Sun motif with rays — crisp, graphic, sunny
import math
sd = ImageDraw.Draw(bg)
sun_cx, sun_cy, sun_r = W // 2, 430, 110
# rays
ray_len = 70
ray_gap = 30
for i in range(12):
    ang = (math.pi * 2) * (i / 12)
    x1 = sun_cx + math.cos(ang) * (sun_r + ray_gap)
    y1 = sun_cy + math.sin(ang) * (sun_r + ray_gap)
    x2 = sun_cx + math.cos(ang) * (sun_r + ray_gap + ray_len)
    y2 = sun_cy + math.sin(ang) * (sun_r + ray_gap + ray_len)
    sd.line((x1, y1, x2, y2), fill=INK, width=14)
# sun body (solid dark circle for crisp poster feel)
sd.ellipse((sun_cx - sun_r, sun_cy - sun_r, sun_cx + sun_r, sun_cy + sun_r),
           fill=INK)
# small inner highlight
sd.ellipse((sun_cx - sun_r + 28, sun_cy - sun_r + 28,
            sun_cx - sun_r + 58, sun_cy - sun_r + 58),
           fill=(255, 214, 64))

# ---------- club cards (larger, crisper) ----------
CARD_X = 80
CARD_W = W - 160
CARD_H = 250
CARD_RADIUS = 40
GAP = 40

CARDS = [
    {"time": "17:30", "name": "Svedjans Löpsällskap", "sub": "Svedjan Bageri"},
    {"time": "18:00", "name": "Runday",              "sub": "Scandic Park / Stadion"},
]

card_font_time = ImageFont.truetype(ARCHIVO_BLACK, 74)
card_font_name = ImageFont.truetype(ARCHIVO_BLACK, 56)
card_font_sub  = ImageFont.truetype(DM_SANS_500, 34)

# Move cards lower to sit below the sun motif
start_y = 780

for i, c in enumerate(CARDS):
    y = start_y + i * (CARD_H + GAP)

    # drop shadow
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    sdraw.rounded_rectangle(
        (CARD_X + 6, y + 14, CARD_X + CARD_W + 6, y + CARD_H + 14),
        radius=CARD_RADIUS, fill=(120, 70, 0, 90))
    shadow = shadow.filter(ImageFilter.GaussianBlur(12))
    bg = Image.alpha_composite(bg.convert("RGBA"), shadow).convert("RGB")
    draw = ImageDraw.Draw(bg)

    # white card
    draw.rounded_rectangle(
        (CARD_X, y, CARD_X + CARD_W, y + CARD_H),
        radius=CARD_RADIUS, fill=CARD_BG)

    # time (left)
    tx = CARD_X + 56
    ty = y + CARD_H / 2 - 48
    draw.text((tx, ty), c["time"], font=card_font_time, fill=RED_TIME)

    # name (right of time)
    nx = CARD_X + 320
    draw.text((nx, y + 50), c["name"], font=card_font_name, fill=INK)
    draw.text((nx, y + 50 + 70), c["sub"], font=card_font_sub, fill=(110, 108, 102))

# ---------- "Svep upp" hint (larger) ----------
swipe_font = ImageFont.truetype(DM_SANS_500, 38)
swipe_text = "Svep upp och hitta din klubb"
sw = draw.textlength(swipe_text, font=swipe_font)
swipe_y = start_y + 2 * (CARD_H + GAP) + 40
draw.text((W / 2 - sw / 2, swipe_y), swipe_text, font=swipe_font, fill=INK)

# ---------- CTA button (bigger) ----------
btn_w, btn_h = 560, 120
btn_x = W / 2 - btn_w / 2
btn_y = swipe_y + 90
draw.rounded_rectangle((btn_x, btn_y, btn_x + btn_w, btn_y + btn_h),
                       radius=btn_h / 2, fill=INK)
btn_font = ImageFont.truetype(ARCHIVO_BLACK, 46)
btn_text = "runclubs.se"
bw = draw.textlength(btn_text, font=btn_font)
# draw text, then arrow glyph separately (Archivo Black lacks →, use DM Sans)
arrow_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
arrow = "→"
aw = draw.textlength(arrow, font=arrow_font)
total = bw + 24 + aw
tx0 = W / 2 - total / 2
draw.text((tx0, btn_y + btn_h / 2 - 30), btn_text,
          font=btn_font, fill=(255, 255, 255))
draw.text((tx0 + bw + 24, btn_y + btn_h / 2 - 32), arrow,
          font=arrow_font, fill=(255, 255, 255))

# ---------- footer ----------
foot_font = ImageFont.truetype(ARCHIVO_BLACK, 26)
foot_text = "FLER KLUBBAR OCH TIDER"
fw = draw.textlength(foot_text, font=foot_font)
draw.text((W / 2 - fw / 2, H - 140), foot_text, font=foot_font, fill=INK)

bg.save(OUT, "PNG", optimize=True)
print("Saved:", OUT, "size:", os.path.getsize(OUT))
