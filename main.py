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

from config import MongoConfig

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

def get_currentTime_iso(replaceMs = False):
    if replaceMs:
        return datetime.datetime.now().replace(microsecond=0).isoformat()
    return datetime.datetime.now().isoformat()
    
def get_utcTime_iso(replaceMs = False):
    if replaceMs:
        return datetime.datetime.utcnow().replace(microsecond=0).isoformat()
    return datetime.datetime.utcnow().isoformat()

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
            temp_c = calc_temp
            temp_f = c_to_f(calc_temp)
            # get humidity
            humidity = sense.get_humidity()
            # get pressure in millibars # add * 0.0295300 to inHg 
            pressure = sense.get_pressure()
            # get compass
            compass = sense.get_compass()
            compass_raw = sense.get_compass_raw()
            # get gyroscope
            gyro = sense.get_gyroscope()
            gyro_raw = sense.get_gyroscope_raw()
            # get accelerometer
            accel = sense.get_accelerometer()
            accel_raw = sense.get_accelerometer_raw()
                      
            # display on console
            print(str(get_currentTime_iso())
                    + ": "
                    + "Temp: %sF (%sC), Pressure: %s hPa, Humidity: %s%%"
                    % (round(temp_f, 1), round(temp_c, 1), round(pressure, 1), round(humidity, 1))
                )
            # display the temp using the HAT's LED light
            msg = "%sC"% (round(temp_c, 1))
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
                            "temperature": temp_c,
                            "humidity": humidity,
                            "pressure": pressure,
                            "compass": compass,
                            "compassRaw": compass_raw,
                            "gyroscope": gyro,
                            "gyroscopeRaw": gyro_raw,
                            "accelerometer": accel,
                            "accelerometerRaw": accel_raw,
                            "device": os.uname()[1],
                            "uploadDtInUtc": str(get_utcTime_iso(True)),
                            "uploadDtInLocal": str(get_currentTime_iso(True)),
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
print("\nInitializing DB configuration")
db_url = MongoConfig.MONGODB_URL
db_user = MongoConfig.DB_NAME
db_pw = MongoConfig.COLL_NAME
if (db_url is None) or (db_user is None) or (db_pw is None):
    print("Missing values from the DB configuration file\n")
    sys.exit(1)

# Now see what we're supposed to do next
if __name__ == "__main__":      # running this module as the main program
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting application\n")
        sys.exit(0)
