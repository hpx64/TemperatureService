# Temperature Service
Fork of LHardwick [Victron-Service](https://github.com/LHardwick-git/Victron-Service)

This is a service to publish CPU and 1-Wire temperature data on the D-Bus of Venus OS running on a Raspberry Pi device.

Please [support this project](https://www.paypal.com/donate/?hosted_button_id=Q4JE3NZEU9LRU) to keep it up to date and add more features.

## Features
The TemperatureService supports multiple DS18B20 on one bus as well as multiple buses on different GPIOs. 

* CPU temperature
* Real sensor ID (visible in VRM too)
* VRM instance starting at 100
* Multiple sensors on one bus
* Multiple buses (up to 9)
  * w1_bus_master1
  * w1_bus_master2
  * ...

## Installation
The package can be installed via the [SetupHelper](https://github.com/kwindrem/SetupHelper) by Kevin Windrem. 

**Package name**: TemperatureService \
**GitHub user**: hpx64 \
**GitHub tag**: main

You can skip the reboot in SetupHelper and **press Later** if you want to configure the GPIO ports.
The default port for 1-Wire is GPIO 4.

> [!CAUTION]
> Please note that there may sometimes be conflicts with already occupied GPIOs. \
> The 1-Wire GPIO port can be customized with the parameter _gpiopin_.

## Configuration

Check or change the configuration in /u-boot/config.txt after installation. If you have made changes, you must reboot.

```bash
nano /u-boot/config.txt
```

Add _gpiopin=_ with a colon after dtoverlay=w1-gpio if you need to change the GPIO port.

**Example for GPIO configuration**
```
### Changed by Temperature Service ###
dtoverlay=w1-gpio:gpiopin=17
### END Changed by Temperature Service ###
```

You can use one or more dtoverlay entries in the /u-boot/config.txt

**Example for 2 buses**
```
### Changed by Temperature Service ###
dtoverlay=w1-gpio:gpiopin=17
dtoverlay=w1-gpio:gpiopin=22
### END Changed by Temperature Service ###
```

## Screenshots

### Device List

<img src="https://github.hpx64.de/TemperatureService/screenshots/Device_List.png" alt="Device List" style="width:50%; height:auto;">

### Device CPU

<img src="https://github.hpx64.de/TemperatureService/screenshots/Device_CPU.png" alt="Device CPU" style="width:50%; height:auto;">

### 1-Wire DS18B20 on w1_bus_master3

<img src="https://github.hpx64.de/TemperatureService/screenshots/1-Wire_Hardwareversion.png" alt="Bus number in Hardwareversion" style="width:50%; height:auto;">

> [!NOTE]
> I2C and ADC support is currently not available. \
> If you need I2C or ADC in this package, please contact me.

_The service has only been tested on the Raspberry Pi 4 but should work on Pi 3 and Pi 2._

Please [support this project](https://www.paypal.com/donate/?hosted_button_id=Q4JE3NZEU9LRU)