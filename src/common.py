# -*- coding: utf-8 -*
"""
Created on 15.02.2022
@AUTHOR=Alexander Kombeiz (akombeiz@ukaachen.de)
@VERSION=1.33
"""

#
#      Copyright (c) 2022  AKTIN
#
#      This program is free software: you can redistribute it and/or modify
#      it under the terms of the GNU Affero General Public License as
#      published by the Free Software Foundation, either version 3 of the
#      License, or (at your option) any later version.
#
#      This program is distributed in the hope that it will be useful,
#      but WITHOUT ANY WARRANTY; without even the implied warranty of
#      MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#      GNU Affero General Public License for more details.
#
#      You should have received a copy of the GNU Affero General Public License
#      along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
#

import json
import logging
import os
import xml.etree.ElementTree as et
from abc import ABC, ABCMeta, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from smtplib import SMTP_SSL as SMTP
from typing import Callable

import pandas as pd
import pytz
import requests
import toml
from atlassian import Confluence
from dateutil import parser


class SingletonMeta(type):
    """
    Meta class to make python classes a Singleton
    """
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class SingletonABCMeta(ABCMeta):
    """
    Meta class to make abstract python classes a Singleton -> All implementing classes
    are automatically Singletons
    """
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(SingletonABCMeta, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class DataWriter(ABC, metaclass=SingletonABCMeta):
    """
    Abstract class to store data in a local file
    """
    _encoding: str = 'utf-8'

    @abstractmethod
    def write_data_to_file(self, data, filepath: str):
        pass


class CSVHandler(DataWriter, ABC):
    """
    Operations for reading a CSV file as a dataframe or writing a dataframe to CSV
    """
    _category: str
    _separator: str = ';'

    def __init__(self):
        self.__timestamp = TimestampHandler()

    def write_data_to_file(self, data: pd.DataFrame, filepath: str):
        data.to_csv(filepath, sep=self._separator, encoding=self._encoding, index=False)

    def read_csv_as_df(self, csv_path: str) -> pd.DataFrame:
        return pd.read_csv(csv_path, sep=self._separator, encoding=self._encoding, dtype=str)

    def generate_node_csv_name(self, node_id: str, year: str = None) -> str:
        """
        Naming convention is <ID_NODE>_<CATEGORY>_<CURRENT YEAR>
        """
        if year is None:
            year = self.__timestamp.get_current_year()
        csv_name = '_'.join([node_id, self._category, year])
        return ''.join([csv_name, '.csv'])

    def init_csv_file(self, filepath: str, csv_name: str = None) -> str:
        if csv_name:
            filepath = os.path.join(filepath, csv_name)
        if not os.path.isfile(filepath):
            df = pd.DataFrame(columns=self.get_csv_columns())
            self.write_data_to_file(df, filepath)
        return filepath

    @abstractmethod
    def get_csv_columns(self) -> list:
        pass


class InfoCSVHandler(CSVHandler):
    """
    Implementation for stats CSV. Writes CSV with import and connection information
    of a single connected node
    """
    _category = 'stats'

    def get_csv_columns(self) -> list:
        return ['date', 'last_contact', 'last_start', 'last_write', 'last_reject',
                'imported', 'updated', 'invalid', 'failed', 'error_rate',
                'daily_imported', 'daily_updated', 'daily_invalid', 'daily_failed', 'daily_error_rate']


class ErrorCSVHandler(CSVHandler):
    """
    Implementation for error CSV. Writes CSV with import errors of a single connected
    node
    """
    _category = 'errors'

    def get_csv_columns(self) -> list:
        return ['timestamp', 'repeats', 'content']


class TextWriter(DataWriter):

    def write_data_to_file(self, data, filepath: str):
        with open(filepath, 'a', encoding=self._encoding) as file:
            file.write(data)

    def save_dict_as_txt_file(self, dictionary: dict, filepath: str):
        with open(filepath, 'w', encoding=self._encoding) as file:
            file.write(json.dumps(dictionary))

    def load_txt_file_as_dict(self, filepath: str) -> dict:
        with open(filepath, 'r', encoding=self._encoding) as file:
            return json.load(file)

    def init_new_file_if_nonexisting(self, filepath: str):
        if not os.path.isfile(filepath):
            self.save_dict_as_txt_file({}, filepath)


class TimestampHandler(metaclass=SingletonMeta):
    """
    Handles everything regarding dates and timestamps
    """
    __tzinfo = pytz.UTC

    def get_current_date(self) -> str:
        return str(datetime.utcnow().replace(tzinfo=self.__tzinfo))

    def get_yesterdays_date(self) -> str:
        date = datetime.utcnow().replace(tzinfo=self.__tzinfo) - timedelta(days=1)
        return str(date)

    def get_current_year(self) -> str:
        date = datetime.utcnow().replace(tzinfo=self.__tzinfo)
        return str(date.year)

    def __to_utc(self, date: str) -> datetime:
        return parser.parse(date).astimezone(self.__tzinfo)

    def get_utc_year_from_date_string(self, date: str) -> str:
        return str(self.__to_utc(date).year)

    def get_utc_ymd_from_date_string(self, date: str) -> str:
        return self.__to_utc(date).strftime('%Y-%m-%d')

    def get_utc_ymd_hms_from_date_string(self, date: str) -> str:
        return self.__to_utc(date).strftime('%Y-%m-%d %H:%M:%S')

    def get_timedelta_in_absolute_hours(self, date1: str, date2: str) -> float:
        delta = abs(self.__to_utc(date2) - self.__to_utc(date1))
        return round(delta.total_seconds() / 3600)

    @staticmethod
    def convert_ts_to_berlin_time(date: str) -> str:
        """
        If dt is naive, it is assumed to be in UTC
        """
        dt = parser.parse(date)
        if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
            dt = pytz.UTC.localize(dt)
        berlin_tz = pytz.timezone('Europe/Berlin')
        berlin_time = dt.astimezone(berlin_tz)
        return str(berlin_time)


class BrokerNodeConnection(metaclass=SingletonMeta):
    """
    Uses REST endpoint of broker-server to get information about
    connected nodes
    """
    __timeout = 10
    __namespace = './/{http://aktin.org/ns/exchange}'

    def __init__(self):
        self.__broker_url = os.getenv('BROKER.URL')
        self.__admin_api_key = os.getenv('BROKER.API_KEY')
        self.__check_broker_server_availability()

    def __check_broker_server_availability(self):
        url = self.__append_to_broker_url('broker', 'status')
        response = requests.head(url, timeout=self.__timeout)
        response.raise_for_status()

    def __append_to_broker_url(self, *items: str) -> str:
        url = self.__broker_url
        for item in items:
            url = f'{url}/{item}'
        return url

    def get_broker_nodes(self) -> list:
        url = self.__append_to_broker_url('broker', 'node')
        tree = self.__get_processed_response(url)
        list_ids = []
        for node in tree.findall(f'{self.__namespace}node'):
            id_element = node.find(f'{self.__namespace}id')
            if id_element is not None:
                list_ids.append(id_element.text)
        return list_ids

    def get_broker_node(self, node_id: str) -> 'BrokerNodeConnection.BrokerNode':
        url = self.__append_to_broker_url('broker', 'node', node_id)
        tree = self.__get_processed_response(url)
        return self.BrokerNode(
            node_id,
            tree.find(f'{self.__namespace}clientDN').text,
            tree.find(f'{self.__namespace}last-contact').text)

    def get_broker_node_stats(self, node_id: str) -> 'BrokerNodeConnection.BrokerNodeStats':
        url = self.__append_to_broker_url('broker', 'node', node_id, 'stats')
        tree = self.__get_processed_response(url)
        return self.BrokerNodeStats(
            tree.find('start').text,
            tree.find('last-write').text if tree.find('last-write') is not None else None,
            tree.find('last-reject').text if tree.find('last-reject') is not None else None,
            tree.find('imported').text,
            tree.find('updated').text,
            tree.find('invalid').text,
            tree.find('failed').text)

    def get_broker_node_errors(self, node_id: str) -> list:
        url = self.__append_to_broker_url('broker', 'node', node_id, 'stats')
        tree = self.__get_processed_response(url)
        errors = []
        for elem in tree.find('last-errors'):
            error = self.BrokerNodeError(
                elem.get('repeats'),
                elem.get('timestamp'),
                elem.text)
            errors.append(error)
        return errors

    def get_broker_node_resource(self, node_id: str, resource: str) -> dict:
        """
        Possible resources are 'versions', 'rscript', 'python', 'import-scripts'.
        URL to mentioned resources can also be non-existing.
        """
        url = self.__append_to_broker_url('broker', 'node', node_id, resource)
        try:
            tree = self.__get_processed_response(url)
            resources = {elem.get('key'): elem.text for elem in tree.iterfind('entry')}
        except requests.exceptions.HTTPError:
            resources = {}
        return resources

    def __get_processed_response(self, url: str) -> et.Element:
        """
        Returns XML tree object from GET request
        """
        response = requests.get(url, headers=self.__create_basic_headers(), timeout=self.__timeout)
        response.raise_for_status()
        tree = et.fromstring(response.content)
        return tree

    def __create_basic_headers(self) -> dict:
        """
        HTTP header for requests to AKTIN Broker
        """
        headers = requests.utils.default_headers()
        headers['Authorization'] = f'Bearer {self.__admin_api_key}'
        headers['User-Agent'] = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36'
        headers['Accept'] = 'application/xml'
        return headers

    @dataclass()
    class BrokerNode:

        __id: str
        __domain_name: str
        __last_contact: str

        @property
        def id(self) -> str:
            return self.__id

        @property
        def domain_name(self) -> str:
            return self.__domain_name

        @property
        def last_contact(self) -> str:
            return self.__last_contact

    @dataclass()
    class BrokerNodeStats:

        __last_start: str
        __last_write: str
        __last_reject: str
        __imported: str
        __updated: str
        __invalid: str
        __failed: str

        @property
        def dwh_start(self) -> str:
            return self.__last_start

        @property
        def last_write(self) -> str:
            return self.__last_write

        @property
        def last_reject(self) -> str:
            return self.__last_reject

        @property
        def imported(self) -> str:
            return self.__imported

        @property
        def updated(self) -> str:
            return self.__updated

        @property
        def invalid(self) -> str:
            return self.__invalid

        @property
        def failed(self) -> str:
            return self.__failed

    @dataclass()
    class BrokerNodeError:

        __repeats: str
        __timestamp: str
        __content: str

        @property
        def repeats(self) -> str:
            return self.__repeats

        @property
        def timestamp(self) -> str:
            return self.__timestamp

        @property
        def content(self) -> str:
            return self.__content


class ResourceLoader(ABC, metaclass=SingletonABCMeta):
    """
    To load resources from the resources folder
    """

    def __init__(self):
        self.__resources_dir = os.getenv('DIR.RESOURCES')

    def _get_resource_as_string(self, resource_name: str, encoding: str) -> str:
        resource_path = os.path.join(self.__resources_dir, resource_name)
        with open(resource_path, 'r', encoding=encoding) as file:
            content = file.read()
        return content


class ConfluenceConnection(metaclass=SingletonMeta):
    """
    Uses Atlassian Python API to execute CRUD operations on Confluence
    """

    def __init__(self):
        """
        Confluence connection is created on initialization
        """
        confluence_url = os.getenv('CONFLUENCE.URL')
        confluence_token = os.getenv('CONFLUENCE.TOKEN')
        self.__space = os.getenv('CONFLUENCE.SPACE')
        self.__confluence = Confluence(url=confluence_url, token=confluence_token)

    def does_page_exists(self, pagename: str) -> bool:
        return self.__confluence.page_exists(self.__space, pagename)

    def get_page_content(self, pagename: str) -> str:
        page_id = self.__confluence.get_page_id(self.__space, pagename)
        page = self.__confluence.get_page_by_id(page_id, expand='body.storage')
        content = page['body']['storage']['value']
        return content

    def upload_file_as_attachement_to_page(self, pagename: str, filepath: str, filetype: str) -> int:
        """
        Identical named files are automatically replaced on confluence
        filetype can be: ''text/csv', 'image/png'
        """
        page_id = self.__confluence.get_page_id(self.__space, pagename)
        self.__confluence.attach_file(filepath, content_type=filetype, page_id=page_id)
        return page_id

    def create_confluence_page(self, pagename: str, parentname: str, content: str):
        parent_id = self.__confluence.get_page_id(self.__space, parentname)
        self.__confluence.create_page(self.__space, pagename, content, parent_id=parent_id)

    def update_confluence_page(self, pagename: str, content: str):
        page_id = self.__confluence.get_page_id(self.__space, pagename)
        self.__confluence.update_page(page_id, pagename, content)


class ConfluenceNodeMapper(metaclass=SingletonMeta):
    """
    Maps the ID of a broker node to a JSON file with information related to a Confluence page,
    such as institution name and Jira query labels.
    """

    def __init__(self):
        path_mapping_json = os.getenv('CONFLUENCE.MAPPING_JSON')
        self.__dict_mapping = self.__load_json_file_as_dict(path_mapping_json)

    @staticmethod
    def __load_json_file_as_dict(filepath: str) -> dict:
        with open(filepath, encoding='utf-8') as json_file:
            return json.load(json_file)

    def get_all_keys(self) -> list:
        return list(self.__dict_mapping.keys())

    def get_node_from_mapping_dict(self, node_id: str) -> dict:
        return self.__dict_mapping.get(node_id)

    def get_node_value_from_mapping_dict(self, node_id: str, key: str) -> str:
        node_mapping = self.__dict_mapping.get(node_id)
        if node_mapping:
            return node_mapping.get(key)
        return None


class MailServerConnection(metaclass=SingletonABCMeta):
    """
    Creates a connection with an external mail server.
    """

    def __init__(self):
        self._user = os.getenv('SMTP.USERNAME')
        self.__host = os.getenv('SMTP.SERVER')
        self.__password = os.getenv('SMTP.PASSWORD')
        self._connection = None

    def _connect(self):
        self._connection = SMTP(self.__host)
        self._connection.login(self._user, self.__password)

    def _close(self):
        if self._connection:
            self._connection.close()


class MailSender(MailServerConnection):
    """
    Class responsible for sending emails using the mail server connection.
    """

    def __init__(self):
        super().__init__()
        self.__static_recipients = os.getenv('SMTP.STATIC_RECIPIENTS').split(',')

    def __enter__(self):
        self._connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._close()

    def send_mail(self, recipients: list, mail: MIMEText):
        with self:
            mail['From'] = self._user
            recipients.extend(self.__static_recipients)
            recipients = list(set(recipients))  # Remove duplicates
            mail['To'] = ', '.join(recipients)
            self._connection.sendmail(self._user, recipients, mail.as_string())


class ConfigReader(metaclass=SingletonMeta):
    """
    This class should be called by every other script on startup!
    Checks given config file to include required keys and loads key-values as
    environment variables after validation. The environment variables are assumed
    by the classes of other scripts
    """
    __required_keys = {
        'BROKER.URL',
        'BROKER.API_KEY',
        'DIR.WORKING',
        'DIR.RESOURCES',
        'CONFLUENCE.URL',
        'CONFLUENCE.SPACE',
        'CONFLUENCE.TOKEN',
        'CONFLUENCE.MAPPING_JSON',
        'SMTP.SERVER',
        'SMTP.USERNAME',
        'SMTP.PASSWORD',
        'SMTP.STATIC_RECIPIENTS',
        'AKTIN.DWH_VERSION',
        'AKTIN.I2B2_VERSION'
    }
    __optional_keys = {'REQUESTS_CA_BUNDLE'}

    def load_config_as_env_vars(self, path: str):
        properties = self.__load_config_file(path)
        flattened_props = self.__flatten_config(properties)
        self.__validate_config(flattened_props)
        for key in self.__required_keys | self.__optional_keys:
            if key in flattened_props:
                if key == 'SMTP.STATIC_RECIPIENTS':
                    os.environ[key] = ','.join(flattened_props.get(key))
                else:
                    os.environ[key] = flattened_props.get(key)

    @staticmethod
    def __load_config_file(path: str) -> dict:
        if not os.path.isfile(path):
            raise SystemExit('invalid TOML file path')
        with open(path, encoding='utf-8') as file:
            return toml.load(file)

    @staticmethod
    def __flatten_config(config: dict, parent_key='', sep='.') -> dict:
        items = []
        for key, val in config.items():
            new_key = f'{parent_key}{sep}{key}' if parent_key else key
            if isinstance(val, dict):
                items.extend(ConfigReader.__flatten_config(val, new_key, sep=sep).items())
            else:
                items.append((new_key, val))
        return dict(items)

    def __validate_config(self, config: dict):
        loaded_keys = set(config.keys())
        missing_keys = self.__required_keys - loaded_keys
        if missing_keys:
            raise SystemExit(f'following keys are missing in config file: {missing_keys}')


class MyLogger(metaclass=SingletonMeta):
    """
    This class should be called by every other script on startup!
    """

    def __init__(self):
        self.__logger = self.init_logger()

    @staticmethod
    def init_logger():
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
        return logger

    def stop_logger(self):
        handlers = self.__logger.handlers[:]
        for handler in handlers:
            handler.close()
            self.__logger.removeHandler(handler)
        logging.shutdown()


class Main(metaclass=SingletonMeta):
    """
    Main class responsible for executing the main functionality of a script.
    """

    @staticmethod
    def main(path_config: str, functionality: Callable[[], None]):
        logger = MyLogger()
        reader = ConfigReader()
        try:
            logger.init_logger()
            reader.load_config_as_env_vars(path_config)
            functionality()  # Call the provided function to execute the specific functionality
        except Exception as e:
            logging.exception(e)
        finally:
            logger.stop_logger()
