"""Fetch the published weight files over HTTPS. No huggingface_hub."""
import os
from urllib.request import Request, urlopen

LAYA_FILES = (
    "laya-multilingual-fp16-seq512.rknn",
    "tokenizer.json",
    "temperature.json",
)
KEV_FILES = (
    "kev-0.8b-w8a8-opt0-ctx320.rkllm",
    "tokenizer.json",
    "q_weight.npy",
    "k_weight.npy",
    "q_bias.npy",
    "k_bias.npy",
    "pointer.json",
)
KEV_CPU_FILES = tuple(name for name in KEV_FILES if not name.endswith(".rkllm"))


def _fetch(url, dest):
    if os.path.isfile(dest) and os.path.getsize(dest) > 0:
        return
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".partial"
    request = Request(url, headers={"User-Agent": "system-one-rknn"})
    print("download", url, flush=True)
    with urlopen(request, timeout=120) as response, open(tmp, "wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
    os.replace(tmp, dest)


def model_files(laya_repo, kev_repo, names, engine="npu"):
    laya_files = () if engine == "cpu" else LAYA_FILES
    kev_files = KEV_CPU_FILES if engine == "cpu" else KEV_FILES
    catalog = {
        "laya": (laya_repo, "laya", laya_files),
        "kev": (kev_repo, "kev", kev_files),
    }
    jobs = []
    for name in names:
        repo, folder, files = catalog[name]
        jobs.extend((repo, folder, filename) for filename in files)
    return jobs


def ensure_models(root, laya_repo, kev_repo, names, engine="npu"):
    for repo, folder, name in model_files(laya_repo, kev_repo, names, engine):
        url = "https://huggingface.co/%s/resolve/main/%s" % (repo, name)
        _fetch(url, os.path.join(root, folder, name))
