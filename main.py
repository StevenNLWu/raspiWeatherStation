#!/usr/bin/python

from __future__ import print_function

import datetime
import os
import sys
import time
from urllib.parse import urlencode

from urllib.request import urlopen
from sense_hat import SenseHat

import pymongo
from pymongo import MongoClient
import json

from config import WuConfig
from config import MongoConfig

# enable or disable upload of Weather Underground
WU_WEATHER_UPLOAD = False
# how often to do upload
WU_MEASUREMENT_INTERVAL = 10  # minutes
# the weather underground URL used to upload weather data
WU_URL = "http://weatherstation.wunderground.com/weatherstation/updateweatherstation.php"

# enable or disable upload of MongoDB
MONGODB_UPLOAD = True
# how often to do upload
MEASUREMENT_INTERVAL = 1  # minutes

# some string constants
SINGLE_HASH = "#"
HASHES = "########################################"
SLASH_N = "\n"

# set up the colours
blue = [0, 0, 255]
green = [0, 255, 0]
red = [255, 0, 0]
empty = [0, 0, 0]

def c_to_f(input_temp):
    # convert input_temp from Celsius to Fahrenheit
    return (input_temp * 1.8) + 32

def get_currentTime_iso():
    return datetime.datetime.now().replace(microsecond=0).isoformat(),

def get_cpu_temp():
    # 'borrowed' from https://www.raspberrypi.org/forums/viewtopic.php?f=104&t=111457
    # executes a command at the OS to pull in the CPU temperature
    res = os.popen('vcgencmd measure_temp').readline()
    return float(res.replace("temp=", "").replace("'C\n", ""))

# use moving average to smooth readings
def get_smooth(x):
    # do we have the t object?
    if not hasattr(get_smooth, "t"):
        # then create it
        get_smooth.t = [x, x, x]
    # manage the rolling previous values
    get_smooth.t[2] = get_smooth.t[1]
    get_smooth.t[1] = get_smooth.t[0]
    get_smooth.t[0] = x
    # average the three last temperatures
    xs = (get_smooth.t[0] + get_smooth.t[1] + get_smooth.t[2]) / 3
    return xs

def get_temp():
    # ====================================================================
    # to do some approximation of the actual temp
    # taking CPU temp into account.
    # The Pi foundation recommende using the following:
    # http://yaab-arduino.blogspot.co.uk/2016/08/accurate-temperature-reading-sensehat.html
    # ====================================================================
    # First, get temp readings from both sensors
    t1 = sense.get_temperature_from_humidity()
    t2 = sense.get_temperature_from_pressure()
    # t becomes the average of the temperatures from both sensors
    t = (t1 + t2) / 2
    # Now, grab the CPU temperature
    t_cpu = get_cpu_temp()
    # Calculate the 'real' temperature compensating for CPU heating
    t_corr = t - ((t_cpu - t) / 1.5)
    # Finally, average out that value across the last three readings
    t_corr = get_smooth(t_corr)
    # convoluted, right?
    # Return the calculated temperature
    return t_corr

