#!/usr/bin/env python3
"""Reapply local PGR Wine/Rosetta patches after a game update.

Run this from the Punishing Gray Raven install directory after Steam updates the
game. The script backs up each binary before modifying it and only patches known
byte signatures or PE-derived locations.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import shutil
import struct
import sys
from dataclasses import dataclass
from pathlib import Path


IMAGE_DIRECTORY_ENTRY_EXPORT = 0
IMAGE_DIRECTORY_ENTRY_IMPORT = 1
IMAGE_SCN_MEM_EXECUTE = 0x20000000


def u16(data: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def u64(data: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from("<Q", data, offset)[0]


def p32(value: int) -> bytes:
    return struct.pack("<i", value)


def p32u(value: int) -> bytes:
    return struct.pack("<I", value)


def p64(value: int) -> bytes:
    return struct.pack("<Q", value)


@dataclass(frozen=True)
class Section:
    name: str
    virtual_address: int
    virtual_size: int
    raw_offset: int
    raw_size: int
    characteristics: int

    @property
    def executable(self) -> bool:
        return bool(self.characteristics & IMAGE_SCN_MEM_EXECUTE)


class PE:
    def __init__(self, path: Path, data: bytes | bytearray):
        self.path = path
        self.data = data
        if data[:2] != b"MZ":
            raise ValueError(f"{path.name}: not an MZ executable")
        self.pe_offset = u32(data, 0x3C)
        if data[self.pe_offset : self.pe_offset + 4] != b"PE\0\0":
            raise ValueError(f"{path.name}: not a PE executable")
        self.number_of_sections = u16(data, self.pe_offset + 6)
        self.optional_header_size = u16(data, self.pe_offset + 20)
        self.optional_header = self.pe_offset + 24
        self.magic = u16(data, self.optional_header)
        if self.magic != 0x20B:
            raise ValueError(f"{path.name}: expected PE32+ x64 image")
        self.image_base = u64(data, self.optional_header + 24)
        self.data_directories = self.optional_header + 112
        self.sections = self._read_sections()

    def _read_sections(self) -> list[Section]:
        sections_offset = self.optional_header + self.optional_header_size
        sections: list[Section] = []
        for index in range(self.number_of_sections):
            offset = sections_offset + index * 40
            name = bytes(self.data[offset : offset + 8]).split(b"\0", 1)[0].decode("latin1")
            sections.append(
                Section(
                    name=name,
                    virtual_size=u32(self.data, offset + 8),
                    virtual_address=u32(self.data, offset + 12),
                    raw_size=u32(self.data, offset + 16),
                    raw_offset=u32(self.data, offset + 20),
                    characteristics=u32(self.data, offset + 36),
                )
            )
        return sections

    def data_directory(self, index: int) -> tuple[int, int]:
        offset = self.data_directories + index * 8
        return u32(self.data, offset), u32(self.data, offset + 4)

    def rva_to_offset(self, rva: int) -> int:
        for section in self.sections:
            size = max(section.virtual_size, section.raw_size)
            if section.virtual_address <= rva < section.virtual_address + size:
                raw_delta = rva - section.virtual_address
                if raw_delta >= section.raw_size:
                    break
                return section.raw_offset + raw_delta
        raise ValueError(f"{self.path.name}: cannot map RVA 0x{rva:x} to file offset")

    def offset_to_rva(self, offset: int) -> int:
        for section in self.sections:
            if section.raw_offset <= offset < section.raw_offset + section.raw_size:
                return section.virtual_address + (offset - section.raw_offset)
        raise ValueError(f"{self.path.name}: cannot map file offset 0x{offset:x} to RVA")

    def read_c_string(self, rva: int) -> str:
        offset = self.rva_to_offset(rva)
        end = self.data.index(0, offset)
        return bytes(self.data[offset:end]).decode("ascii", errors="replace")

    def import_iat_va(self, dll_name: str, function_name: str) -> int:
        import_rva, _ = self.data_directory(IMAGE_DIRECTORY_ENTRY_IMPORT)
        if not import_rva:
            raise ValueError(f"{self.path.name}: no import directory")
        descriptor_offset = self.rva_to_offset(import_rva)
        wanted_dll = dll_name.lower()
        index = 0
        while True:
            offset = descriptor_offset + index * 20
            original_first_thunk = u32(self.data, offset)
            name_rva = u32(self.data, offset + 12)
            first_thunk = u32(self.data, offset + 16)
            if original_first_thunk == name_rva == first_thunk == 0:
                break
            name = self.read_c_string(name_rva).lower()
            if name == wanted_dll:
                lookup_rva = original_first_thunk or first_thunk
                lookup_offset = self.rva_to_offset(lookup_rva)
                thunk_index = 0
                while True:
                    thunk = u64(self.data, lookup_offset + thunk_index * 8)
                    if thunk == 0:
                        break
                    if not (thunk & (1 << 63)):
                        import_name_offset = self.rva_to_offset(thunk) + 2
                        end = self.data.index(0, import_name_offset)
                        imported = bytes(self.data[import_name_offset:end]).decode("ascii", errors="replace")
                        if imported == function_name:
                            return self.image_base + first_thunk + thunk_index * 8
                    thunk_index += 1
            index += 1
        raise ValueError(f"{self.path.name}: import {dll_name}!{function_name} not found")

    def export_rva_by_name(self, function_name: str) -> int:
        export_rva, _ = self.data_directory(IMAGE_DIRECTORY_ENTRY_EXPORT)
        if not export_rva:
            raise ValueError(f"{self.path.name}: no export directory")
        export_offset = self.rva_to_offset(export_rva)
        number_of_names = u32(self.data, export_offset + 24)
        address_of_functions = u32(self.data, export_offset + 28)
        address_of_names = u32(self.data, export_offset + 32)
        address_of_ordinals = u32(self.data, export_offset + 36)
        names_offset = self.rva_to_offset(address_of_names)
        ordinals_offset = self.rva_to_offset(address_of_ordinals)
        functions_offset = self.rva_to_offset(address_of_functions)
        for index in range(number_of_names):
            name_rva = u32(self.data, names_offset + index * 4)
            if self.read_c_string(name_rva) == function_name:
                ordinal_index = u16(self.data, ordinals_offset + index * 2)
                return u32(self.data, functions_offset + ordinal_index * 4)
        raise ValueError(f"{self.path.name}: export {function_name} not found")

    def sole_export_entry_rva(self) -> int:
        export_rva, _ = self.data_directory(IMAGE_DIRECTORY_ENTRY_EXPORT)
        if not export_rva:
            raise ValueError(f"{self.path.name}: no export directory")
        export_offset = self.rva_to_offset(export_rva)
        number_of_functions = u32(self.data, export_offset + 20)
        address_of_functions = u32(self.data, export_offset + 28)
        if number_of_functions != 1:
            raise ValueError(f"{self.path.name}: expected one PGRBase export, found {number_of_functions}")
        functions_offset = self.rva_to_offset(address_of_functions)
        return u32(self.data, functions_offset)

    def find_executable_code_cave(self, size: int, preferred_rva: int | None = None) -> int:
        if preferred_rva is not None:
            try:
                preferred_offset = self.rva_to_offset(preferred_rva)
                if self.data[preferred_offset : preferred_offset + size] == b"\xCC" * size:
                    return preferred_offset
            except ValueError:
                pass

        for section in self.sections:
            if not section.executable or section.raw_size < size:
                continue
            start = section.raw_offset
            end = section.raw_offset + section.raw_size
            run_start = -1
            run_len = 0
            for offset in range(start, end):
                if self.data[offset] == 0xCC:
                    if run_start < 0:
                        run_start = offset
                    run_len += 1
                    if run_len >= size:
                        return run_start
                else:
                    run_start = -1
                    run_len = 0
        raise ValueError(f"{self.path.name}: no executable 0xCC code cave of {size} bytes found")


class PatchSession:
    def __init__(self, root: Path, dry_run: bool):
        self.root = root
        self.dry_run = dry_run
        self.backup_dir = root / "patch_backups" / _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        self.backed_up: set[Path] = set()
        self.changed: set[Path] = set()
        self.warnings: list[str] = []

    def backup(self, path: Path) -> None:
        if path in self.backed_up or self.dry_run:
            return
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, self.backup_dir / path.name)
        self.backed_up.add(path)

    def write(self, path: Path, data: bytes | bytearray) -> None:
        if self.dry_run:
            return
        self.backup(path)
        path.write_bytes(bytes(data))
        self.changed.add(path)

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        print(f"WARN: {message}")


def find_exact(data: bytes | bytearray, needle: bytes) -> list[int]:
    out: list[int] = []
    start = 0
    while True:
        found = data.find(needle, start)
        if found < 0:
            return out
        out.append(found)
        start = found + 1


def find_masked(data: bytes | bytearray, pattern: list[int | None]) -> list[int]:
    out: list[int] = []
    plen = len(pattern)
    last = len(data) - plen + 1
    for offset in range(max(last, 0)):
        for index, wanted in enumerate(pattern):
            if wanted is not None and data[offset + index] != wanted:
                break
        else:
            out.append(offset)
    return out


def find_masked_in_section(pe: PE, data: bytes | bytearray, pattern: list[int | None], section_name: str) -> list[int]:
    for section in pe.sections:
        if section.name != section_name:
            continue
        start = section.raw_offset
        end = section.raw_offset + section.raw_size
        return [start + hit for hit in find_masked(data[start:end], pattern)]
    return []


def hits_in_section(pe: PE, hits: list[int], section_name: str) -> list[int]:
    for section in pe.sections:
        if section.name != section_name:
            continue
        start = section.raw_offset
        end = section.raw_offset + section.raw_size
        return [hit for hit in hits if start <= hit < end]
    return []


def build_unity_stub(stub_va: int, load_library_iat_va: int, unity_main_rva: int, game_image_base: int) -> bytes:
    code = bytearray()
    code += b"\x48\x83\xEC\x28"  # sub rsp, 28h
    code += b"\x48\x8D\x0D" + p32(80 - 11)  # lea rcx, UnityPlayer.dll
    code += b"\xFF\x15" + p32(load_library_iat_va - (stub_va + 17))  # call [LoadLibraryA IAT]
    code += b"\x48\x85\xC0"  # test rax, rax
    code += b"\x74" + bytes([66 - 22])  # je fail
    code += b"\x49\x89\xC3"  # mov r11, rax
    code += b"\x48\xB9" + p64(game_image_base)  # mov rcx, PGR.exe hInstance
    code += b"\x31\xD2"  # xor edx, edx
    code += b"\x4C\x8D\x05" + p32(96 - 44)  # lea r8, empty wide cmdline
    code += b"\x41\xB9\x01\x00\x00\x00"  # mov r9d, 1
    code += b"\x4C\x89\xD8"  # mov rax, r11
    code += b"\x48\x05" + p32u(unity_main_rva)  # add rax, UnityMain RVA
    code += b"\xFF\xD0"  # call rax
    code += b"\x48\x83\xC4\x28"  # add rsp, 28h
    code += b"\xC3"  # ret
    code += b"\xB8\xDE\x00\x00\x00"  # fail: mov eax, 222
    code += b"\x48\x83\xC4\x28"
    code += b"\xC3"
    code += b"\x90" * (80 - len(code))
    code += b"UnityPlayer.dll\0"
    code += b"\0" * (96 - len(code))
    code += b"\0\0"
    code += b"\0" * (124 - len(code))
    return bytes(code)


def patch_pgrbase(session: PatchSession) -> None:
    path = session.root / "PGRBase.dll"
    pgr_exe = session.root / "PGR.exe"
    unity_player = session.root / "UnityPlayer.dll"
    if not path.exists():
        session.warn("PGRBase.dll missing")
        return
    if not pgr_exe.exists():
        session.warn("PGR.exe missing; cannot derive game image base")
        return
    if not unity_player.exists():
        session.warn("UnityPlayer.dll missing; cannot derive UnityMain RVA")
        return

    data = bytearray(path.read_bytes())
    pe = PE(path, data)
    changed = False

    rosetta_original = bytes.fromhex("21 ca 21 ca 81 f2 b3 a5 d6 7a 0f 1f c2 41 8b 0a 50 48 8d 05")
    rosetta_patched = bytes.fromhex("21 ca 21 ca 81 f2 b3 a5 d6 7a 90 90 90 41 8b 0a 50 48 8d 05")
    original_hits = find_exact(data, rosetta_original)
    patched_hits = find_exact(data, rosetta_patched)
    if original_hits:
        if len(original_hits) != 1:
            session.warn(f"PGRBase Rosetta NOP signature matched {len(original_hits)} times; skipping")
        else:
            patch_offset = original_hits[0] + 10
            print(f"PGRBase.dll: patching Rosetta NOP at file+0x{patch_offset:x}")
            data[patch_offset : patch_offset + 3] = b"\x90\x90\x90"
            changed = True
    elif patched_hits:
        print("PGRBase.dll: Rosetta NOP already patched")
    else:
        session.warn("PGRBase Rosetta NOP signature not found")

    game_pe = PE(pgr_exe, pgr_exe.read_bytes())
    unity_pe = PE(unity_player, unity_player.read_bytes())
    load_library_iat_va = pe.import_iat_va("kernel32.dll", "LoadLibraryA")
    unity_main_rva = unity_pe.export_rva_by_name("UnityMain")
    entry_rva = pe.sole_export_entry_rva()
    entry_offset = pe.rva_to_offset(entry_rva)
    entry_va = pe.image_base + entry_rva

    existing = bytes(data[entry_offset : entry_offset + 16])
    if existing[0] == 0xE9:
        target_va = entry_va + 5 + struct.unpack_from("<i", existing, 1)[0]
        try:
            target_offset = pe.rva_to_offset(target_va - pe.image_base)
            if b"UnityPlayer.dll\0" in bytes(data[target_offset : target_offset + 128]):
                print("PGRBase.dll: Unity startup stub already installed")
                if changed:
                    session.write(path, data)
                return
        except ValueError:
            pass

    if not (existing[0] == 0xE9 and existing[5:16] == b"\xCC" * 11):
        session.warn(
            "PGRBase export entry does not look like the expected protected jump; "
            f"found {existing[:16].hex(' ')}"
        )
        if changed:
            session.write(path, data)
        return

    stub_len = 124
    stub_offset = pe.find_executable_code_cave(stub_len, preferred_rva=0x1DA0A)
    stub_rva = pe.offset_to_rva(stub_offset)
    stub_va = pe.image_base + stub_rva
    stub = build_unity_stub(stub_va, load_library_iat_va, unity_main_rva, game_pe.image_base)
    rel = stub_va - (entry_va + 5)
    if not -(1 << 31) <= rel < (1 << 31):
        session.warn("PGRBase stub is out of rel32 jump range")
        if changed:
            session.write(path, data)
        return

    print(f"PGRBase.dll: installing Unity startup stub at RVA 0x{stub_rva:x}")
    data[stub_offset : stub_offset + len(stub)] = stub
    data[entry_offset : entry_offset + 5] = b"\xE9" + p32(rel)
    changed = True

    if changed:
        session.write(path, data)


def patch_gameassembly(session: PatchSession) -> None:
    path = session.root / "GameAssembly.dll"
    if not path.exists():
        session.warn("GameAssembly.dll missing")
        return

    data = bytearray(path.read_bytes())
    pe = PE(path, data)
    pattern = [
        0x33,
        0x0D,
        None,
        None,
        None,
        None,
        0x41,
        0x09,
        0xC9,
        0x45,
        0x31,
        0xC1,
        0x41,
        0x0F,
        0x1F,
        0xC1,
        0x44,
        0x8B,
        0x0A,
        0x49,
        0x89,
        0xD0,
        0x4C,
        0x23,
        0x05,
    ]
    patched_pattern = pattern[:]
    patched_pattern[12:16] = [0x90, 0x90, 0x90, 0x90]

    fallback_pattern: list[int | None] = [
        0x44,
        0x33,
        0x0D,
        None,
        None,
        None,
        None,
        0x44,
        0x33,
        0x0D,
        None,
        None,
        None,
        None,
        0x41,
        0x0F,
        0x1F,
        0xC1,
        0x44,
        0x8B,
        0x0A,
        0x4C,
        0x8B,
        0x05,
        None,
        None,
        None,
        None,
        0x4C,
        0x33,
        0x05,
        None,
        None,
        None,
        None,
        0x49,
        0x21,
        0xD0,
    ]
    fallback_patched_pattern = fallback_pattern[:]
    fallback_patched_pattern[14:18] = [0x90, 0x90, 0x90, 0x90]

    fallback2_pattern: list[int | None] = [
        0x44,
        0x33,
        0x05,
        None,
        None,
        None,
        None,
        0x44,
        0x33,
        0x05,
        None,
        None,
        None,
        None,
        0x45,
        0x21,
        0xC1,
        0x41,
        0x0F,
        0x1F,
        0xC1,
        0x44,
        0x8B,
        0x0A,
        0x49,
        0x89,
        0xD0,
        0x49,
        0xF7,
        0xD0,
    ]
    fallback2_patched_pattern = fallback2_pattern[:]
    fallback2_patched_pattern[17:21] = [0x90, 0x90, 0x90, 0x90]

    original_hits = find_masked_in_section(pe, data, pattern, ".tvm0")
    patched_hits = find_masked_in_section(pe, data, patched_pattern, ".tvm0")
    if original_hits:
        if len(original_hits) != 1:
            session.warn(f"GameAssembly Rosetta NOP signature matched {len(original_hits)} times; skipping")
            return
        patch_offset = original_hits[0] + 12
        print(f"GameAssembly.dll: patching Rosetta NOP at file+0x{patch_offset:x}")
        data[patch_offset : patch_offset + 4] = b"\x90\x90\x90\x90"
        session.write(path, data)
    elif patched_hits:
        print("GameAssembly.dll: Rosetta NOP already patched")
    else:
        fallback_hits = find_masked_in_section(pe, data, fallback_pattern, ".tvm0")
        fallback_patched_hits = find_masked_in_section(pe, data, fallback_patched_pattern, ".tvm0")
        if fallback_hits:
            if len(fallback_hits) != 1:
                session.warn(f"GameAssembly Rosetta NOP fallback signature matched {len(fallback_hits)} times; skipping")
                return
            patch_offset = fallback_hits[0] + 14
            print(f"GameAssembly.dll: patching Rosetta NOP fallback at file+0x{patch_offset:x}")
            data[patch_offset : patch_offset + 4] = b"\x90\x90\x90\x90"
            session.write(path, data)
        elif fallback_patched_hits:
            print("GameAssembly.dll: Rosetta NOP fallback already patched")
        else:
            fallback2_hits = find_masked_in_section(pe, data, fallback2_pattern, ".tvm0")
            fallback2_patched_hits = find_masked_in_section(pe, data, fallback2_patched_pattern, ".tvm0")
            if fallback2_hits:
                if len(fallback2_hits) != 1:
                    session.warn(f"GameAssembly Rosetta NOP fallback2 signature matched {len(fallback2_hits)} times; skipping")
                    return
                patch_offset = fallback2_hits[0] + 17
                print(f"GameAssembly.dll: patching Rosetta NOP fallback2 at file+0x{patch_offset:x}")
                data[patch_offset : patch_offset + 4] = b"\x90\x90\x90\x90"
                session.write(path, data)
            elif fallback2_patched_hits:
                print("GameAssembly.dll: Rosetta NOP fallback2 already patched")
            else:
                session.warn("GameAssembly Rosetta NOP signature not found")


def main() -> int:
    parser = argparse.ArgumentParser(description="Reapply local PGR Wine/Rosetta patches")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="PGR install directory; defaults to this script's directory",
    )
    parser.add_argument("--dry-run", action="store_true", help="validate and print actions without writing files")
    args = parser.parse_args()

    root = args.root.resolve()
    session = PatchSession(root, args.dry_run)
    print(f"PGR patch root: {root}")
    if args.dry_run:
        print("Dry run: no files will be modified")

    try:
        patch_pgrbase(session)
        patch_gameassembly(session)
    except Exception as exc:  # Keep failures readable for post-update triage.
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if session.changed:
        print("Changed files:")
        for path in sorted(session.changed):
            print(f"  {path.name}")
        print(f"Backups: {session.backup_dir}")
    else:
        print("No file changes needed")
    if session.warnings:
        print("Warnings need review before assuming the update is fully patched.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
