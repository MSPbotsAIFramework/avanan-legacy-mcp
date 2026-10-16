# Copyright 2026 MSPbots.ai
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Process settings. Holds no credentials: those arrive per request as headers."""

from pydantic_settings import BaseSettings, SettingsConfigDict

API_VERSION = "v1.0"

# SmartAPI hosts per region. Client ID and secret are issued per region.
REGION_HOSTS: dict[str, str] = {
    "us": "smart-api-production-1-us.avanan.net",
    "eu": "smart-api-production-1-eu.avanan.net",
    "ca": "smart-api-production-1-ca.avanan.net",
    "ap": "smart-api-production-5-ap.avanan.net",
    "euw2": "smart-api-production-1-euw2.avanan.net",
    "aps1": "smart-api-production-1-aps1.avanan.net",
    "mec1": "smart-api-production-1-mec1.avanan.net",
}
DEFAULT_REGION = "us"

# Friendly spellings accepted in X-Avanan-Region.
REGION_ALIASES: dict[str, str] = {
    **{code: code for code in REGION_HOSTS},
    "usa": "us",
    "europe": "eu",
    "canada": "ca",
    "au": "ap",
    "australia": "ap",
    "uk": "euw2",
    "in": "aps1",
    "india": "aps1",
    "uae": "mec1",
}


def resolve_region(value: str | None) -> str | None:
    """Region code for a header value; DEFAULT_REGION when blank, None when unknown."""
    text = (value or "").strip().lower()
    if not text:
        return DEFAULT_REGION
    return REGION_ALIASES.get(text)


class Settings(BaseSettings):
    # extra="ignore": the runtime injects variables this project does not declare.
    model_config = SettingsConfigDict(extra="ignore")

    mcp_http_port: int = 8080
    mcp_http_host: str = "0.0.0.0"
    log_level: str = "INFO"


def get_settings() -> Settings:
    return Settings()
