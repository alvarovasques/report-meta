from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Lê o .env (nunca versionado). Nomes iguais aos do .env.example."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    meta_graph_version: str = "v24.0"
    meta_app_id: str
    meta_app_secret: str = ""
    meta_system_user_token: str = ""
    meta_system_user_token_file: str = "/run/secrets/meta_system_user_token"
    meta_business_id: str
    meta_page_id: str
    meta_ig_user_id: str
    meta_ad_account_id: str  # act_XXXX
    report_timezone: str = "America/Campo_Grande"
    ads_attribution_windows: str = "7d_click,1d_view"
    database_url: str = Field(default="postgresql://report:report@localhost:5432/report_meta")

    def model_post_init(self, __context) -> None:  # noqa: D401
        """Token pode vir de Docker secret em vez de variável de ambiente."""
        if not self.meta_system_user_token:
            try:
                with open(self.meta_system_user_token_file, encoding="utf-8") as f:
                    self.meta_system_user_token = f.read().strip()
            except OSError:
                pass

    @property
    def graph_base(self) -> str:
        return f"https://graph.facebook.com/{self.meta_graph_version}"


settings = Settings()
