#!/usr/bin/env python

# Copyright (c) 2021 LHardwick-git, Edit by HPx64
# Licensed under the BSD 3-Clause license. See LICENSE file in the project root for full license information.

# If editing then use
# svc -d /service/TemperatureService
# svc -u /service/TemperatureService
# to stop and restart the service

import logging
import os
import platform
import sys

import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

# victronenergy packages
sys.path.insert(1, "/opt/victronenergy/dbus-tempsensor-relay/ext/velib_python")
from vedbus import VeDbusService
from settingsdevice import SettingsDevice  # available in the velib_python repository


def get_model() -> str:
    with open("/proc/device-tree/model") as f:
        model = f.read()
    return model


def get_cpuinfo(key):
    value = ""
    try:
        f = open("/proc/cpuinfo", "r")
        for line in f:
            if line.startswith(key) and ":" in line:
                line = line.strip()
                logging.debug(line)
                value = line.split(":")[1]
                logging.info(key + "=" + value)
                break
        f.close()
    except Exception:
        pass

    return value


def get_version() -> str:
    version_filepath = os.path.join(os.path.dirname(__file__), "version")
    with open(version_filepath) as f:
        version = f.readline(1).rstrip()
    return version


def update():
    update_rpi()
    update_w1()
    return True


#   update Pi CPU temperature
def update_rpi():
    if not os.path.exists("/sys/devices/virtual/thermal/thermal_zone0/temp"):
        if dbusservice["cpu-temp"]["/Connected"] != 0:
            logging.info("cpu temperature interface disconnected")
            dbusservice["cpu-temp"]["/Connected"] = 0
    else:
        if dbusservice["cpu-temp"]["/Connected"] != 1:
            logging.info("cpu temperature interface connected")
            dbusservice["cpu-temp"]["/Connected"] = 1
        with open("/sys/devices/virtual/thermal/thermal_zone0/temp", "r") as f:
            value = float(f.readline().rstrip())
            temperature = round(value / 1000.0, 1)
            dbusservice["cpu-temp"]["/Temperature"] = temperature


# update 1-Wire temperature
def update_w1():
    # check, create and update 1-Wire devices

    # read list of slaves
    if os.path.isfile("/sys/devices/w1_bus_master1/w1_master_slaves"):
        with open("/sys/devices/w1_bus_master1/w1_master_slaves", "r") as f:
            lines = f.read()
            w1_slaves = lines.splitlines()

        # Loop through all connected 1-Wire devices, create dbusService if necessary
        for index, w1_id in enumerate(w1_slaves):
            family_id = w1_id[0:2]
            device_id = w1_id[3:]
            logging.debug("1-Wire Family ID: " + family_id + ", Device ID: " + device_id)

            # DS18B20 Sensors
            if family_id != "28":
                continue

            if ("w1-temp:" + w1_id) not in dbusservice:
                logging.info("1-Wire Sensor found with no service -> Create Service")

                dbusservice["w1-temp:" + w1_id] = new_service(base, "temperature", "OneWire", "1-Wire", index + 1, 100 + index, device_id)
                dbusservice["w1-temp:" + w1_id]["/ProductId"] = int(device_id, 16)
                dbusservice["w1-temp:" + w1_id]["/ProductName"] = "DS18B20"
                dbusservice["w1-temp:" + w1_id]["/HardwareVersion"] = w1_id
                dbusservice["w1-temp:" + w1_id]["/FirmwareVersion"] = device_id
                initSettings(new_settings)
                readSettings(setting_objects)

                logging.info("Created Service 1-Wire ID: " + str(index + 1) + " Settings ID:" + str(100 + index))

            # read temperature value
            value = None
            if os.path.exists("/sys/devices/w1_bus_master1/" + w1_id + "/temperature"):
                with open("/sys/devices/w1_bus_master1/" + w1_id + "/temperature", "r") as f:
                    if line := f.readline():
                        line = line.rstrip()
                        logging.debug("RawValue " + w1_id + ":" + line)
                        if line.strip("-").isnumeric():
                            value = round(float(line) / 1000.0, 1)
            dbusservice["w1-temp:" + w1_id]["/Temperature"] = value

    # Check 1-Wire Service Connection
    for item in dbusservice:
        logging.debug("Looking for 1-Wire Service: " + item)
        if dbusservice[item]["/Mgmt/Connection"] == "1-Wire":
            logging.debug("Found 1-Wire Service")
            if not os.path.exists("/sys/devices/w1_bus_master1/" + item[8:]):
                if dbusservice[item]["/Connected"] != 0:
                    logging.info(item + " temperature interface disconnected")
                    dbusservice[item]["/Connected"] = 0
                    dbusservice[item]["/Status"] = 1
                    dbusservice[item]["/Temperature"] = None
            else:
                if dbusservice[item]["/Connected"] != 1:
                    logging.info(item + " temperature interface connected")
                    dbusservice[item]["/Connected"] = 1
                    dbusservice[item]["/Status"] = 0


# =========================== Start of settings interface ================
#  The settings interface handles the persistent storage of changes to settings
#  This should probably be created as a new class extension to the settingDevice object
#  The complexity is because this python service handles temperature and humidity
#  Data for about 6 different service paths so we need different dBusObjects for each device
#
settings = {}
new_settings = {}  # Used to gather new settings to create/check as each dBus object is created
setting_objects = {}  # Used to identify the dBus object and path for each setting
# setting_objects = {setting: [path,object],}
# each setting is the complete string e.g. /Settings/Temperature/4/Scale

setting_defaults = {"/Offset": [0, -10, 10], "/Scale": [1.0, -5, 5], "/TemperatureType": [0, 0, 3], "/CustomName": ["", 0, 0]}


