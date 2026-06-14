#!/usr/bin/env python3
"""ria 小红书拍摄公式：角度/景别/姿势/场景模板，组合出多样化的穿搭内容 prompt。

参考小红书穿搭/写真对标账号（aeri.ling 类）的出片套路：同一套穿搭多角度多姿势（轮播），
或一组不同穿搭各配合适机位。解决"角度单一"问题。

用法：
    python3 scripts/ria_shot_formula.py --mode series --outfit-idx 0   # 一套穿搭多机位（轮播帖）
    python3 scripts/ria_shot_formula.py --mode lookbook                # 多套穿搭各一张
    python3 scripts/ria_shot_formula.py --list                          # 看全部机位/穿搭
被 ria_content_batch.py 调用产出实际图。
"""
import argparse

# 身份前缀：纯 trigger。Juggernaut/SDXL 的 LoRA 连发色/耳饰一起绑了，不用写进提示词
# （Z-Image 的 LoRA 只绑脸不绑发、加发色提示词会把脸带欧美，已弃用 Z-Image）。
TRIGGER = "ria"
# 写实质量块（配合 Z-Image 或 Qwen 都通用）
QUALITY = ("photorealistic, professional fashion photography, natural detailed skin texture with visible pores, "
           "sharp focus, high resolution, realistic candid photo, soft natural lighting")
NEGATIVE = ("oil painting, illustration, 3d render, cartoon, plastic skin, waxy, airbrushed, lowres, blurry, "
            "deformed, extra fingers, bad anatomy, watermark, text, logo")

# 机位公式：(名称, 景别+角度+姿势+构图[+隐含场景])
SHOTS = [
    ("full_front",     "full body OOTD shot, eye level, standing facing camera with one hand in pocket, relaxed confident posture, centered"),
    ("full_low_leg",   "full body shot from a low camera angle to lengthen the legs, standing with weight on one leg, looking down toward the lens, editorial"),
    ("full_walk",      "full body candid walking shot mid-stride on a city sidewalk, looking ahead, natural movement, street style"),
    ("full_lean",      "full body, leaning against a textured wall with ankles crossed, relaxed, gaze to the side, off-center composition"),
    ("cowboy_3q",      "three-quarter knee-up shot, body turned 3/4 to camera, one hand adjusting hair, soft gaze, rule-of-thirds"),
    ("half_side",      "waist-up shot from the side, profile turning slightly toward camera, elegant posture"),
    ("over_shoulder",  "waist-up over-the-shoulder shot, back partly to camera, looking back at the lens, hair in motion"),
    ("back_outfit",    "full body back view showing the outfit from behind, head turned to glance back over the shoulder"),
    ("sit_cafe",       "seated at a sunny cafe table, upper body, one hand holding a coffee cup, gentle candid smile looking away, window light"),
    ("sit_stairs",     "sitting on outdoor stone steps, full body, knees together, hands resting on lap, casual lifestyle, natural light"),
    ("mirror_selfie",  "full body mirror selfie holding a phone, casual OOTD pose, slightly high angle, bedroom mirror"),
    ("detail_acc",     "close detail shot of the outfit, accessories, hands and waist, no face, product-focus flat composition"),
    ("high_self",      "upper body from a slightly high self-portrait angle, looking up at the camera with a soft smile, face-flattering"),
    ("candid_laugh",   "upper body candid, natural laugh looking away from camera, lifestyle moment, golden hour"),
]

# 穿搭公式：小红书常见风格池
OUTFITS = [
    "wearing an oversized beige knit sweater and light blue denim shorts",
    "wearing a fitted black blazer mini dress and heels",
    "wearing a white cropped tee and high-waisted wide-leg jeans",
    "wearing a pastel floral midi sundress",
    "wearing a cropped hoodie and bike shorts, athleisure",
    "wearing a camel trench coat over a cream turtleneck, autumn street style",
    "wearing a satin slip dress, evening elegant",
    "wearing an oversized denim jacket and a pleated mini skirt",
]

# 同一套穿搭做轮播帖时的推荐机位组合（多样且互补）
SERIES_SHOTS = ["full_front", "full_low_leg", "cowboy_3q", "over_shoulder", "sit_cafe", "back_outfit"]


def build_prompt(outfit, shot_recipe):
    return f"{TRIGGER}, {outfit}, {shot_recipe}, {QUALITY}"


def series(outfit_idx=0, shots=None):
    outfit = OUTFITS[outfit_idx % len(OUTFITS)]
    names = shots or SERIES_SHOTS
    smap = dict(SHOTS)
    return [(f"o{outfit_idx}_{n}", build_prompt(outfit, smap[n])) for n in names if n in smap]


def lookbook(n=8):
    out = []
    for i in range(n):
        outfit = OUTFITS[i % len(OUTFITS)]
        sname, srecipe = SHOTS[i % len(SHOTS)]
        out.append((f"look{i}_{sname}", build_prompt(outfit, srecipe)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["series", "lookbook"], default="series")
    ap.add_argument("--outfit-idx", type=int, default=0)
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    if args.list:
        print("=== 机位公式 SHOTS ===")
        for n, r in SHOTS:
            print(f"  {n:16} {r}")
        print("\n=== 穿搭池 OUTFITS ===")
        for i, o in enumerate(OUTFITS):
            print(f"  [{i}] {o}")
        return
    items = series(args.outfit_idx) if args.mode == "series" else lookbook(args.n)
    for name, p in items:
        print(f"\n[{name}]\n{p}")


if __name__ == "__main__":
    main()
