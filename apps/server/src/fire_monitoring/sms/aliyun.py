from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime
from urllib.parse import quote

import httpx

from ..config.model import SmsSettings


def _percent(value: str) -> str:
    return quote(value, safe="~")


class AliyunSmsSender:
    endpoint = "https://dysmsapi.aliyuncs.com/"

    def __init__(self, settings: SmsSettings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self._client = client or httpx.Client(timeout=10)

    def send(self, phone: str, template_param: dict[str, str]) -> None:
        params = {
            "AccessKeyId": self.settings.access_key_id,
            "Action": "SendSms",
            "Format": "JSON",
            "PhoneNumbers": phone,
            "RegionId": "cn-hangzhou",
            "SignName": self.settings.sign_name,
            "SignatureMethod": "HMAC-SHA1",
            "SignatureNonce": uuid.uuid4().hex,
            "SignatureVersion": "1.0",
            "TemplateCode": self.settings.template_code,
            "TemplateParam": json.dumps(template_param, ensure_ascii=False),
            "Timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "Version": "2017-05-25",
        }
        canonical = "&".join(
            f"{_percent(key)}={_percent(params[key])}" for key in sorted(params)
        )
        string_to_sign = f"POST&{_percent('/')}&{_percent(canonical)}"
        digest = hmac.new(
            (self.settings.access_key_secret + "&").encode(),
            string_to_sign.encode(),
            hashlib.sha1,
        ).digest()
        params["Signature"] = base64.b64encode(digest).decode()
        response = self._client.post(self.endpoint, data=params)
        response.raise_for_status()
        body = response.json()
        if body.get("Code") != "OK":
            raise RuntimeError(body.get("Message") or body.get("Code") or "短信发送失败")
