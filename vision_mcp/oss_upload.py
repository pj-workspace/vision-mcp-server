"""DashScope temporary file upload: getPolicy -> POST OSS -> oss:// URL."""

from __future__ import annotations

from pathlib import Path

import requests

UPLOADS_URL = "https://dashscope.aliyuncs.com/api/v1/uploads"


class OssUploadError(Exception):
    """Failed to obtain policy or upload file."""


def get_upload_policy(api_key: str, model_name: str) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
    }
    params = {"action": "getPolicy", "model": model_name}
    response = requests.get(UPLOADS_URL, headers=headers, params=params, timeout=60)
    if response.status_code != 200:
        raise OssUploadError(f"getPolicy failed: {response.status_code} {response.text}")
    body = response.json()
    data = body.get("data")
    if not isinstance(data, dict):
        raise OssUploadError(f"getPolicy invalid response: {body}")
    return data


def upload_file_to_oss(policy_data: dict, file_path: str | Path) -> str:
    path = Path(file_path)
    if not path.is_file():
        raise OssUploadError(f"not a file: {path}")

    file_name = path.name
    upload_dir = policy_data["upload_dir"]
    key = f"{upload_dir}/{file_name}"

    with path.open("rb") as fh:
        files = {
            "OSSAccessKeyId": (None, policy_data["oss_access_key_id"]),
            "Signature": (None, policy_data["signature"]),
            "policy": (None, policy_data["policy"]),
            "x-oss-object-acl": (None, policy_data["x_oss_object_acl"]),
            "x-oss-forbid-overwrite": (None, policy_data["x_oss_forbid_overwrite"]),
            "key": (None, key),
            "success_action_status": (None, "200"),
            "file": (file_name, fh),
        }
        upload_host = policy_data["upload_host"]
        response = requests.post(upload_host, files=files, timeout=120)

    if response.status_code != 200:
        raise OssUploadError(f"OSS upload failed: {response.status_code} {response.text}")

    return f"oss://{key}"


def upload_file_and_get_url(api_key: str, model_name: str, file_path: str | Path) -> str:
    policy = get_upload_policy(api_key, model_name)
    return upload_file_to_oss(policy, file_path)
