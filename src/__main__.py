import json
import logging
import re
from sys import exit
from pathlib import Path
from os import getenv
import subprocess
from src import (
    r2,
    utils,
    release,
    downloader
)

def run_build(app_name: str, source: str, arch: str = "universal") -> str:
    """Build APK for specific architecture"""
    download_files, name = downloader.download_required(source)

    revanced_cli = utils.find_file(download_files, 'revanced-cli', '.jar')
    revanced_patches = next((f for f in download_files if f.suffix == '.rvp'), None)

    # Detect patch version for logging purposes only
    if revanced_patches:
        version_match = re.search(r'(\d+\.\d+(\.\d+)?)', revanced_patches.name)
        if version_match:
            version_str = version_match.group(1)
            major_version = int(version_str.split('.')[0])
            if major_version >= 5:
                logging.info(f"Patches v{version_str} detected — using CLI v5+ compatible syntax")
            else:
                logging.info(f"Patches v{version_str} detected")
        else:
            logging.warning("Could not parse patches version from filename")

    download_methods = [
        downloader.download_apkmirror,
        downloader.download_apkpure,
        downloader.download_uptodown
    ]

    input_apk = None
    version = None
    for method in download_methods:
        try:
            input_apk, version = method(app_name, revanced_cli, revanced_patches)
            if input_apk:
                logging.info(f"✅ Successfully downloaded APK using {method.__name__}")
                break
        except FileNotFoundError as e:
            logging.debug(f"{method.__name__} config not found: {e}")
            continue
        except Exception as e:
            logging.warning(f"{method.__name__} failed: {e}")
            continue
            
    if input_apk is None:
        logging.error(f"❌ Failed to download APK for {app_name}")
        logging.error("All download sources failed. This likely means:")
        logging.error(f"  1. Missing config files in apps/apkmirror/, apps/apkpure/, or apps/uptodown/ for '{app_name}'")
        logging.error(f"  2. The app '{app_name}' is not supported by this patch source")
        logging.error(f"  3. Create config file: apps/{{platform}}/{app_name}.json with package and version info")
        return None

    # Additional safety check
    if not isinstance(input_apk, Path):
        logging.error(f"❌ Invalid APK path returned: {input_apk}")
        return None

    if input_apk.suffix != ".apk":
        logging.warning("Input file is not .apk, using APKEditor to merge")
        apk_editor = downloader.download_apkeditor()

        merged_apk = input_apk.with_suffix(".apk")

        utils.run_process([
            "java", "-jar", apk_editor, "m",
            "-i", str(input_apk),
            "-o", str(merged_apk)
        ], silent=True)

        input_apk.unlink(missing_ok=True)

        if not merged_apk.exists():
            logging.error("Merged APK file not found")
            exit(1)

        input_apk = merged_apk
        logging.info(f"Merged APK file generated: {input_apk}")

    # ARCHITECTURE-SPECIFIC PROCESSING
    if arch != "universal":
        logging.info(f"Processing APK for {arch} architecture...")
        
        # Remove unwanted architectures based on selected arch
        if arch == "arm64-v8a":
            # Remove x86, x86_64, and armeabi-v7a
            utils.run_process([
                "zip", "--delete", str(input_apk), 
                "lib/x86/*", "lib/x86_64/*", "lib/armeabi-v7a/*"
            ], silent=True, check=False)
        elif arch == "armeabi-v7a":
            # Remove x86, x86_64, and arm64-v8a
            utils.run_process([
                "zip", "--delete", str(input_apk),
                "lib/x86/*", "lib/x86_64/*", "lib/arm64-v8a/*"
            ], silent=True, check=False)
    else:
        # Universal: only remove x86 architectures
        utils.run_process([
            "zip", "--delete", str(input_apk), 
            "lib/x86/*", "lib/x86_64/*"
        ], silent=True, check=False)

    exclude_patches = []
    include_patches = []

    patches_path = Path("patches") / f"{app_name}-{source}.txt"
    if patches_path.exists():
        with patches_path.open('r') as patches_file:
            for line in patches_file:
                line = line.strip()
                if line.startswith('-'):
                    exclude_patches.extend(["-d", line[1:].strip()])
                elif line.startswith('+'):
                    include_patches.extend(["-e", line[1:].strip()])

    # FIX: Repair corrupted APK from Uptodown
    logging.info("Checking APK for corruption...")
    try:
        fixed_apk = Path(f"{app_name}-fixed-v{version}.apk")
        subprocess.run([
            "zip", "-FF", str(input_apk), "--out", str(fixed_apk)
        ], check=False, capture_output=True)
        
        if fixed_apk.exists() and fixed_apk.stat().st_size > 0:
            input_apk.unlink(missing_ok=True)
            fixed_apk.rename(input_apk)
            logging.info("APK fixed successfully")
    except Exception as e:
        logging.warning(f"Could not fix APK: {e}")

    # Include architecture in output filename
    output_apk = Path(f"{app_name}-{arch}-patch-v{version}.apk")

    # CRITICAL FIX: Use -p instead of --patches for CLI v5.0+
    # The CLI v5.0+ uses -p flag, while v4.x used --patches
    patch_command = [
        "java", "-jar", str(revanced_cli),
        "patch", "-p", str(revanced_patches),  # Changed from --patches to -p
        "-e", "Hide ADB",
        "--out", str(output_apk), str(input_apk),
        *exclude_patches, *include_patches
    ]
    
    logging.info(f"Running patch command with CLI v5+ syntax...")
    
    utils.run_process(patch_command, stream=True)

    input_apk.unlink(missing_ok=True)

    # Include architecture in final signed APK name
    signed_apk = Path(f"{app_name}-{arch}-{name}-v{version}.apk")

    apksigner = utils.find_apksigner()
    if not apksigner:
        exit(1)

    try:
        utils.run_process([
            str(apksigner), "sign", "--verbose",
            "--ks", "keystore/public.jks",
            "--ks-pass", "pass:public",
            "--key-pass", "pass:public",
            "--ks-key-alias", "public",
            "--in", str(output_apk), "--out", str(signed_apk)
        ], stream=True)
    except Exception as e:
        logging.warning(f"Standard signing failed: {e}")
        logging.info("Trying alternative signing method...")
        
        utils.run_process([
            str(apksigner), "sign", "--verbose",
            "--min-sdk-version", "21",
            "--ks", "keystore/public.jks",
            "--ks-pass", "pass:public",
            "--key-pass", "pass:public",
            "--ks-key-alias", "public",
            "--in", str(output_apk), "--out", str(signed_apk)
        ], stream=True)

    output_apk.unlink(missing_ok=True)
    print(f"✅ APK built: {signed_apk.name}")
    
    return str(signed_apk)

