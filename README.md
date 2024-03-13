# datacollector

The *datacollector* is a command line application to demonstrate the usage of
the [*sarad* library](https://github.com/SARAD-GmbH/sarad). It allows to send
measuring values to a Zabbix server or publish MQTT messages or to display
values.

## Getting started
Requires Python 3.

Clone the repository to your local computer and move into the directory.
```
sudo pip install --editable ./
```

Afterwards you should be able to run the sample application by for instance calling
```
datacollector cluster
```

Get further help with
```
datacollector --help
```

*Read the code!*

[![pdm-managed](https://img.shields.io/badge/pdm-managed-blueviolet)](https://pdm-project.org)
