# PGR Local Wine Patcher

Contains a local patcher for keeping Punishing: Gray Raven playable through Sikarugir/Wine after game updates.

## What It Patches

- `PGRBase.dll`
- Reapplies the Rosetta-hostile NOP instruction fix.
- Reinstalls the Unity startup stub used to bypass the ACE bootstrap/download path.
- Uses PE import/export parsing so the Unity stub patch is not tied to one fixed export file offset.

- `GameAssembly.dll`
- Reapplies the known Rosetta-hostile NOP instruction fix.

- `PGR.exe`
- Not modified.

## Usage

Put the the patcher into your Steam/SteamLibrary/steamapps/common/Punishing Gray Raven director and run it from bash:

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

The game has separate Wine/Unity registry state for window size. The current working setup uses normal windowed mode at `1920x1080`, with Wine Retina mode disabled.

Virtual desktop mode is intentionally not enabled because it made the game window harder to move.

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
