<img width="769" height="169" alt="Screenshot 2026-05-26 at 13 45 39" src="https://github.com/user-attachments/assets/7ca5577c-11d0-4e3a-9856-efd0a2e677f5" />

# PGR Local Wine Patcher

A local patcher for making Punishing: Gray Raven playable through Sikarugir/Wine. Uses dev flags and ACE kernel stubs. 

## What It Patches

- `PGRBase.dll`
- Applies the Rosetta-hostile NOP instruction fix.
- Applies the Unity startup stub used to bypass the ACE bootstrap/download path.
- Uses PE import/export parsing so the Unity stub patch is not tied to one fixed export file offset.

- `GameAssembly.dll`
- Applies the known Rosetta-hostile NOP instruction fix.

- `PGR.exe`
- Not being modified. 

## Usage

Put the the patcher into your Steam/SteamLibrary/steamapps/common/Punishing Gray Raven and run it from bash:

```bash
./pgr_apply_patches.py
```

To check what it would do without changing files:

```bash
./pgr_apply_patches.py --dry-run
```

You can also point it at another copied install directory if you're using the Kuro Launcher version instead:

```bash
./pgr_apply_patches.py --root "/path/to/Punishing Gray Raven"
```

## Backups

Before modifying a DLL, the patcher creates timestamped backups under:

```text
patch_backups/YYYYMMDD-HHMMSS/
```

Only files that are actually modified are backed up.

## Expected Output

If the install is already patched, dry-run should look similar to:

```text
PGRBase.dll: Rosetta NOP already patched
PGRBase.dll: Unity startup stub already installed
GameAssembly.dll: Rosetta NOP already patched
No file changes needed
```

After a game update, successful patching should mention changed files:

```text
PGRBase.dll: patching Rosetta NOP ...
PGRBase.dll: installing Unity startup stub ...
GameAssembly.dll: patching Rosetta NOP ...
Changed files:
  GameAssembly.dll
  PGRBase.dll
```

If the script prints warnings, review them before assuming the updated game is fully patched. Warnings usually mean Kuro changed the binary enough that the old byte signature was not found safely.

## Current Wine Notes

Everything working as expected, including Google OAUTH, store etc. On startup you'll get a blank Kuro SDK window (caused by using decrypted internal dev flags and stubs) which you can ignore. 

Performance: 80-120fps on a M4 Pro using DXVK

## Important Files

- `pgr_apply_patches.py`: repeatable patcher.
- `PGRBase.dll`: active patched launcher-side DLL.
- `GameAssembly.dll`: active patched IL2CPP DLL.
- `PGR.exe`: should remain original and unmodified.
- `patch_backups/`: generated backups from patcher runs.

## Recovery

If a patch causes trouble, restore the relevant DLL from the newest backup in `patch_backups/`.

Example:

```bash
cp -p "patch_backups/YYYYMMDD-HHMMSS/PGRBase.dll" "PGRBase.dll"
cp -p "patch_backups/YYYYMMDD-HHMMSS/GameAssembly.dll" "GameAssembly.dll"
```
