"""Download isolated Linux runtimes into this workspace; verify upstream checksums."""
import hashlib
import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / ".runtime" / "downloads"


def fetch(url, name, expected, algorithm):
    target = DEST / name
    if target.exists():
        with target.open("rb") as cached:
            cached_hash = hashlib.file_digest(cached, algorithm).hexdigest()
        if cached_hash == expected:
            print(f"Verified cached {name}", flush=True)
            return
    tmp = target.with_suffix(".partial")
    with httpx.stream("GET", url, follow_redirects=True, timeout=120) as response:
        response.raise_for_status()
        size = int(response.headers.get("content-length", 0))
        done, report = 0, 0
        digest = hashlib.new(algorithm)
        with tmp.open("wb") as out:
            for chunk in response.iter_bytes(1024 * 1024):
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if done - report >= 50 * 1024 * 1024:
                    print(f"{name}: {done // 1048576}/{size // 1048576} MiB", flush=True)
                    report = done
        if digest.hexdigest() != expected:
            raise ValueError(f"Checksum mismatch: {name}")
    tmp.replace(target)
    print(f"Verified {name}: {digest.hexdigest()}", flush=True)


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    base = "https://downloads.apache.org/hadoop/common/hadoop-3.4.2/"
    name = "hadoop-3.4.2-lean.tar.gz"
    with httpx.Client(follow_redirects=True, timeout=120) as client:
        check = client.get(base + name + ".sha512")
        check.raise_for_status()
        expected = next(word for word in check.text.split() if len(word) == 128)
        java = client.get("https://api.adoptium.net/v3/assets/latest/11/hotspot",
                          params={"architecture": "x64", "image_type": "jre", "os": "linux"})
        java.raise_for_status()
        package = java.json()[0]["binary"]["package"]
    fetch(package["link"], "java11.tar.gz", package["checksum"], "sha256")
    fetch(base + name, name, expected, "sha512")
    (DEST / "provenance.json").write_text(json.dumps({
        "hadoop_url": base + name, "hadoop_sha512": expected,
        "java_url": package["link"], "java_sha256": package["checksum"]
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
