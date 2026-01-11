import re
import json
from sys import exit
from pathlib import Path
from src import repository, gh

def convert_title(text):
    if not text or not isinstance(text, str):
        return text
    return re.sub(
        r'\b([a-z0-9]+(?:-[a-z0-9]+)*)\b',
        lambda m: m.group(1).replace('-', ' ').title(),
        text,
        flags=re.IGNORECASE
    )

def extract_version(file_path):
    if not file_path:
        return 'unknown'
    path = Path(file_path)
    base_name = path.stem
    match = re.search(r'(\d+\.\d+\.\d+(-[a-z]+\.\d+)?(-release\d*)?)', base_name)
    return match.group(1) if match else 'unknown'

def create_github_release(name, patches_name, cli_name, apk_file_path):
    patchver = extract_version(patches_name)
    cliver = extract_version(cli_name)
    tag_name = f"{name}-v{patchver}"

    apk_path = Path(apk_file_path)
    if not apk_path.exists():
        exit(1)

    repo = gh.get_repo(repository)

    # Step 1: Check for existing release with the exact tag name
    try:
        existing_release = repo.get_release(tag_name)
    except:
        existing_release = None

    # Step 2: Delete existing assets if same APK already uploaded
    if existing_release:
        for asset in existing_release.get_assets():
            if asset.name == apk_path.name:
                asset.delete_asset()

    # Step 3: Delete old releases with the same base name and matching version suffix
    releases = list(repo.get_releases())

    suffix_match = re.search(r'(-[a-z]+\.\d+)$', patchver)
    current_suffix = suffix_match.group(1) if suffix_match else ''

    for release in releases:
        release_tag = release.tag_name
        if release_tag.startswith(f"{name}-v") and release_tag != tag_name:
            old_version = release_tag[len(name) + 2:]
            old_suffix_match = re.search(r'(-[a-z]+\.\d+)$', old_version)
            old_suffix = old_suffix_match.group(1) if old_suffix_match else ''

            if old_suffix == current_suffix:
                old_numeric = re.sub(r'(-[a-z]+\.\d+)?(-release\d*)?$', '', old_version)
                current_numeric = re.sub(r'(-[a-z]+\.\d+)?(-release\d*)?$', '', patchver)
                if old_numeric < current_numeric:
                    release.delete_release()

    # Step 4: Create new release if it doesn't exist
    if not existing_release:
        release_body = f"""\
# Release Notes

## Build Tools:
- **ReVanced Patches:** v{patchver}
- **ReVanced CLI:** v{cliver}

## Note:
**ReVanced GmsCore** is **necessary** to work. 
- Please **download** it from [HERE](https://github.com/revanced/gmscore/releases/latest).
"""
        release_name = f"{convert_title(name)} v{patchver}"
        existing_release = repo.create_git_release(
            tag=tag_name,
            name=release_name,
            message=release_body,
            draft=False,
            prerelease=False
        )

    # Step 5: Upload APK
    existing_release.upload_asset(
        path=str(apk_path),
        label=apk_path.name,
        content_type='application/vnd.android.package-archive'
    )
