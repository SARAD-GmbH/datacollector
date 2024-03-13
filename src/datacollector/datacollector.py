#! python
"""Command line application that gives back the most recent value of a SARAD
instrument whenever it is called.
Made to be a data source for Zabbix agent."""

import logging
import logging.config
import os
import pickle
import signal
import socket
import sys
import time

import click
import paho.mqtt.client as mqtt  # type: ignore
import schedule  # type: ignore
import yaml
from appdirs import AppDirs  # type: ignore
from filelock import FileLock, Timeout  # type: ignore
from pyzabbix import ZabbixMetric, ZabbixSender  # type: ignore

from sarad.cluster import SaradCluster

LOGLEVEL = logging.DEBUG
LOGCFG = {
    "version": 1,
    "formatters": {
        "normal": {
            "format": "%(asctime)-15s %(levelname)-8s %(module)-14s %(message)s"
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "normal",
            "level": logging.INFO,
            "stream": "ext://sys.stdout",
        },
        "file": {
            "class": "logging.FileHandler",
            "formatter": "normal",
            "level": LOGLEVEL,
            "filename": "datacollector.log",
            "mode": "w",
            "encoding": "utf-8",
        },
    },
    "root": {"handlers": ["file", "console"], "level": logging.DEBUG},
}

logging.config.dictConfig(LOGCFG)
logger = logging.getLogger(__name__)

# * Create mycluster object:
mycluster: SaradCluster = SaradCluster()
mycluster.update_connected_instruments()
logger.debug(mycluster.__dict__)

# * Configuration file:
config = {}
"""Dict: Content of the configuration file datacollector.conf."""
dirs = AppDirs("datacollector")
for loc in [
    os.curdir,
    os.path.expanduser("~"),
    dirs.user_config_dir,
    dirs.site_config_dir,
]:
    try:
        with open(
            os.path.join(loc, "datacollector.conf"), "r", encoding="utf-8"
        ) as ymlfile:
            config = yaml.safe_load(ymlfile)
        break
    except IOError:
        pass

if not config:
    logger.debug("There seems to be no configuration file. Using defaults.")

# ** MQTT config:
try:
    BROKER = config["mqtt"]["broker"]
except KeyError:
    BROKER = "localhost"
try:
    CLIENT_ID = config["mqtt"]["client_id"]
except KeyError:
    CLIENT_ID = socket.gethostname()


def on_connect(client, userdata, flags, result_code):
    # pylint: disable=unused-argument
    """Will be carried out when the client connected to the MQTT broker."""
    if result_code:
        logger.info("Connection to MQTT broker failed. result_code=%s", result_code)
    else:
        logger.info("Connected with MQTT broker.")


def on_disconnect(client, userdata, result_code):
    # pylint: disable=unused-argument
    """Will be carried out when the client disconnected
    from the MQTT broker."""
    if result_code:
        logger.info(
            "Disconnection from MQTT broker failed. result_code=%s", result_code
        )
    else:
        logger.info("Gracefully disconnected from MQTT broker.")


mqtt_client = mqtt.Client()
mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect

# ** Zabbix config:
try:
    SERVER = config["zabbix"]["server"]
except KeyError:
    SERVER = "localhost"
try:
    HOST = config["zabbix"]["host"]
except KeyError:
    HOST = socket.gethostname()
# Create Zabbix sender object
zbx = ZabbixSender(SERVER)


# * Strings:
LOCK_HINT = "Another instance of this application currently holds the lock."


# * Handling of Ctrl+C:
def signal_handler(sig, frame):  # pylint: disable=unused-argument
    """On Ctrl+C:
    - stop all cycles
    - disconnect from MQTT broker"""
    logger.info("You pressed Ctrl+C!")
    for instrument in mycluster:
        instrument.stop_cycle()
        logger.info("Device %s stopped.", instrument.device_id)
    mqtt_client.disconnect()
    mqtt_client.loop_stop()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)


# * Main group of commands:
@click.group()
def cli():
    """Description for the group of commands"""
    logger.debug("broker = %s, client_id = %s", BROKER, CLIENT_ID)


# * Single value output:
@cli.command()
@click.option(
    "--instrument",
    default="j2hRuRDy",
    help=(
        "Instrument Id.  Run ~datacollector cluster~ to get "
        "the list of available instruments."
    ),
)
@click.option(
    "--component",
    default=0,
    type=click.IntRange(0, 63),
    help="The Id of the sensor component.",
)
@click.option(
    "--sensor",
    default=0,
    type=click.IntRange(0, 255),
    help="The Id of the sensor of the component.",
)
@click.option(
    "--measurand",
    default=0,
    type=click.IntRange(0, 3),
    help="The Id of the measurand of the sensor.",
)
@click.option(
    "--lock_path",
    type=click.Path(writable=True),
    default="mycluster.lock",
    help="The path and file name of the lock file.",
)
def value(instrument, component, sensor, measurand, lock_path):
    """Command line application that gives back
    the most recent value of a SARAD instrument whenever it is called."""
    lock = FileLock(lock_path)  # pylint: disable=abstract-class-instantiated
    try:
        with lock.acquire(timeout=10):
            for my_instrument in mycluster.connected_instruments:
                if my_instrument.device_id == instrument:
                    my_instrument.get_recent_value(component, sensor, measurand)
                    click.echo(
                        my_instrument.components[component]
                        .sensors[sensor]
                        .measurands[measurand]
                    )
    except Timeout:
        click.echo(LOCK_HINT)


