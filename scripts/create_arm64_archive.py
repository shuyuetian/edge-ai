#!/usr/bin/env python3
"""创建权限明确的 ARM64 交付压缩包。"""

import argparse
import gzip
import os
from pathlib import Path
import tarfile


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--root-name", required=True)
    return parser.parse_args()


def archive_mode(relative_path, is_directory):
    if is_directory:
        return 0o755
    if relative_path.parts[0] == "bin":
        return 0o755
    if relative_path.suffix == ".sh":
        return 0o755
    return 0o644


def add_entry(archive, source_root, path, root_name):
    relative_path = path.relative_to(source_root)
    archive_name = Path(root_name) / relative_path
    info = archive.gettarinfo(str(path), arcname=str(archive_name))
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    info.mode = archive_mode(relative_path, path.is_dir())

    if path.is_dir():
        archive.addfile(info)
    elif path.is_file():
        with path.open("rb") as stream:
            archive.addfile(info, stream)
    else:
        raise ValueError("交付包不允许特殊文件: {}".format(path))


def main():
    args = parse_args()
    source = args.source.resolve()
    archive_path = args.archive.resolve()
    if not source.is_dir():
        raise ValueError("交付目录不存在: {}".format(source))
    if not args.root_name or "/" in args.root_name or "\\" in args.root_name:
        raise ValueError("root-name 必须是单级目录名")

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with archive_path.open("wb") as output:
        with gzip.GzipFile(fileobj=output, mode="wb", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                root_info = tarfile.TarInfo(args.root_name)
                root_info.type = tarfile.DIRTYPE
                root_info.mode = 0o755
                root_info.uid = 0
                root_info.gid = 0
                root_info.uname = "root"
                root_info.gname = "root"
                root_info.mtime = int(os.stat(source).st_mtime)
                archive.addfile(root_info)

                for path in sorted(source.rglob("*")):
                    add_entry(archive, source, path, args.root_name)


if __name__ == "__main__":
    main()