def main():

    # initialize the lastMinute variable to the current time to start
    last_minute = datetime.datetime.now().minute
    # on startup, just use the previous minute as lastMinute
    last_minute -= 1
    if last_minute == 0:
        last_minute = 59

    # rotate the HAT
    sense.set_rotation(180);

    # infinite loop to continuously check weather values
    while 1:
        # The temp measurement smoothing algorithm's accuracy is based
        # on frequent measurements, so we'll take measurements every 5 seconds
        # but only upload on measurement_interval
        current_second = datetime.datetime.now().second
        # are we at the top of the minute or at a 5 second interval?
        if (current_second == 0) or ((current_second % 5) == 0):
            # ========================================================
            # read values from the Sense HAT
            # ========================================================
            # Calculate the temperature; adjust the temp based on CPU's temp
            calc_temp = get_temp()
            # temp for our purposes
            temp_c = round(calc_temp, 1)
            temp_f = round(c_to_f(calc_temp), 1)
            # get humidity
            humidity = round(sense.get_humidity(), 0)
            # convert pressure from millibars to inHg before posting
            pressure = round(sense.get_pressure() * 0.0295300, 1)
            
            # display on console
            print(str(get_currentTime_iso())
                    + ": "
                    + "Temp: %sF (%sC), Pressure: %s inHg, Humidity: %s%%" % (temp_f, temp_c, pressure, humidity)
                )
            # display the temp using the HAT's LED light
            msg = "%sC"% (temp_c)
            sense.show_message(msg, scroll_speed=0.1, text_colour=green)

            # ========================================================
            # Upload weather data
            # ========================================================
            # check every mins
            current_minute = datetime.datetime.now().minute
            if current_minute != last_minute:
                last_minute = current_minute
                
                # ========================================================
                # Upload weather data to mongoDB
                # ========================================================
                # time to upload? (do upload every MEASUREMENT_INTERVAL min)
                if (current_minute == 0) or ((current_minute % MEASUREMENT_INTERVAL) == 0):
                     if MONGODB_UPLOAD:
                        
                        # our weather data
                        weather_data = {
                            "temperature": str(temp_c),
                            "humidity": str(humidity),
                            "pressure": str(pressure),
                            "device": os.uname()[1],
                            "uploadDatetime": get_currentTime_iso(),
                        }
                    
                        # connection to DB
                        try:
                            print(str(get_currentTime_iso()) + ": " + "uploading data to my mongoDB")
                            client = MongoClient(MongoConfig.MONGODB_URL)
                            db = client[MongoConfig.DB_NAME]
                            coll = db[MongoConfig.COLL_NAME]
                            # post
                            result = coll.insert_one(weather_data)
                            print("mongoDB response:", result)
                        except Exception as e:
                            print(str(get_currentTime_iso()) + ": " + "Exception: ", str(e))
                            
                # ========================================================
                # Upload weather data to mongoDB
                # ========================================================
                # time to upload? (do upload every WU_MEASUREMENT_INTERVAL min)
                if (current_minute == 0) or ((current_minute % WU_MEASUREMENT_INTERVAL) == 0):
                    if WU_WEATHER_UPLOAD:

                        # build a weather data object
                        weather_data = {
                            "action": "updateraw",
                            "ID": wu_station_id,
                            "PASSWORD": wu_station_key,
                            "dateutc": "now",
                            "tempf": str(temp_f),
                            "humidity": str(humidity),
                            "baromin": str(pressure),
                        }
                        
                        # connect to Weather Underground
                        try:
                            print(str(get_currentTime_iso()) + ": " + "Uploading data to Weather Underground")
                            upload_url = WU_URL + "?" + urlencode(weather_data)
                            response = urllib2.urlopen(upload_url)
                            html = response.read()
                            print("WU's Server response:", html)
                            response.close()
                        except Exception as e:
                            print(str(get_currentTime_iso()) + ": " + "Exception: ", str(e))

        # wait a second then check again
        # You can always increase the sleep value below to check less often
        time.sleep(1)  # this should never happen since the above is an infinite loop

    print("Leaving main()")


# ============================================================================
# here's where we start doing stuff
# ============================================================================
# make sure we don't have a MEASUREMENT_INTERVAL > 60
if (MEASUREMENT_INTERVAL is None) or (MEASUREMENT_INTERVAL > 60):
    print("The application's 'MEASUREMENT_INTERVAL' cannot be empty or greater than 60")
    sys.exit(1)

# ============================================================================
# make sure the sensor
# ============================================================================
try:
    sense = SenseHat()
except:
    print("Unable to initialize the Sense HAT library:", sys.exc_info()[0])
    sys.exit(1)

# ============================================================================
#  Read Weather Underground Configuration Parameters
# ============================================================================
print("\nInitializing Weather Underground configuration")
wu_station_id = WuConfig.STATION_ID
wu_station_key = WuConfig.STATION_KEY
if (wu_station_id is None) or (wu_station_key is None):
    print("Missing values from the Weather Underground configuration file\n")
    sys.exit(1)

# Now see what we're supposed to do next
if __name__ == "__main__":      # running this module as the main program
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting application\n")
        sys.exit(0)
