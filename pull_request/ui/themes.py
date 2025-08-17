from pydantic_settings import BaseSettings, SettingsConfigDict

class BoardTheme(BaseSettings):
    light_square_color: str
    dark_square_color: str
    piece_color_white: str
    piece_color_black: str

    model_config = SettingsConfigDict(extra="ignore")

# Predefined board themes
BOARD_THEMES = {
    "default": BoardTheme(
        light_square_color="#EEEED2",
        dark_square_color="#769656",
        piece_color_white="bold white",
        piece_color_black="black",
    ),
    "high_contrast_light": BoardTheme(
        light_square_color="#FFFFFF",
        dark_square_color="#000000",
        piece_color_white="bold blue",
        piece_color_black="bold yellow",
    ),
    "high_contrast_dark": BoardTheme(
        light_square_color="#000000",
        dark_square_color="#FFFFFF",
        piece_color_white="bold blue",
        piece_color_black="bold yellow",
    ),
    "colorblind_red_green": BoardTheme(
        light_square_color="#F0E68C",  # Khaki
        dark_square_color="#8B0000",  # DarkRed
        piece_color_white="bold white",
        piece_color_black="bold black",
    ),
}
