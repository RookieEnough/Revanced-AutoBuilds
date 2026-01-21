import json
import logging
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
    revanced_patches = utils.find_file(download_files, 'patches', '.rvp')

    download_methods = [
        downloader.download_apkmirror,
        downloader.download_apkpure,
        downloader.download_uptodown
    ]

    input_apk = None
    version = None
    for method in download_methods:
        input_apk, version = method(app_name, revanced_cli, revanced_patches)
        if input_apk:
            break
            
    if input_apk is None:
        logging.error(f"❌ Failed to download APK for {app_name}")
        logging.error("All download sources failed. Skipping this app.")
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

    utils.run_process([
        "java", "-jar", str(revanced_cli),
        "patch", "--patches", str(revanced_patches),
        "--out", str(output_apk), str(input_apk),
        *exclude_patches, *include_patches
    ], stream=True)

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
        print(f"\n🎯 Built {len(built_apks)} APK(s) for {app_name}:")
        for apk in built_apks:
            print(f"  📱 {Path(apk).name}")
        
    else:
        # Fallback to single universal build
        logging.warning("arch-config.json not found, building universal only")
        apk_path = run_build(app_name, source, "universal")
        if apk_path:
            print(f"🎯 Final APK path: {apk_path}")

if __name__ == "__main__":
    main()
