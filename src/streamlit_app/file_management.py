# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
File management for Streamlit web interface.

This module handles uploaded PDF files, including:
- File hashing for duplicate detection
- Manifest file management (tracking all uploaded files)
- Upload directory management
- File metadata tracking

The manifest file stores metadata about all uploaded PDFs to enable:
- Duplicate detection (by SHA256 hash)
- File selection from previously uploaded files
- Upload history tracking
"""

import hashlib
import json
from pathlib import Path

# Upload directory and manifest configuration
UPLOAD_DIR = Path("tmp/uploaded")
MANIFEST_FILE = UPLOAD_DIR / ".manifest.json"


def calculate_file_hash(file_bytes: bytes) -> str:
    """
    Calculate SHA256 hash of file content for duplicate detection.

    Args:
        file_bytes: Raw bytes of the file

    Returns:
        SHA256 hash as hexadecimal string

    Example:
        >>> with open("paper.pdf", "rb") as f:
        ...     file_hash = calculate_file_hash(f.read())
        >>> print(file_hash)
        'a1b2c3d4e5f6...'
    """
    return hashlib.sha256(file_bytes).hexdigest()


def load_manifest() -> dict:
    """
    Load manifest file containing metadata of all uploaded files.

    Returns:
        Dictionary with "files" key containing list of file metadata dicts.
        Returns empty structure if manifest doesn't exist or is invalid.

    Example:
        >>> manifest = load_manifest()
        >>> print(f"Found {len(manifest['files'])} uploaded files")
        Found 5 uploaded files
    """
    if MANIFEST_FILE.exists():
        try:
            with open(MANIFEST_FILE) as f:
                return json.load(f)
        except Exception:
            # Return empty structure if manifest is corrupted
            return {"files": []}
    return {"files": []}


def save_manifest(manifest: dict):
    """
    Save manifest file with updated file metadata.

    Args:
        manifest: Dictionary with "files" key containing file metadata list

    Note:
        Creates UPLOAD_DIR if it doesn't exist.

    Example:
        >>> manifest = load_manifest()
        >>> manifest["files"].append(new_file_info)
        >>> save_manifest(manifest)
    """
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_FILE, "w") as f:
        json.dump(manifest, f, indent=2)


def find_duplicate_by_hash(file_hash: str) -> dict | None:
    """
    Check if a file with this hash already exists in the manifest.

    Args:
        file_hash: SHA256 hash of file to check

    Returns:
        File info dictionary if duplicate found and file still exists,
        None otherwise

    Example:
        >>> file_hash = calculate_file_hash(uploaded_file.getvalue())
        >>> duplicate = find_duplicate_by_hash(file_hash)
        >>> if duplicate:
        ...     print(f"Duplicate: {duplicate['original_name']}")
    """
    manifest = load_manifest()
    for file_info in manifest["files"]:
        if file_info.get("hash") == file_hash:
            # Verify file still exists on disk
            if Path(file_info["path"]).exists():
                return file_info
    return None


def add_file_to_manifest(file_info: dict):
    """
    Add a new file entry to the manifest.

    Args:
        file_info: Dictionary with file metadata including:
            - hash: SHA256 hash of file content
            - path: Full path to saved file
            - original_name: Original filename from upload
            - size_mb: File size in megabytes
            - upload_time: ISO format timestamp

    Example:
        >>> file_info = {
        ...     "hash": "a1b2c3...",
        ...     "path": "tmp/uploaded/20250109_120000_paper.pdf",
        ...     "original_name": "paper.pdf",
        ...     "size_mb": 2.5,
        ...     "upload_time": "2025-01-09T12:00:00"
        ... }
        >>> add_file_to_manifest(file_info)
    """
    manifest = load_manifest()
    manifest["files"].append(file_info)
    save_manifest(manifest)


def get_uploaded_files() -> list[dict]:
    """
    Get list of all previously uploaded files from manifest.

    Automatically filters out files that no longer exist on disk
    and updates the manifest if any files were removed.

    Returns:
        List of file info dictionaries for files that still exist

    Example:
        >>> files = get_uploaded_files()
        >>> for file in files:
        ...     print(f"{file['original_name']} - {file['upload_time']}")
        paper1.pdf - 2025-01-09T12:00:00
        paper2.pdf - 2025-01-09T13:00:00
    """
    manifest = load_manifest()

    # Filter out files that no longer exist on disk
    existing_files = [f for f in manifest["files"] if Path(f["path"]).exists()]

    # Update manifest if any files were removed
    if len(existing_files) != len(manifest["files"]):
        manifest["files"] = existing_files
        save_manifest(manifest)

    return existing_files
