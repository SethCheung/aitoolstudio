#!/usr/bin/env python3
"""ria_v4 数据集构建：硬筛 + 重打标 + 组装夜训任务。

两阶段（在 Mac 跑，调度 197/249）：
  --stage filter   把候选池推到 197，ArcFace 对 c0/c1/portrait 质心硬筛 >=0.6，
                   拉回通过图，拼对比图供人工复核。
  --stage compose  把通过图 + 3 张确认真脸组装到 NAS jobs/ria_v4/dataset_face，
                   写「token+场景」精简打标（删掉发色/眼睛/耳饰），写 dataset.toml + job.env，
                   留作夜训任务（dim16/alpha16）。

修复对照（相对 v3）：
  1) 数据=编辑真脸+硬筛同一张脸（v3 是 LoRA 现编的飘脸，训练集本身 0.43~0.75 散）
  2) 打标只留 token+场景（v3 把发色/眼睛/耳饰写进 caption，token 没学到脸）
  3) alpha 显式=dim（v3 没传 alpha，缩放仅 1/32）
"""
import argparse
import subprocess
from pathlib import Path

POOL_LOCAL = "/tmp/ria_v4_pool"
SURV_LOCAL = "/tmp/ria_v4_surv"
W197 = "sjm@192.168.1.197"
NAS = "/mnt/nas_comfyui/AI-Tool-Studio/comfyui"
REF_DIR = f"{NAS}/training/jobs/ria_v4_ref"
THRESHOLD = 0.6

# 精简打标：trigger「ria」+ 只写会变的（景别/视角/表情/光线/场景），
# 不写脸/发色/发型/眼睛/耳饰——逼 token 吸收身份不变量。
CAPTIONS = {
    "front_neutral_studio": "ria, head and shoulders portrait, front view, neutral expression, white studio background",
    "front_smile_studio": "ria, head and shoulders portrait, front view, soft smile, white studio background",
    "tq_left_neutral": "ria, portrait, three-quarter left view, neutral expression, studio background",
    "tq_right_smile": "ria, portrait, three-quarter right view, soft smile, studio background",
    "front_daylight": "ria, upper body, front view, neutral expression, natural daylight, outdoor",
    "golden_hour": "ria, upper body, soft smile, golden hour sunlight, outdoor",
    "cafe_window": "ria, upper body, sitting in a cafe, window light, looking at camera",
    "street_day": "ria, upper body, standing on a city street, daytime, looking at camera",
    "serious_editorial": "ria, head and shoulders portrait, front view, serious editorial expression, studio light",
    "look_up_soft": "ria, portrait, chin up, looking upward, soft expression, studio",
    "look_down_calm": "ria, portrait, gaze lowered, calm expression, studio",
    "closeup_beauty": "ria, close-up portrait, front view, neutral expression, soft light",
    "tq_left_smile": "ria, portrait, three-quarter left view, bright smile, studio",
    "indoor_warm": "ria, upper body, indoors, warm light, relaxed, looking at camera",
    "side_soft_light": "ria, head and shoulders portrait, front view, side lighting, neutral expression",
    "natural_candid": "ria, upper body, candid, soft daylight, slight smile",
}
REF_CAPTION = "ria, close-up portrait, front view, neutral expression, soft light"

# 训练超参（写进 job.env）
JOB_ENV = "NETWORK_DIM=16\nNETWORK_ALPHA=16\nEPOCHS=10\nSAVE_EVERY=1\nLR=1e-4\nRESOLUTION=1024\nNUM_REPEATS=6\nFLOW_SHIFT=2.2\n"


def sh(cmd):
    print(f"$ {cmd}", flush=True)
    return subprocess.run(cmd, shell=True, text=True)


def caption_for(fname: str) -> str:
    stem = Path(fname).stem
    if stem.startswith("ref_"):
        return REF_CAPTION
    # {iname}_{rk}_s{si}  —— iname 可能含下划线，去掉末尾 _<rk>_s<si>
    parts = stem.rsplit("_", 2)
    iname = parts[0] if len(parts) == 3 else stem
    return CAPTIONS.get(iname, "ria, portrait, front view, neutral expression")


