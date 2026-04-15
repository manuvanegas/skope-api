from functools import lru_cache
from logging.config import dictConfig
from pathlib import Path
from typing import List, Optional, Tuple, Type
from pydantic import BaseModel
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
    PydanticBaseSettingsSource,
    YamlConfigSettingsSource,
)

import yaml
import logging


logger = logging.getLogger(__name__)

class Store(BaseModel):
    base_path: str
    template: str
    uncertainty_template: str


class Settings(BaseSettings):
    allowed_origins: List[str] = ["*"]
    environment: str = "dev"
    name: str = "SKOPE API Services (development)"
    base_uri: str = "timeseries"
    max_processing_time: int = 15000  # in milliseconds
    default_max_cells:int = 1000000  # max number of cells to extract from data cubes
    store: Store
    redis_url: Optional[str] = None
    sentry_dsn: str = "https://9b9dc2f60562380edeb675c39fe1c896@sentry.comses.net/4"
    tile_server_url: str
    storage_base_url: str

    model_config = SettingsConfigDict(yaml_file="config/app_settings.yml")

    @classmethod
    def create(cls):
        instance = Settings()
        with open(instance.logging_config_file) as f:
            dictConfig(yaml.safe_load(f))
        return instance

    @property
    def is_production(self):
        return self.environment == "prod"

    @property
    def logging_config_file(self):
        return "config/logging.yml"

    @property
    def registry_path(self):
        # return Path(f"deploy/metadata/{self.environment}.yml")
        return Path("metadata.yml")

    def _get_path(self, template, dataset_id, variable_id):
        base = Path(self.store.base_path).resolve()
        path = Path(
            template.format(dataset_id=dataset_id, variable_id=variable_id)
        ).resolve()
        try:
            path.relative_to(base)
        except ValueError as e:
            logger.warning(
                "path traversal detected: base path %s, data path %s", base, path
            )
            raise e
        return path

    def get_dataset_path(self, dataset_id: str, variable_id: str) -> Path:
        return self._get_path(
            template=self.store.template, dataset_id=dataset_id, variable_id=variable_id
        )

    def get_uncertainty_dataset_path(self, dataset_id: str, variable_id: str) -> Path:
        return self._get_path(
            template=self.store.uncertainty_template,
            dataset_id=dataset_id,
            variable_id=variable_id,
        )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            YamlConfigSettingsSource(settings_cls),
            env_settings,
            file_secret_settings,
        )

@lru_cache()
def get_settings():
    return Settings.create()
