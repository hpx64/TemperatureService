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
    try:
        with open("/proc/device-tree/model") as f:
            model = f.read()
        return model
    except FileNotFoundError:
        pass
    return "-"


def get_cpuinfo(key) -> str:
    try:
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if line.startswith(key) and ":" in line:
                    line = line.strip()
                    value = line.split(":")[1].strip()
                    logging.info(f"cpu info: {key}={value}")
                    return value
    except FileNotFoundError:
        pass
    return "-"


def get_version(filename) -> str:
    version_file = os.path.join(os.path.dirname(__file__), filename)
    try:
        with open(version_file) as f:
            version = f.readline().rstrip()
        return version
    except FileNotFoundError:
        pass
    return "-"


def update():
    update_cpu_temperature()
    update_w1()
    return True


#   update Pi CPU temperature
def update_cpu_temperature():
    if not os.path.exists("/sys/devices/virtual/thermal/thermal_zone0/temp"):
        if dbusservice["cpu-temp"]["/Connected"] != 0:
            dbusservice["cpu-temp"]["/Connected"] = 0
            logging.info("cpu temperature interface disconnected")
    else:
        if dbusservice["cpu-temp"]["/Connected"] != 1:
            dbusservice["cpu-temp"]["/Connected"] = 1
            logging.info("cpu temperature interface connected")
        with open("/sys/devices/virtual/thermal/thermal_zone0/temp", "r") as f:
            value = float(f.readline().rstrip())
            temperature = round(value / 1000.0, 1)
            dbusservice["cpu-temp"]["/Temperature"] = temperature
            # dbusservice["cpu-temp"]["/Humidity"] = 0


# update 1-Wire temperature
def update_w1():
    # check, create and update 1-Wire devices

    instance_index = 100
    for bus in range(1, 9):
        # read list of slaves
        if os.path.isfile(f"/sys/devices/w1_bus_master{bus}/w1_master_slaves"):
            with open(f"/sys/devices/w1_bus_master{bus}/w1_master_slaves", "r") as f:
                lines = f.read()
                w1_slaves = lines.splitlines()

            # Loop through all connected 1-Wire devices, create dbusService if necessary
            for w1_id in w1_slaves:
                family_id = w1_id[:2]
                device_id_string = w1_id[3:]
                # Skip if not a DS18B20 sensor
                if family_id != "28":
                    continue

                logging.debug("1-Wire Family ID: " + family_id + ", Device ID: " + device_id_string + ", Bus: " + str(bus))

                dbus_service_key = "w1-temp:" + w1_id
                if dbus_service_key not in dbusservice:
                    logging.info("1-Wire sensor found without service -> Create new service")

                    instance_index += 1
                    device_id = int(device_id_string, 16)
                    dbusservice[dbus_service_key] = new_service(
                        base, "temperature", "onewire", device_id_string, "1-Wire", instance_index, device_id_string
                    )
                    dbusservice[dbus_service_key]["/ProductId"] = device_id
                    dbusservice[dbus_service_key]["/ProductName"] = "DS18B20"
                    dbusservice[dbus_service_key]["/FirmwareVersion"] = w1_id
                    dbusservice[dbus_service_key]["/HardwareVersion"] = f"{bus}/{w1_id}"
                    dbusservice[dbus_service_key]["/Connected"] = 1
                    dbusservice[dbus_service_key]["/Status"] = 0
                    initSettings(new_settings)
                    readSettings(setting_objects)
                    logging.info(f"New service created for 1-Wire {w1_id} [{instance_index}]")

                # read temperature value
                value = None
                if os.path.exists(f"/sys/devices/w1_bus_master{bus}/{w1_id}/temperature"):
                    with open(f"/sys/devices/w1_bus_master{bus}/{w1_id}/temperature", "r") as f:
                        if line := f.readline():
                            line = line.rstrip()
                            logging.debug("Raw value for " + w1_id + " is " + line)
                            if line.strip("-").isnumeric():
                                value = round(float(line) / 1000.0, 1)
                dbusservice[dbus_service_key]["/Temperature"] = value

    # Check 1-Wire Service Connection
    for item in dbusservice:
        logging.debug("Looking at service: " + item)
        if dbusservice[item]["/Mgmt/Connection"] == "1-Wire":
            logging.debug(f"Found 1-Wire service {item}")
            if os.path.exists("/sys/devices/w1_bus_master" + dbusservice[item]["/HardwareVersion"]):
                if dbusservice[item]["/Connected"] != 1:
                    logging.info(item + " temperature interface connected")
                    dbusservice[item]["/Connected"] = 1
                    dbusservice[item]["/Status"] = 0
            else:
                if dbusservice[item]["/Connected"] != 0:
                    logging.info(item + " temperature interface disconnected")
                    dbusservice[item]["/Connected"] = 0
                    dbusservice[item]["/Status"] = 1
                    dbusservice[item]["/Temperature"] = None


# =========================== Start of settings interface ================
#  The settings interface handles the persistent storage of changes to settings
#  This should probably be created as a new class extension to the settingDevice object
#  We need different dBusObjects for each device
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
    # The callback to the handle value changes has been modified by using an anonymous function (lambda)
    # the callback is declared each time a path is added see example here
    # self.add_path(path, 0, writeable=True, onchangecallback = lambda x,y: handle_changed_value(setting,x,y) )
    logging.info(" ".join(("Storing change to setting", setting + path, str(value))))
    settings[setting + path] = value
    return True


