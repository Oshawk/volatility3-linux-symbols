from io import BytesIO
import lzma
from pathlib import Path
from re import finditer
from subprocess import check_output
import tarfile

import requests
from unix_ar import ArFile

BASE_PATH = Path(__file__).parent.absolute()

DEB_REGEX = r"""href="(?P<remote_file_name>linux-image-(?P<kernel_release>\d+\.\d+\.\d+-[^"]+)-dbg(sym)?_[^"]+_(?P<architecture>[^"]+).d?deb)"""


def grab_deb(name, mirror):
    path = BASE_PATH / name
    path.mkdir(exist_ok=True)

    print(f"getting packages for {name}")
    listing = requests.get(f"{mirror}/pool/main/l/linux/").text
    for match in finditer(DEB_REGEX, listing):
        remote_file_name = match.group("remote_file_name")
        kernel_release = match.group("kernel_release")
        architecture = match.group("architecture")
        local_file_name = f"{kernel_release}_{architecture}"

        if (path / f"{local_file_name}.json.xz").exists():
            print(f"{local_file_name}.json.xz already exists")
            continue

        print(f"downloading {remote_file_name}")
        deb = requests.get(f"{mirror}/pool/main/l/linux/{remote_file_name}")

        print(f"extracting {remote_file_name}")
        ar = ArFile(BytesIO(deb.content))

        tar_name = None
        for ar_info in ar.infolist():
            if ar_info.name.startswith(b"data.tar"):
                tar_name = ar_info.name

        if tar_name is None:
            print(f"data.tar not found in {remote_file_name}")
            continue

        tar = tarfile.open(fileobj=ar.open(tar_name.decode()))

        elf_member = None
        system_map_member = None
        for member in tar.getmembers():
            file_name = member.name.split("/")[-1]
            if file_name.startswith("vmlinux"):
                elf_member = member
            elif file_name.startswith("System.map"):
                system_map_member = member

        if elf_member is None:
            print("elf member not found")
            continue

        if system_map_member is None:
            print("system map member not found")
            continue

        with open(path / f"{local_file_name}_elf", "wb") as f:
            f.write(tar.extractfile(elf_member).read())

        with open(path / f"{local_file_name}_system_map", "wb") as f:
            f.write(tar.extractfile(system_map_member).read())

        print(f"creating {local_file_name}.json.xz")
        with lzma.open(path / f"{local_file_name}.json.xz", "wb") as f:
            f.write(check_output((
                "dwarf2json",
                "linux",
                "--elf",
                path / f"{local_file_name}_elf",
                "--system-map",
                path / f"{local_file_name}_system_map"
            )))

        (path / f"{local_file_name}_elf").unlink()
        (path / f"{local_file_name}_system_map").unlink()


def main():
    # UK mirrors used where possible.
    grab_deb("kali", "https://kali.download/kali/")  # https://http.kali.org/


if __name__ == '__main__':
    main()
