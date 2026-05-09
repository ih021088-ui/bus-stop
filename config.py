from dotenv import load_dotenv
import os

load_dotenv()

PUBLIC_DATA_API_KEY = os.getenv("PUBLIC_DATA_API_KEY", "")

# 기상청 단기예보
WEATHER_API_KEY = PUBLIC_DATA_API_KEY

# 경기도 버스도착정보
BUS_API_KEY = PUBLIC_DATA_API_KEY
