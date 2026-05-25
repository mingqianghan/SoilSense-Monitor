import requests
from datetime import datetime, timedelta
import numpy as np

class WeatherSummary:
    def __init__(self, lat, lon, api_key):
        self.lat = lat
        self.lon = lon
        self.api_key = api_key
        self.base_url = "https://api.openweathermap.org/data/3.0/onecall"
        self.day_summary_url = "https://api.openweathermap.org/data/3.0/onecall/day_summary"
        self.units = 'metric'  # Change to 'imperial' for Fahrenheit
        self.past_week_summary = None
        self.next_week_summary = None
        self.current_weather_summary = None

    def get_past_week_data(self, date):
        url = f"{self.day_summary_url}"
        params = {
            'lat': self.lat,
            'lon': self.lon,
            'date': date,
            'appid': self.api_key,
            'units': self.units
        }

        return self.fetch_data(url, params)

    def generate_past_week_summary(self):
        past_week_data = []
        current_date = datetime.now()

        # Loop to get data for the past 7 days
        for day in range(7):
            date = (current_date - timedelta(days=day)).strftime('%Y-%m-%d')
            data = self.get_past_week_data(date)
            if data:
                past_week_data.append(data)
                
        # Generate a summary from the collected data
        if past_week_data:
            highest_temp = max(day['temperature']['max'] for day in past_week_data if 'temperature' in day and 'max' in day['temperature'])
            lowest_temp = min(day['temperature']['min'] for day in past_week_data if 'temperature' in day and 'min' in day['temperature'])
            avg_temp = sum((day['temperature']['morning'] + day['temperature']['afternoon'] + day['temperature']['evening'] + day['temperature']['night']) / 4 for day in past_week_data if 'temperature' in day and all(key in day['temperature'] for key in ['morning', 'afternoon', 'evening', 'night'])) / len(past_week_data)
            highest_humidity = max(day['humidity']['afternoon'] for day in past_week_data if 'humidity' in day and 'afternoon' in day['humidity'])
            lowest_humidity = min(day['humidity']['afternoon'] for day in past_week_data if 'humidity' in day and 'afternoon' in day['humidity'])
            avg_humidity = sum(day['humidity']['afternoon'] for day in past_week_data if 'humidity' in day and 'afternoon' in day['humidity']) / len(past_week_data)
            avg_wind_speed = sum(day['wind']['max']['speed'] for day in past_week_data if 'wind' in day and 'max' in day['wind'] and 'speed' in day['wind']['max']) / len(past_week_data)
            total_rainfall = sum(day['precipitation']['total'] for day in past_week_data if 'precipitation' in day and 'total' in day['precipitation'])

            self.past_week_summary = {
                'highest_temp': highest_temp,
                'lowest_temp': lowest_temp,
                'avg_temp': avg_temp,
                'highest_humidity': highest_humidity,
                'lowest_humidity': lowest_humidity,
                'avg_humidity': avg_humidity,
                'avg_wind_speed': avg_wind_speed,
                'total_rainfall': total_rainfall
            }
        else:
            self.past_week_summary = {
                'highest_temp': np.nan,
                'lowest_temp': np.nan,
                'avg_temp': np.nan,
                'highest_humidity': np.nan,
                'lowest_humidity': np.nan,
                'avg_humidity': np.nan,
                'avg_wind_speed': np.nan,
                'total_rainfall': np.nan
            }
                

    def get_next_week_forecast(self):
        url = f"{self.base_url}"
        params = {
            'lat': self.lat,
            'lon': self.lon,
            'exclude': 'minutely,hourly,current',
            'appid': self.api_key,
            'units': self.units
        }
        
        return self.fetch_data(url, params)


    def generate_next_week_summary(self):
        forecast_data = self.get_next_week_forecast()

        if forecast_data and 'daily' in forecast_data:
            daily_data = forecast_data['daily'][:7]

            highest_temp = max(day['temp']['max'] for day in daily_data if 'temp' in day and 'max' in day['temp'])
            lowest_temp = min(day['temp']['min'] for day in daily_data if 'temp' in day and 'min' in day['temp'])
            avg_temp = sum((day['temp']['day'] for day in daily_data if 'temp' in day and 'day' in day['temp'])) / len(daily_data)
            highest_humidity = max(day['humidity'] for day in daily_data if 'humidity' in day)
            lowest_humidity = min(day['humidity'] for day in daily_data if 'humidity' in day)
            avg_humidity = sum(day['humidity'] for day in daily_data if 'humidity' in day) / len(daily_data)
            avg_wind_speed = sum(day['wind_speed'] for day in daily_data if 'wind_speed' in day) / len(daily_data)
            total_rainfall = sum(day.get('rain', 0) for day in daily_data)

            self.next_week_summary = {
                'highest_temp': highest_temp,
                'lowest_temp': lowest_temp,
                'avg_temp': avg_temp,
                'highest_humidity': highest_humidity,
                'lowest_humidity': lowest_humidity,
                'avg_humidity': avg_humidity,
                'avg_wind_speed': avg_wind_speed,
                'total_rainfall': total_rainfall
            }
        else:
            self.next_week_summary = {
                'highest_temp': np.nan,
                'lowest_temp': np.nan,
                'avg_temp': np.nan,
                'highest_humidity': np.nan,
                'lowest_humidity': np.nan,
                'avg_humidity': np.nan,
                'avg_wind_speed': np.nan,
                'total_rainfall': np.nan
            }


    def get_current_weather(self):
        url = f"{self.base_url}"
        params = {
            'lat': self.lat,
            'lon': self.lon,
            'exclude': 'minutely,hourly,daily,alerts',
            'appid': self.api_key,
            'units': self.units
        }
        return self.fetch_data(url, params)
        

    def generate_current_weather_summary(self):
        current_data = self.get_current_weather()

        if current_data and 'current' in current_data:
            current_weather = current_data['current']
            temp = current_weather['temp']
            humidity = current_weather['humidity']
            wind_speed = current_weather['wind_speed']
            weather_description = current_weather['weather'][0]['description']
            icon_code = current_weather['weather'][0]['icon']
            icon_url = f"http://openweathermap.org/img/wn/{icon_code}@2x.png"

            self.current_weather_summary = {
                'temp': temp,
                'humidity': humidity,
                'wind_speed': wind_speed,
                'weather_description': weather_description,
                'icon_url': icon_url
            }
        else:
            self.current_weather_summary = {
                'temp': np.nan,
                'humidity': np.nan,
                'wind_speed': np.nan,
                'weather_description': 'N/A',
                'icon_url': '-'
            }
                
            
    def fetch_data(self, url, params, retries=3):
        """Attempts to fetch data with retries if there is no internet connection."""
        for attempt in range(retries):
            try:
                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()  # Raise an error for HTTP errors (e.g., 404, 500)
                return response.json()  # or response.text if expecting non-JSON data
            except requests.exceptions.ConnectionError:
                print(f"Connection error. Retrying ...")
                #time.sleep(delay)
            except requests.exceptions.Timeout:
                print("Request timed out. Please check your network.")
                break
            except requests.exceptions.RequestException as e:
                print(f"Request failed: {e}")
                break
        return None  # Return None or a fallback value if all retries fail
            