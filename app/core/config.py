from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Resume Verification Engine"
    GEMINI_API_KEY: str = ""
    GOOGLE_SEARCH_API_KEY: str = ""
    GOOGLE_SEARCH_CX: str = "764e6f71f8ee04846"
    GITHUB_TOKEN: str = ""  # Optional

    class Config:
        env_file = ".env"

settings = Settings()