# * List SARAD instruments:
@cli.command()
@click.option(
    "--lock_path",
    type=click.Path(writable=True),
    default="mycluster.lock",
    help="The path and file name of the lock file.",
)
def cluster(lock_path):
    """Show list of connected SARAD instruments."""
    lock = FileLock(lock_path)  # pylint: disable=abstract-class-instantiated
    try:
        with lock.acquire(timeout=10):
            for instrument in mycluster:
                click.echo(instrument)
                for component in instrument.components:
                    click.echo(component)
            return mycluster
    except Timeout:
        click.echo(LOCK_HINT)
        return False


# * Transmit all values to a target:
def send(target, instrument, component, sensor):
    """Define a function to be executed on scheduled times"""
    for measurand in sensor:
        c_idx = list(instrument).index(component)
        s_idx = list(component).index(sensor)
        m_idx = list(sensor).index(measurand)
        logger.debug(
            "Trying to get value for c_idx=%d, s_idx=%d, m_idx=%d", c_idx, s_idx, m_idx
        )
        instrument.get_recent_value(c_idx, s_idx, m_idx)
        if target == "screen":
            click.echo(measurand)
        elif target == "mqtt":
            mqtt_client.publish(
                f"{CLIENT_ID}/status/{instrument.device_id}/{sensor.name}/"
                f"{measurand.name}",
                f'{{"val": {measurand.value}, "ts": {measurand.time}}}',
            )
            logger.debug("MQTT message for %s published.", sensor.name)
        elif target == "zabbix":
            zbx_value = measurand.value
            zbx_key = f"{sensor.name}-{measurand.name}"
            metrics = [ZabbixMetric(HOST, zbx_key, zbx_value)]
            zbx.send(metrics)
        else:
            logger.error(("Target must be either screen, mqtt or zabbix."))


def set_send_scheduler(target, instrument, component, sensor):
    """Initialise the scheduler to perform the send function."""
    schedule.every(sensor.interval.seconds).seconds.do(
        send, target, instrument, component, sensor
    )
    logger.debug(
        "Poll sensor %s of device %s in intervals of %d s.",
        sensor.name,
        instrument.device_id,
        sensor.interval.seconds,
    )


def unwrapped_transmit(**kwargs):
    """General function to transmit all values gathered from the instruments
    in our cluster to a target.
    Target can be the output of the command on the command line (screen),
    an MQTT broker or a Zabbix server."""
    lock_path = kwargs["lock_path"]
    target = kwargs["target"]
    lock = FileLock(lock_path)  # pylint: disable=abstract-class-instantiated
    try:
        with lock.acquire(timeout=10):
            with open("last_session", "w+b") as session_file:
                pickle.dump(kwargs, session_file)
            # Connect to MQTT broker
            if target == "mqtt":
                mqtt_client.connect(BROKER)
                mqtt_client.loop_start()
            # Start measuring cycles at all instruments
            if "cycles" in config:
                config_dict = config["cycles"]
            else:
                config_dict = {}
            mycluster.synchronize(config_dict)
            for instrument in mycluster:
                instrument.set_lock()
                logger.info("Device %s started and locked.", instrument.device_id)
            # Build the scheduler
            for instrument in mycluster:
                for component in instrument:
                    for sensor in component:
                        set_send_scheduler(target, instrument, component, sensor)
            logger.info("Waiting for first set of values")
            print("Press Ctrl+C to abort.")
            while True:
                schedule.run_pending()
                time.sleep(1)
    except Timeout:
        click.echo(LOCK_HINT)


@cli.command()
@click.option(
    "--lock_path",
    default="mycluster.lock",
    type=click.Path(writable=True),
    help="The path and file name of the lock file.",
)
@click.option(
    "--target",
    default="screen",
    help=("Where the values shall go to? " "(screen, mqtt, zabbix)."),
)
def transmit(**kwargs):
    """General function to transmit all values gathered from the instruments
    in our cluster to a target.
    Target can be the output of the command on the command line (screen),
    an MQTT broker or a Zabbix server."""
    unwrapped_transmit(**kwargs)


# * Re-start last transmit session:
@cli.command()
def last_session():
    """Starts the last trapper session as continuous service"""
    try:
        with open("last_session", "r+b") as session_file:
            kwargs = pickle.load(session_file)
        logger.debug("Using arguments from last run: %s", kwargs)
        unwrapped_transmit(**kwargs)
    except IOError:
        kwargs = {"lock_path": "mycluster.lock", "target": "screen"}
        logger.debug("No last run detected. Using defaults: %s", kwargs)
        unwrapped_transmit(**kwargs)


if __name__ == "__main__":
    cli()