# Values changed in the GUI need to be updated in the settings
# Without these changes made through the GUI change the dBusObject but not the persistent setting
def handle_changed_value(setting, path, value):
    global settings
    print("some value changed")
    # The callback to the handle value changes has been modified by using an anonymouse function (lambda)
    # the callback is declared each time a path is added see example here
    # self.add_path(path, 0, writeable=True, onchangecallback = lambda x,y: handle_changed_value(setting,x,y) )
    logging.info(" ".join(("Storing change to setting", setting + path, str(value))))
    settings[setting + path] = value
    return True


# Changes made to settings need to be reflected in the GUI and in the running service
def handle_changed_setting(setting, oldvalue, newvalue):
    logging.info("Setting changed, setting: %s, old: %s, new: %s" % (setting, oldvalue, newvalue))
    [path, object] = setting_objects[setting]
    object[path] = newvalue
    return True


# Add setting is called each time a new service path is created that needs a persistent setting
# If the setting already exists the existing recored is unchanged
# If the setting does not exist it is created when the serviceDevice object is created
def addSetting(base, path, dBusObject):
    global setting_objects
    global new_settings

    setting = base + path
    logging.info(" ".join(("Add setting", setting, str(setting_defaults[path]))))
    setting_objects[setting] = [path, dBusObject]  # Record the dBus Object and path for this setting
    new_settings[setting] = [setting] + setting_defaults[path]  # Add the setting to the list to be created


# initSettings is called when all the required settings have been added
def initSettings(supported_settings):
    global settings

    #   settingsDevice is the library class that handles the reading and setting of persistent settings
    settings = SettingsDevice(
        bus=dbus.SystemBus() if (platform.machine() == "armv7l") else dbus.SessionBus(),
        supportedSettings=supported_settings,
        eventCallback=handle_changed_setting,
    )


# readSettings is called after init settings to read all the stored settings and
# set the initial values of each of the service object paths
# Note you can not read or set a setting if it has not be included in the newSettings
#      list passed to create the new settingsDevice class object


def readSettings(list):
    global settings
    for setting in list:
        [path, object] = list[setting]
        logging.info(" ".join(("Retrieved setting", setting, path, str(settings[setting]))))
        object[path] = settings[setting]


# =========================== end of settings interface ======================


class SystemBus(dbus.bus.BusConnection):
    def __new__(cls):
        return dbus.bus.BusConnection.__new__(cls, dbus.bus.BusConnection.TYPE_SYSTEM)


class SessionBus(dbus.bus.BusConnection):
    def __new__(cls):
        return dbus.bus.BusConnection.__new__(cls, dbus.bus.BusConnection.TYPE_SESSION)


def dbusconnection():
    return SessionBus() if "DBUS_SESSION_BUS_ADDRESS" in os.environ else SystemBus()


# Init logging
logging.basicConfig(level=logging.DEBUG)
logging.info(__file__ + " is starting up")
logging.info("Loglevel is set to " + logging.getLevelName(logging.getLogger().getEffectiveLevel()))

# Have a mainloop, so we can send/receive asynchronous calls to and from dbus
DBusGMainLoop(set_as_default=True)


def new_service(base, type, physical, connection, id, instance, setting_id=None):
    self = VeDbusService("{}.{}.{}_id{:02d}".format(base, type, physical, id), dbusconnection())
    self.add_mandatory_paths(
        processname=__file__,
        processversion=get_version() + " running on Python " + platform.python_version(),
        connection=connection,
        deviceinstance=instance,
        productid=0,
        productname="",
        firmwareversion=0,
        hardwareversion=0,
        connected=0,  # Mark devices as disconnected until they are confirmed
    )
    # Create device type specific objects set values to empty until connected
    if setting_id:
        setting = "/Settings/" + type.capitalize() + "/" + str(setting_id)
    else:
        print("no setting required")
        setting = ""
    if type == "temperature":
        self.add_path("/Temperature", [])
        self.add_path("/Status", 0)
        if setting_id:
            addSetting(setting, "/TemperatureType", self)
            addSetting(setting, "/CustomName", self)
        self.add_path("/TemperatureType", 0, writeable=True, onchangecallback=lambda x, y: handle_changed_value(setting, x, y))
        self.add_path("/CustomName", "", writeable=True, onchangecallback=lambda x, y: handle_changed_value(setting, x, y))
        self.add_path("/Function", 1, writeable=True)
    return self


dbusservice = {}  # Dictionary to hold the multiple services
base = "com.victronenergy"

# service defined by (base*, type*, connection*, logial, id*, instance, settings ID):
# The setting iD is used with settingsDevice library to create a persistent setting
# Items marked with a (*) are included in the service name
dbusservice["cpu-temp"] = new_service(base, "temperature", "RpiCpu", "Raspberry Pi", 6, 29, 6)
dbusservice["cpu-temp"]["/ProductId"] = int(get_cpuinfo("Serial"), 16)
dbusservice["cpu-temp"]["/ProductName"] = get_cpuinfo("Model")
dbusservice["cpu-temp"]["/FirmwareVersion"] = get_cpuinfo("Revision")
dbusservice["cpu-temp"]["/HardwareVersion"] = get_cpuinfo("Hardware")
# Persistent settings objects in settingsDevice will not exist before this is executed
initSettings(new_settings)
# Do something to read the saved settings and apply them to the objects
readSettings(setting_objects)

# Do a first update so that all the readings appear.
update()
# update every 10 seconds - temperature and humidity should move slowly so no need to demand
# too much CPU time
GLib.timeout_add(10000, update)

logging.info("Connected to dbus, and switching over to GLib.MainLoop() (= event based)")
mainloop = GLib.MainLoop()
mainloop.run()