def stage_filter():
    sh(f"ssh {W197} 'rm -rf /tmp/ria_v4_pool && mkdir -p /tmp/ria_v4_pool'")
    sh(f"scp -q {POOL_LOCAL}/*.png {W197}:/tmp/ria_v4_pool/")
    # 质心 = c0/c1/portrait
    sh(f"ssh {W197} '~/face_qc_env/bin/python ~/face_qc.py "
       f"--ref {REF_DIR} --candidates /tmp/ria_v4_pool --threshold {THRESHOLD} "
       f"--report /tmp/ria_v4_qc.json --sort-into /tmp/ria_v4_sorted --gpu -1'")
    Path(SURV_LOCAL).mkdir(parents=True, exist_ok=True)
    sh(f"rm -f {SURV_LOCAL}/*.png; scp -q '{W197}:/tmp/ria_v4_sorted/pass/*.png' {SURV_LOCAL}/ || true")
    sh(f"scp -q {W197}:/tmp/ria_v4_qc.json /tmp/ria_v4_qc.json")
    print(f"\n[filter] 通过图已拉到 {SURV_LOCAL}，报告 /tmp/ria_v4_qc.json", flush=True)


def stage_compose():
    # 在 197 上组装（NAS 共享，249 同样可见）
    remote = '''
import json, shutil, os
from pathlib import Path
NAS="/mnt/nas_comfyui/AI-Tool-Studio/comfyui"
REF=f"{NAS}/training/jobs/ria_v4_ref"
JOB=f"{NAS}/training/jobs/ria_v4"
DS=f"{JOB}/dataset_face"
os.makedirs(DS, exist_ok=True)
CAPTIONS=%r
REF_CAPTION=%r
def cap(fn):
    stem=Path(fn).stem
    if stem.startswith("ref_"): return REF_CAPTION
    parts=stem.rsplit("_",2); iname=parts[0] if len(parts)==3 else stem
    return CAPTIONS.get(iname, "ria, portrait, front view, neutral expression")
n=0
# 通过的候选
for p in sorted(Path("/tmp/ria_v4_sorted/pass").glob("*.png")):
    shutil.copy2(p, Path(DS)/p.name)
    (Path(DS)/p.name).with_suffix(".txt").write_text(cap(p.name)); n+=1
# 3 张确认真脸
for r in ["ref_c0.png","ref_c1.png","ref_portrait.jpg"]:
    src=Path(REF)/r
    if src.exists():
        shutil.copy2(src, Path(DS)/r)
        (Path(DS)/r).with_suffix(".txt").write_text(REF_CAPTION); n+=1
Path(JOB,"dataset.toml").write_text(f"""[general]
resolution = [1024, 1024]
caption_extension = ".txt"
batch_size = 1
enable_bucket = true
bucket_no_upscale = false

[[datasets]]
image_directory = "{DS}"
cache_directory = "/home/sjm/lora_work/ria_v4/cache_face"
num_repeats = 6
""")
Path(JOB,"job.env").write_text(%r)
print(f"[compose] dataset_face={n} 张, job 已组装 -> {JOB}")
print("[compose] 注意：未置 .running/.done，夜训 23:30 会自动认领")
''' % (CAPTIONS, REF_CAPTION, JOB_ENV)
    Path("/tmp/ria_v4_compose_remote.py").write_text(remote)
    sh(f"scp -q /tmp/ria_v4_compose_remote.py {W197}:/tmp/ria_v4_compose_remote.py")
    sh(f"ssh {W197} 'python3 /tmp/ria_v4_compose_remote.py'")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=["filter", "compose"])
    args = ap.parse_args()
    if args.stage == "filter":
        stage_filter()
    else:
        stage_compose()


if __name__ == "__main__":
    main()
