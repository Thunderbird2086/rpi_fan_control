#!/usr/bin/env python2

import os
import logging
import argparse
import signal
import sys
import time
import yaml

import RPi.GPIO as GPIO


GPIO_FAN = 'port'
FREQ = 'freq'
DUTY_RATIO_MIN = 'duty_min'
LOG_LEVEL = 'logLevel'
MODE = 'mode'
PWM = 'pwm'
SLEEP_TIME = 'interval'
TEMP_THRESHOLD = 'threshold'
TEMP_MIN = 'temp_min'
TEMP_MAX = 'temp_max'

CONFIG = {
    GPIO_FAN: 12,  # gpio_port 12
    TEMP_THRESHOLD: 70.0,
    PWM: {
        FREQ: 50.0,
        DUTY_RATIO_MIN: 70.0,
        TEMP_MAX: 85.0,
        TEMP_MIN: 65.0
    },
    SLEEP_TIME: 30
}


_CPU_TEMP = '/sys/class/thermal/thermal_zone0/temp'

_FORMAT = '%(message)s'
logging.basicConfig(format=_FORMAT)

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


def getTemperature():
    """read cpu temparture"""
    with open(_CPU_TEMP, "r") as f:
        for t in f:
            temp1 = int(t)/1000
            temp2 = int(t)/100
            tempm = int(temp2) % int(temp1)
            cpu_temp = float("{}.{}".format(int(temp1), tempm))
    _LOGGER.debug("T=%s'C", cpu_temp)
    return cpu_temp


def getDutyRatio(temp, high, low, duty_min=0):
    """get duty ratio based on current temperature"""
    if(high < temp):
        return 100

    if(temp < low):
        return 0

    dr = ((temp - low) / (high - low)) * (100 - duty_min) + duty_min
    return int(dr) if dr < 100 else 100


class Fan:
    """Implement Fan
    """

    def __init__(self, config):
        self.config = config

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.config[GPIO_FAN], GPIO.OUT)

        self.pwm = None
        self.control = self.on_off_control

        if all(k in config for k in (MODE, PWM)):
            _LOGGER.info("PWM fan control")
            self.config_pwm = config[PWM]
            self.pwm = GPIO.PWM(config[GPIO_FAN], self.config_pwm[FREQ])
            self.pwm.start(0)
            self.control = self.pwm_control

    def off(self):
        """Turn off fan."""
        GPIO.output(self.config[GPIO_FAN], False)
        _LOGGER.debug("off")

    def on(self):
        """Turn on fan."""
        GPIO.output(self.config[GPIO_FAN], True)
        _LOGGER.debug("on")

    def clean_up(self):
        """Turn off fan and clean up GPIO"""
        if self.pwm is not None:
            self.pwm.stop()

        self.off()
        GPIO.cleanup()

    def on_off_control(self, cpu_temp):
        """On/Off control"""
        if cpu_temp > self.config[TEMP_THRESHOLD]:
            self.on()
            _LOGGER.info("Turned fan on as T=%s'C", cpu_temp)
        else:
            self.off()

    def pwm_control(self, cpu_temp):
        """PWM control"""
        duty = getDutyRatio(cpu_temp,
                            self.config_pwm[TEMP_MAX],
                            self.config_pwm[TEMP_MIN],
                            self.config_pwm[DUTY_RATIO_MIN])
        if duty > 0:
            _LOGGER.info("duty: %s for T=%s'C", duty, cpu_temp)
        self.pwm.ChangeDutyCycle(duty)

    def run(self):
        """mointor temperature and control fan"""
        while True:
            self.control(getTemperature())
            time.sleep(self.config[SLEEP_TIME])


def getArgParse():
    parser = argparse.ArgumentParser(prog='fan-control.py',
                                     usage='%(prog)s [optoins]',
                                     description='Raspberry pi fan controller')
    parser.add_argument('-d', '--debug', dest='debug',
                        action='store_true', default=False,
                        help='set debug mode(default: off)')
    parser.add_argument('-c', '--config', dest='config',
                        type=argparse.FileType('r'),
                        required=False, default=None,
                        help='config file to override default')

    args, unknown = parser.parse_known_args()
    _LOGGER.info("ignore unknwon argumens: %s", unknown)
    return args


def loadConfig(config_file):
    """load custom configuration"""
    if config_file is None:
        return CONFIG

    user_conf = yaml.load(config_file)
    config = CONFIG
    if PWM in user_conf:
        config[MODE] = PWM
    config.update(user_conf)

    _LOGGER.debug(user_conf)
    _LOGGER.debug(config)

    return config


class SignalHandler:
    """Signal handler"""
    def __init__(self, handler):
        self.custom_handler = handler

    def handler(self, signal, frame):
        self.custom_handler()
        _LOGGER.info("Stop fan control")
        sys.exit(0)


def main():
    _LOGGER.info("Starting fan control")
    args = getArgParse()

    if args.debug:
        _LOGGER.setLevel(logging.DEBUG)

    try:
        fan = Fan(loadConfig(args.config))

        custom_sig_handler = SignalHandler(fan.clean_up)
        signal.signal(signal.SIGTERM, custom_sig_handler.handler)

        fan.run()
    except KeyboardInterrupt:
        fan.clean_up()
    except TypeError as e:
        _LOGGER.error("Type error: %s", e)
        fan.clean_up()
    except Exception as e:
        _LOGGER.exception(e)

    _LOGGER.info("Stop fan control")


if __name__ == '__main__':
    main()
