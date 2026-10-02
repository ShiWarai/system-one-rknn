"""NPU runtimes baked into the arm64 image, one set per board."""
import hashlib
import os
import sys
from urllib.request import Request, urlopen

# Commits v2.3.2 and release-v1.3.1. A new board is a new entry and a CI matrix row.
_RKNN_RT_URL = (
    "https://github.com/airockchip/rknn-toolkit2/raw/"
    "42aa1d426c0a9e0869b6374edba009f7208a1926/"
    "rknpu2/runtime/Linux/librknn_api/aarch64/librknnrt.so"
)
_RKLLM_RT_URL = (
    "https://github.com/airockchip/rknn-llm/raw/"
    "f7390530443bf84f0394255a449d7cbe81e69d1c/"
    "rkllm-runtime/Linux/librkllm_api/aarch64/librkllmrt.so"
)
RK3588_LIBRARIES = (
    (
        "librknnrt-2.3.2.so",
        _RKNN_RT_URL,
        "d31fc19c85b85f6091b2bd0f6af9d962d5264a4e410bfb536402ec92bac738e8",
    ),
    (
        "librkllmrt-1.3.1.so",
        _RKLLM_RT_URL,
        "f25e9b099db08aaacd0a3ac62b4697d3951d6ae61ae41ea09f6702cfa89eb32c",
    ),
)

_BOARDS = {
    "rk3588": RK3588_LIBRARIES,
}


class UnsupportedBoard(Exception):
    pass


def runtime_libraries(board):
    """(filename, url, sha256) for this board. Empty and unknown boards fail."""
    name = (board or "").strip()
    try:
        return _BOARDS[name]
    except KeyError:
        known = ", ".join(sorted(_BOARDS))
        raise UnsupportedBoard("unsupported BOARD %r; known: %s" % (board, known)) from None


def _sha256(path):
    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _fetch(url, dest, digest):
    if os.path.isfile(dest) and _sha256(dest) == digest:
        return
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".partial"
    request = Request(url, headers={"User-Agent": "system-one-rknn"})
    print("download", url, flush=True)
    try:
        with urlopen(request, timeout=120) as response, open(tmp, "wb") as handle:
            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                handle.write(chunk)
        if _sha256(tmp) != digest:
            raise RuntimeError("sha256 mismatch for %s" % os.path.basename(dest))
        os.replace(tmp, dest)
    except Exception:
        if os.path.isfile(tmp):
            os.remove(tmp)
        raise


def install_runtime_libraries(board, arch, dest):
    """Write the board runtimes into dest. Only arm64 receives the aarch64 files."""
    specs = runtime_libraries(board)
    if arch != "arm64":
        return []
    written = []
    for filename, url, digest in specs:
        path = os.path.join(dest, filename)
        _fetch(url, path, digest)
        written.append(path)
    return written


def main(argv):
    if len(argv) != 4:
        raise SystemExit("usage: npu_libs.py BOARD ARCH DEST")
    try:
        install_runtime_libraries(argv[1], argv[2], argv[3])
    except UnsupportedBoard as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main(sys.argv)