def main():
    app_name = getenv("APP_NAME")
    source = getenv("SOURCE")

    if not app_name or not source:
        logging.error("APP_NAME and SOURCE environment variables must be set")
        exit(1)

    # Read arch-config.json
    arch_config_path = Path("arch-config.json")
    if arch_config_path.exists():
        with open(arch_config_path) as f:
            arch_config = json.load(f)
        
        # Find arches for this app
        arches = ["universal"]  # default
        for config in arch_config:
            if config["app_name"] == app_name and config["source"] == source:
                arches = config["arches"]
                break
        
        # Build for each architecture
        built_apks = []
        for arch in arches:
            logging.info(f"🔨 Building {app_name} for {arch} architecture...")
            apk_path = run_build(app_name, source, arch)
            if apk_path:
                built_apks.append(apk_path)
                print(f"✅ Built {arch} version: {Path(apk_path).name}")
        
        # Summary
        if built_apks:
            print(f"\n🎯 Built {len(built_apks)} APK(s) for {app_name}:")
            for apk in built_apks:
                print(f"  📱 {Path(apk).name}")
        else:
            print(f"\n❌ Failed to build any APKs for {app_name}")
            exit(1)
        
    else:
        # Fallback to single universal build
        logging.warning("arch-config.json not found, building universal only")
        apk_path = run_build(app_name, source, "universal")
        if apk_path:
            print(f"🎯 Final APK path: {apk_path}")
        else:
            logging.error("Build failed")
            exit(1)

if __name__ == "__main__":
    main()
