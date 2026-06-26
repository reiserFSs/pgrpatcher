<img width="1391" height="313" alt="image" src="https://github.com/user-attachments/assets/57261abf-56ab-4500-b0b8-cf528d14e1c6" />

# PGR Local Wine Patcher

A local patcher for making Punishing: Gray Raven playable through Sikarugir/Wine. 

## What It Patches

- `PGRBase.dll`
- Applies Rosetta-hostile NOP instruction fix.
- Applies Unity startup stub used to bypass the ACE bootstrap/download path.
- Uses PE import/export parsing so the Unity stub patch is not tied to one fixed export file offset.

- `GameAssembly.dll`
- Applies Rosetta-hostile NOP instruction fix.

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

## Current Wine 10 Notes

Everything working as expected, including Google OAUTH, store etc. On startup you'll get a blank KRSDKExternal.exe window (caused by using decrypted internal dev flags and stubs) which you can ignore. Do not close the window or try to move it offscreen through Wine, it'll freeze the main PGR.EXE process. 

Note: You will need to include GStreamer into your Wine Env or else the game trying to play back Criware videos will crash the client. 

Performance: 80-120fps on a M4 Pro using DXVK, but performance is roughly 5-10% better using D3Metal so I rec. using that renderer. 

<img width="1906" height="1063" alt="Screenshot 2026-05-26 at 17 39" src="https://github.com/user-attachments/assets/0c10ce84-ddab-47df-b3bf-018209cd7083" />

## Current Wine 11 Notes

Preffered Wine Runtime. Near native startup time, no KRSDK window, performance and better controller support. You can use Crossover's Wine 11 Runtime with your existing Sikarugir Bottle using this prefix (change paths where needed):

```
CX_APPLEGPTK_LIBD3DSHARED_PATH="/Applications/CrossOver.app/Contents/SharedSupport/CrossOver/lib64/apple_gptk/external/libd3dshared.dylib" CX_GRAPHICS_BACKEND="d3dmetal" CX_ROOT="/Applications/CrossOver.app/Contents/SharedSupport/CrossOver" CX_WINELOADER="/Applications/CrossOver.app/Contents/SharedSupport/CrossOver/bin/wineloader" DYLD_FALLBACK_LIBRARY_PATH="/Applications/CrossOver.app/Contents/SharedSupport/CrossOver/lib64:/Applications/CrossOver.app/Contents/SharedSupport/CrossOver/lib" GST_PLUGIN_PATH_1_0="/Applications/CrossOver.app/Contents/SharedSupport/CrossOver/lib64/gstreamer-1.0" GST_PLUGIN_SYSTEM_PATH="/Applications/CrossOver.app/Contents/SharedSupport/CrossOver/lib64/gstreamer-1.0" GST_PLUGIN_SYSTEM_PATH_1_0="/Applications/CrossOver.app/Contents/SharedSupport/CrossOver/lib64/gstreamer-1.0" GST_REGISTRY="/Volumes/Lucia/PGR-native-research/logs/starter/gstreamer/crossover-gstreamer-registry.x86_64.bin" MTL_HUD_ENABLED="1" WINED3DMETAL="1" WINEDEBUG="-all" WINEDLLOVERRIDES="d3d11,dxgi=n,b" WINEDLLPATH="/Applications/CrossOver.app/Contents/SharedSupport/CrossOver/lib/dxmt:/Applications/CrossOver.app/Contents/SharedSupport/CrossOver/lib/wine" WINEDLLPATH_PREPEND="/Applications/CrossOver.app/Contents/SharedSupport/CrossOver/lib/dxmt" WINEESYNC="0" WINEFSYNC="0" WINELOADER="/Applications/CrossOver.app/Contents/SharedSupport/CrossOver/bin/wineloader" WINEMSYNC="0" WINEPREFIX="/Users/reiserfs/Applications/Sikarugir/Steam.app/Contents/SharedSupport/prefix" WINESERVER="/Applications/CrossOver.app/Contents/SharedSupport/CrossOver/bin/wineserver" /Applications/CrossOver.app/Contents/SharedSupport/CrossOver/bin/wineloader PGR.exe
```

## Recovery

If a patch causes trouble, restore the relevant DLL from the newest backup in `patch_backups/`.

Example:

```bash
cp -p "patch_backups/YYYYMMDD-HHMMSS/PGRBase.dll" "PGRBase.dll"
cp -p "patch_backups/YYYYMMDD-HHMMSS/GameAssembly.dll" "GameAssembly.dll"
```
