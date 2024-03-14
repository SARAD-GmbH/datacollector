# datacollector

The *datacollector* is a command line application to demonstrate the usage of
the [*sarad* library](https://github.com/SARAD-GmbH/sarad). It allows to send
measuring values to a Zabbix server or publish MQTT messages or to display
values.

## Installation
### Using Pip
```
pip install git+https://github.com/SARAD-GmbH/datacollector.git
```

### Using Pipx
```
pipx install git+https://github.com/SARAD-GmbH/datacollector.git
```

## Getting started

After the installation you should be able to run the application by for instance calling
```
datacollector cluster
```

Get further help with
```
datacollector --help
```

The application will create a log file `datacollector.log` as well as a lock
file for the cluster `mycluster.lock` in the same directory the command line
application is started from.

A configuration file `datacollector.conf` (refer to the example in
`src/datacollector/`) can be placed in the same directory to set e.g. the
address of your MQTT broker.

*Read the code!*

[![pdm-managed](https://img.shields.io/badge/pdm-managed-blueviolet)](https://pdm-project.org)
