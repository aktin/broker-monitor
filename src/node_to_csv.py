# -*- coding: utf-8 -*
"""
Created on 19.01.2022
@AUTHOR=Alexander Kombeiz (akombeiz@ukaachen.de)
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

import os
import sys
from abc import ABC, abstractmethod

import pandas as pd

from common import Main, BrokerNodeConnection, ErrorCSVHandler, InfoCSVHandler, SingletonABCMeta, TimestampHandler, TextWriter, DataWriter


class BrokerNodeRetriever(ABC, metaclass=SingletonABCMeta):
    """
    Abstract base class for retrieving broker node data and downloading it to a file.
    """
    _handler: DataWriter

    def __init__(self):
        self._working_dir = os.getenv('DIR.WORKING')
        self._broker_node_connection = BrokerNodeConnection()
        self._timestamp_handler = TimestampHandler()

    def _init_node_directory_if_nonexisting(self, foldername: str) -> str:
        my_dir = os.path.join(self._working_dir, foldername)
        if not os.path.isdir(my_dir):
            os.makedirs(my_dir)
        return my_dir

    @abstractmethod
    def download_broker_data_to_file(self, node_id: str):
        pass


class NodeInfoRetriever(BrokerNodeRetriever):
    """
    Fetches import and connection information from broker node to a CSV file.
    """
    _handler = InfoCSVHandler()

    def download_broker_data_to_file(self, node_id: str):
        """
        Calls AKTIN Broker Endpoints to get import statistics of the connected node and writes the response to a CSV file.
        - One row in the CSV file represents the status of one day.
        - Computes differences to the last row in the CSV file (assuming it contains the import statistics of yesterday).
        - Import stats are resetted on DWH restart, so no daily differences are calculated then.
        - Running the method multiple times will overwrite the row of the current day each time.
        - All date information from the broker server is converted into a local, human-readable format.
        - The variables 'last-reject' and 'last-write' from the broker server can be None if no data was imported or no error occurred.
        - Missing or not computable values are added as '-'.
        - The CSV file is rotated each year to limit its file size.
        - If the CSV file is empty or newly created, the existence of the last year's CSV file is checked.
        """
        csv_name = self._handler.generate_node_csv_name(node_id)
        working_dir = self._init_node_directory_if_nonexisting(node_id)
        csv_path = self._handler.init_csv_file(working_dir, csv_name)
        node = self._broker_node_connection.get_broker_node(node_id)
        stats = self._broker_node_connection.get_broker_node_stats(node_id)
        df = self._handler.read_csv_as_df(csv_path)
        df = self.__delete_todays_row_if_exists(df)
        if df.empty:
            csv_row = self.__get_last_row_of_last_years_csv_if_exists(node_id, working_dir)
        else:
            csv_row = df.iloc[-1]
        if csv_row is not None:
            if self.__was_last_check_yesterday(csv_row) and self.__are_dwh_start_date_equal(csv_row, stats):
                daily_map = self.__compute_daily_stats(csv_row, stats)
            else:
                daily_map = self.__generate_empty_daily_stats()
        else:
            daily_map = self.__generate_empty_daily_stats()
        stats_map = self.__generate_row_stats(node, stats)
        stats_map.update(daily_map)
        stats_dict = pd.DataFrame(stats_map, index=[0])
        df = pd.concat([df, stats_dict])
        self._handler.write_data_to_file(df, csv_path)

    def __delete_todays_row_if_exists(self, csv: pd.DataFrame) -> pd.DataFrame:
        """
        Each row should represent one day, and no duplicates are allowed.
        """
        if not csv.empty:
            current_date = self._timestamp_handler.get_current_date()
            current_ymd = self._timestamp_handler.get_utc_ymd_from_date_string(current_date)
            last_ymd_of_csv = self._timestamp_handler.get_utc_ymd_from_date_string(csv.iloc[-1].date)
            if last_ymd_of_csv == current_ymd:
                csv = csv.head(-1)
            if any(csv['date'] == current_ymd):
                raise SystemExit('date of today was found in multiple rows!!')
        return csv

    def __get_last_row_of_last_years_csv_if_exists(self, node_id: str, working_dir: str) -> pd.DataFrame:
        """
        Retrieves the last row of the CSV file from the last year if it exists.
        This is important at the turn of the year to compute daily differences if yesterday's date was New Year's Eve.
        """
        current_year = self._timestamp_handler.get_current_year()
        last_year = str(int(current_year) - 1)
        last_year_csv_name = self._handler.generate_node_csv_name(node_id, last_year)
        last_year_csv_path = os.path.join(working_dir, last_year_csv_name)
        if os.path.isfile(last_year_csv_path):
            last_years_df = self._handler.read_csv_as_df(last_year_csv_path)
            return last_years_df.iloc[-1]
        return None

    def __was_last_check_yesterday(self, csv_row: pd.DataFrame) -> bool:
        """
        This is a consistency check. Today's stats cannot be computed without yesterday's stats.
        """
        yesterdays_date = self._timestamp_handler.get_yesterdays_date()
        yesterdays_ymd = self._timestamp_handler.get_utc_ymd_from_date_string(yesterdays_date)
        last_ymd_of_csv = csv_row.date[:10]
        return last_ymd_of_csv == yesterdays_ymd

    def __are_dwh_start_date_equal(self, csv_row: pd.DataFrame, stats: BrokerNodeConnection.BrokerNodeStats) -> bool:
        """
        This is a consistency check. Import stats of AKTIN DWH are reset on each restart.
        """
        last_start = self._timestamp_handler.get_utc_ymd_hms_from_date_string(csv_row.last_start)
        dwh_start = self._timestamp_handler.get_utc_ymd_hms_from_date_string(stats.dwh_start)
        return last_start == dwh_start

    @staticmethod
    def __generate_empty_daily_stats() -> dict:
        return {'daily_imported': '-',
                'daily_updated': '-',
                'daily_invalid': '-',
                'daily_failed': '-',
                'daily_error_rate': '-'}

    def __compute_daily_stats(self, csv_stats: pd.DataFrame, node_stats: BrokerNodeConnection.BrokerNodeStats) -> dict:
        """
        Computes the daily stats based on the CSV and broker node statistics.
        """
        daily_imported = int(node_stats.imported) - int(csv_stats.imported)
        daily_updated = int(node_stats.updated) - int(csv_stats.updated)
        daily_invalid = int(node_stats.invalid) - int(csv_stats.invalid)
        daily_failed = int(node_stats.failed) - int(csv_stats.failed)
        daily_error_rate = self.__compute_error_rate(daily_imported, daily_updated, daily_invalid, daily_failed)
        return {'daily_imported': daily_imported,
                'daily_updated': daily_updated,
                'daily_invalid': daily_invalid,
                'daily_failed': daily_failed,
                'daily_error_rate': daily_error_rate}

    def __generate_row_stats(self, node_broker: BrokerNodeConnection.BrokerNode, node_stats: BrokerNodeConnection.BrokerNodeStats) -> dict:
        """
        Generates the row statistics dictionary based on the broker node and its statistics.
        'last_contact' seems to be in UTC, the other dates are in local timezone
        """
        imported = int(node_stats.imported)
        updated = int(node_stats.updated)
        invalid = int(node_stats.invalid)
        failed = int(node_stats.failed)
        return {'date': self._timestamp_handler.get_current_date(),
                'last_contact': node_broker.last_contact,
                'last_start': node_stats.dwh_start,
                'last_write': node_stats.last_write if node_stats.last_write is not None else '-',
                'last_reject': node_stats.last_reject if node_stats.last_reject is not None else '-',
                'imported': imported,
                'updated': updated,
                'invalid': invalid,
                'failed': failed,
                'error_rate': self.__compute_error_rate(imported, updated, invalid, failed)}

    @staticmethod
    def __compute_error_rate(imported: int, updated: int, invalid: int, failed: int) -> str:
        """
        The error rate is computed as (invalid + failed) / (imported + updated).
        If the denominator is 0, the error rate is set to 100.
        """
        sum_success = imported + updated
        sum_failure = invalid + failed
        if sum_failure > 0 and sum_success == 0:
            error_rate = '100.0'
        elif sum_failure == 0 and sum_success == 0:
            error_rate = '-'
        else:
            error_rate = sum_failure / (sum_success + sum_failure) * 100
            error_rate = f'{error_rate:.2f}'
        return error_rate


class NodeErrorRetriever(BrokerNodeRetriever):
    """
    Retrieves import errors from a broker node and saves them to a CSV file.
    """
    _handler = ErrorCSVHandler()

    def download_broker_data_to_file(self, node_id: str):
        """
        Downloads import errors from the connected broker node and writes them to a CSV file.
        - Each row in the CSV file represents one occurred error.
        - Logged errors can be updated on the broker side, where the 'timestamp' is updated
          and 'repeats' is incremented.
        - Updates in the CSV file are done by deleting and re-appending the corresponding row.
        - Only errors of the current year are tracked in the CSV file to limit its size.
        - Similar to NodeInfoFetcher, the CSV file is rotated each year.
        """
        csv_name = self._handler.generate_node_csv_name(node_id)
        working_dir = self._init_node_directory_if_nonexisting(node_id)
        csv_path = self._handler.init_csv_file(working_dir, csv_name)
        errors = self._broker_node_connection.get_broker_node_errors(node_id)
        df = self._handler.read_csv_as_df(csv_path)
        for error in errors:
            if self.__did_error_appear_this_year(error):
                error_row = self.__convert_error_to_row(error)
                if self.__is_error_already_logged(df, error_row):
                    if self.__did_error_row_repeats_change(df, error_row):
                        df = self.__delete_old_error_row(df, error_row)
                        df = pd.concat([df, error_row])
                else:
                    df = pd.concat([df, error_row])
        df = df.sort_values(by='timestamp', ascending=False)
        self._handler.write_data_to_file(df, csv_path)

    def __did_error_appear_this_year(self, error: BrokerNodeConnection.BrokerNodeError) -> bool:
        current_year = self._timestamp_handler.get_current_year()
        year_of_error = self._timestamp_handler.get_utc_year_from_date_string(error.timestamp)
        return current_year == year_of_error

    @staticmethod
    def __convert_error_to_row(error: BrokerNodeConnection.BrokerNodeError) -> pd.DataFrame:
        """
        The var 'repeats' from broker-server can be None, if the error occured just once.
        Var 'timestamp' is in local timezone.
        """
        new_row = {
            'timestamp': error.timestamp,
            'repeats': error.repeats if error.repeats is not None else '1',
            'content': error.content}
        return pd.DataFrame(new_row, index=[0])

    @staticmethod
    def __is_error_already_logged(csv: pd.DataFrame, error_row: pd.DataFrame) -> bool:
        set_csv = set(csv['content'])
        set_error = set(error_row['content'])
        return any(set_csv.intersection(set_error))

    @staticmethod
    def __did_error_row_repeats_change(csv: pd.DataFrame, error_row: pd.DataFrame) -> bool:
        df_intersection = pd.merge(csv, error_row, on='content', how='inner')
        repeats_csv = df_intersection['repeats_x'].values
        repeats_row_error = df_intersection['repeats_y'].values
        return repeats_csv != repeats_row_error

    @staticmethod
    def __delete_old_error_row(csv: pd.DataFrame, error_row: pd.DataFrame) -> pd.DataFrame:
        idx = csv.index[csv['content'] == error_row['content'][0]]
        return csv.drop(index=idx)


class NodeResourceRetriever(BrokerNodeRetriever):
    """
    Fetches broker node resources such as installed versions or packages and saves them to a text file.
    """
    _handler = TextWriter()

    def download_broker_data_to_file(self, node_id: str):
        dir_working = self._init_node_directory_if_nonexisting(node_id)
        self.__fetch_broker_node_resource_to_text_file('versions', node_id, dir_working)
        self.__fetch_broker_node_resource_to_text_file('rscript', node_id, dir_working)
        self.__fetch_broker_node_resource_to_text_file('python', node_id, dir_working)
        self.__fetch_broker_node_resource_to_text_file('import-scripts', node_id, dir_working)

    def __fetch_broker_node_resource_to_text_file(self, resource_type: str, node_id: str, working_dir: str):
        """
        Fetches a specific broker node resource and saves it to a text file.
        - Changes in resource items are logged by comparing the existing information in the file
        (from the previous day) with the current information from the broker.
        - Older information is overwritten with newer information after logging.
        """
        response = self._broker_node_connection.get_broker_node_resource(node_id, resource_type)
        response = self.__clean_dictionary(response)
        resourcepath = self.__generate_resource_file_path(resource_type, node_id, working_dir)
        if os.path.exists(resourcepath):
            resource = self._handler.load_txt_file_as_dict(resourcepath)
            logpath = self.__generate_resource_log_path(resource_type, node_id, working_dir)
            self.__log_new_and_updated_items(logpath, response, resource)
            self.__log_deleted_items(logpath, response, resource)
        self._handler.save_dict_as_txt_file(response, resourcepath)

    def __log_new_and_updated_items(self, logpath: str, broker: dict, resource: dict):
        """
        The log includes the timestamp, resource name, previous version (if exists), and new version.
        """
        broker_set = set(broker.items())
        resource_set = set(resource.items())
        difference = broker_set.difference(resource_set)
        if difference:
            for resource_name, new_version in difference:
                current = self._timestamp_handler.get_current_date()
                old_version = resource.get(resource_name, 'NEW')
                data = f'{current} : [{resource_name}] {old_version} --> {new_version}\n'
                self._handler.write_data_to_file(data, logpath)

    def __log_deleted_items(self, logpath: str, broker: dict, resource: dict):
        """
        The log includes the timestamp, resource name, and the fact that it has been deleted.
        """
        broker_set = set(broker.keys())
        resource_set = set(resource.keys())
        difference = resource_set.difference(broker_set)
        if difference:
            for resource_name in difference:
                current = self._timestamp_handler.get_current_date()
                old_version = resource.get(resource_name)
                data = f'{current} : [{resource_name}] {old_version} --> DELETED\n'
                self._handler.write_data_to_file(data, logpath)

    @staticmethod
    def __clean_dictionary(dictionary: dict) -> dict:
        """
        Cleans the dictionary by setting None values to '-', and removing possible '\n' from values.
        """
        for key, value in dictionary.copy().items():
            if value is None:
                dictionary[key] = '-'
            else:
                dictionary[key] = value.replace('\n', '')
        return dictionary

    @staticmethod
    def __generate_resource_file_path(resource_type: str, node_id: str, working_dir: str) -> str:
        """
        Generates the file path for the resource file (file with current status of resource)
        """
        name_file = ''.join([node_id, '_', resource_type, '.txt'])
        return os.path.join(working_dir, name_file)

    @staticmethod
    def __generate_resource_log_path(resource_type: str, node_id: str, working_dir: str) -> str:
        """
        Generates the file path for the log file (file with containing all changes of a resrouce)
        """
        name_file = ''.join([node_id, '_log_', resource_type, '.log'])
        return os.path.join(working_dir, name_file)


class NodeRetrieverManager:
    """
    Manages the fetching of broker node information.
    """

    def __init__(self):
        self.__list_node_ids = BrokerNodeConnection().get_broker_nodes()
        self.__info_fetcher = NodeInfoRetriever()
        self.__error_fetcher = NodeErrorRetriever()
        self.__resources_fetcher = NodeResourceRetriever()

    def fetch_broker_node_information(self):
        for id_node in self.__list_node_ids:
            self.__info_fetcher.download_broker_data_to_file(id_node)
            self.__error_fetcher.download_broker_data_to_file(id_node)
            self.__resources_fetcher.download_broker_data_to_file(id_node)


if __name__ == '__main__':
    if len(sys.argv) == 1:
        raise SystemExit(f'Usage: python {__file__} <path_to_config.toml>')
    Main.main(sys.argv[1], lambda: NodeRetrieverManager().fetch_broker_node_information())
