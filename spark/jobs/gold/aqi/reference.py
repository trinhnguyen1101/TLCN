"""1459/QĐ-TCMT (2019), table 2. All concentrations in ug/m3."""
METHOD_VERSION = "vn-aqi-1459-2019-project-v1"
REFERENCE_SHA256 = "968c4cbb9bf5cf03e4a9bf30850afd8695d130f767324ac57ca02e2d54a48c26"
REFERENCE_URL = "https://vea.mae.gov.vn/Data/files/QD%201459%20TCMT%20ngay%2012_11_2019%20AQI%281%29.pdf"
INDICES = (0, 50, 100, 150, 200, 300, 400, 500)
BREAKPOINTS = {
    "pm25": (0, 25, 50, 80, 150, 250, 350, 500),
    "pm10": (0, 50, 150, 250, 350, 420, 500, 600),
    "so2": (0, 125, 350, 550, 800, 1600, 2100, 2630),
    "no2": (0, 100, 200, 700, 1200, 2350, 3100, 3850),
    "co": (0, 10000, 30000, 45000, 60000, 90000, 120000, 150000),
    "o3": (0, 160, 200, 300, 400, 800, 1000, 1200),
    "o3_8h": (0, 100, 120, 170, 210, 400),
}
POLLUTANTS = ("pm25", "pm10", "so2", "no2", "co", "o3")
# Table 1 RGB, converted exactly to hex.
CATEGORIES = ((50, "good", "Tốt", "#00E400"),
              (100, "moderate", "Trung bình", "#FFFF00"),
              (150, "poor", "Kém", "#FF7E00"),
              (200, "unhealthy", "Xấu", "#FF0000"),
              (300, "very_unhealthy", "Rất xấu", "#8F3F97"),
              (500, "hazardous", "Nguy hại", "#7E0023"))
PROFILES = ("station_reference", "model_estimate", "area_estimate", "proxy_estimate")
