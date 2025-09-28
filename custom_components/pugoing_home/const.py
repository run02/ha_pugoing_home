"""Constants for integration_blueprint."""

from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "pugoing_home"
ATTRIBUTION = "Data provided by http://jsonplaceholder.typicode.com/"

PUGOING_POLL_INTERVAL = 1.5
LAMP_STATE_DEBOUNCE_SECONDS = 5
CURTAIN_STATE_DEBOUNCE_SECONDS = 5
BUTTON_STATE_DEBOUNCE_SECONDS = 10

MINIMUM_HA_VERSION = "2024.4.1"