# Changes made to settings need to be reflected in the GUI and in the running service
def handle_changed_setting(setting, oldvalue, newvalue):
    logging.info("Setting changed, setting: %s, old: %s, new: %s" % (setting, oldvalue, newvalue))
    [path, dbus_object] = setting_objects[setting]
    dbus_object[path] = newvalue
    return True


# Add setting is called each time a new service path is created that needs a persistent setting
# If the setting already exists the existing recorded is unchanged
# If the setting does not exist it is created when the serviceDevice object is created
def addSetting(base, path, dbus_object):
    global setting_objects
    global new_settings

    setting = base + path
    logging.info("Add setting " + setting + " " + str(setting_defaults[path]))
    setting_objects[setting] = [path, dbus_object]  # Record the dBus Object and path for this setting
    new_settings[setting] = [setting] + setting_defaults[path]  # Add the setting to the list to be created


# initSettings is called when all the required settings have been added
def initSettings(supported_settings):
    global settings

    # settingsDevice is the library class that handles the reading and setting of persistent settings
    settings = SettingsDevice(
        bus=dbus.SystemBus() if (platform.machine() == "armv7l") else dbus.SessionBus(),
        supportedSettings=supported_settings,
        eventCallback=handle_changed_setting,
    )


# readSettings is called after init settings to read all the stored settings and
# set the initial values of each of the service object paths
# Note you can not read or set a setting if it has not be included in the newSettings
#      list passed to create the new settingsDevice class object


def readSettings(setting_object_list):
    global settings
    for setting in setting_object_list:
        [path, dbus_object] = setting_object_list[setting]
        logging.info(" ".join(("Retrieved setting", setting, path, str(settings[setting]))))
        dbus_object[path] = settings[setting]


# =========================== end of settings interface ======================


class SystemBus(dbus.bus.BusConnection):
    def __new__(cls):
        return dbus.bus.BusConnection.__new__(cls, dbus.bus.BusConnection.TYPE_SYSTEM)


class SessionBus(dbus.bus.BusConnection):
    def __new__(cls):
        return dbus.bus.BusConnection.__new__(cls, dbus.bus.BusConnection.TYPE_SESSION)


def dbusConnection():
    return SessionBus() if "DBUS_SESSION_BUS_ADDRESS" in os.environ else SystemBus()


# Init logging
logging.basicConfig(level=logging.DEBUG)
logging.info(__file__ + " is starting up")
logging.info("Loglevel is set to " + logging.getLevelName(logging.getLogger().getEffectiveLevel()))

# Have a mainloop, so we can send/receive asynchronous calls to and from dbus
DBusGMainLoop(set_as_default=True)


def new_service(base, type, sensor_type, sensor_id, connection, instance: int, setting_id, namespace="com.victronenergy"):
    service_name = "{}.{}.{}_{}".format(base, type, sensor_type, sensor_id)
    service = VeDbusService(service_name, dbusConnection())
    service.add_mandatory_paths(
        processname=__file__,
        processversion=get_version(filename="version") + " running on Python " + platform.python_version(),
        connection=connection,
        deviceinstance=instance,
        productid=0,
        productname="",
        firmwareversion=0,
        hardwareversion=0,
        connected=0,
    )
    setting = "/Settings/" + type.capitalize() + "/" + str(setting_id)
    if type == "temperature":
        service.add_path("/Temperature", [])
        service.add_path("/Status", 0)
        # bind settings
        service.add_path("/TemperatureType", 0, writeable=True, onchangecallback=lambda x, y: handle_changed_value(setting, x, y))
        addSetting(setting, "/TemperatureType", service)
        service.add_path("/CustomName", "", writeable=True, onchangecallback=lambda x, y: handle_changed_value(setting, x, y))
        addSetting(setting, "/CustomName", service)
        service.add_path("/Function", 1, writeable=True)
    # if sensor_type == "cpu":
    #     service.add_path("/Humidity", 0, description="CPU Usage")
    return service


def create_cpu_service(name, namespace="com.victronenergy"):
    dbusservice[name] = new_service(base, "temperature", "cpu", 1, "Raspberry Pi", 29, "RaspberryCPU")
    dbusservice[name]["/ProductId"] = int(get_cpuinfo("Serial"), 16)
    dbusservice[name]["/ProductName"] = get_cpuinfo("Model")
    dbusservice[name]["/FirmwareVersion"] = get_cpuinfo("Revision")
    dbusservice[name]["/HardwareVersion"] = get_cpuinfo("Hardware")
    dbusservice[name]["/CustomName"] = "CPU"
    dbusservice[name]["/TemperatureType"] = 2
    # Persistent settings objects in settingsDevice will not exist before this is executed
    initSettings(new_settings)
    # Do something to read the saved settings and apply them to the objects
    readSettings(setting_objects)


dbusservice = {}  # Dictionary to hold the multiple services
base = "com.victronenergy"

create_cpu_service("cpu-temp")

# Do a first update so that all the readings appear
update()
# update every 10 seconds - temperature should move slowly so no need to demand
# too much CPU time
GLib.timeout_add(10000, update)

logging.info("Connected to dbus, and switching over to GLib.MainLoop() (= event based)")
mainloop = GLib.MainLoop()
mainloop.run()
