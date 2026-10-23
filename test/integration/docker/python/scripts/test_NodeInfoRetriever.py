import os
import unittest
from datetime import datetime, timedelta
from shutil import rmtree

import pandas as pd
import pytz
from common import InfoCSVHandler, ConfigReader
from dateutil import parser
from node_to_csv import NodeInfoRetriever

from BrokerNodeDummy import BrokerNodeDummy, BrokerNodeImports


class TestNodeInfoRetriever(unittest.TestCase):
    __DEFAULT_NODE_ID: str = '0'
    __DEFAULT_API_KEY: str = 'xxxApiKey123'
    __DIR_ROOT: str = None

    @classmethod
    def setUpClass(cls):
        ConfigReader().load_config_as_env_vars('settings.toml')
        cls.__DIR_ROOT = os.environ['DIR.WORKING'] if os.environ['DIR.WORKING'] else os.getcwd()
        cls.__CSV_HANDLER = InfoCSVHandler()
        name_csv = InfoCSVHandler().generate_node_csv_name(cls.__DEFAULT_NODE_ID)
        cls.__DEFAULT_CSV_PATH = os.path.join(cls.__DIR_ROOT, cls.__DEFAULT_NODE_ID, name_csv)
        cls.__RETRIEVER = NodeInfoRetriever()
        cls.__DUMMY = BrokerNodeDummy(cls.__DEFAULT_API_KEY)

    def setUp(self):
        stats = self.__create_stats1()
        self.__DUMMY.put_import_info_on_broker(stats)
        self.__RETRIEVER.download_broker_data_to_file(self.__DEFAULT_NODE_ID)

    def tearDown(self):
        [rmtree(name) for name in os.listdir(self.__DIR_ROOT) if os.path.isdir(name) and len(name) <= 2]

    def test_init_working_csv(self):
        self.__init_new_dummy_and_put_default_stats_on_node(self.__DEFAULT_API_KEY)
        self.__init_new_dummy_and_put_default_stats_on_node('xxxApiKey567')
        self.__make_new_fetching_and_check_csv_count(self.__DEFAULT_NODE_ID, 1)
        self.__make_new_fetching_and_check_csv_count(self.__DEFAULT_NODE_ID, 1)
        self.__make_new_fetching_and_check_csv_count('1', 2)

    def __init_new_dummy_and_put_default_stats_on_node(self, api_key: str):
        stats = self.__create_stats1()
        dummy = BrokerNodeDummy(api_key)
        dummy.put_import_info_on_broker(stats)

    def __make_new_fetching_and_check_csv_count(self, id_node: str, count: int):
        self.__RETRIEVER.download_broker_data_to_file(id_node)
        list_csv = self.__list_csv_in_working_directory()
        self.assertEqual(count, len(list_csv))

    def __list_csv_in_working_directory(self) -> list:
        list_csv = []
        for root, dirs, files in os.walk(self.__DIR_ROOT):
            for name in files:
                if name.endswith('.csv'):
                    list_csv.append(name)
        return list_csv

    def test_csv_columns(self):
        df = self.__CSV_HANDLER.read_csv_as_df(self.__DEFAULT_CSV_PATH)
        header = list(df.columns)
        expected_columns = ['date', 'last_contact', 'last_start', 'last_write', 'last_reject', 'imported',
                            'updated', 'invalid', 'failed', 'error_rate', 'daily_imported',
                            'daily_updated', 'daily_invalid', 'daily_failed', 'daily_error_rate']
        self.assertTrue(len(expected_columns), len(header))
        self.assertCountEqual(expected_columns, header)

    def test_fetch_default_stats_to_csv(self):
        df = self.__CSV_HANDLER.read_csv_as_df(self.__DEFAULT_CSV_PATH)
        self.assertEqual(1, df.shape[0])
        self.__check_date_stats_in_csv_row(df.iloc[0], '2020-01-01 01:00:00+0100', '-', '-')
        self.__check_global_import_stats_in_csv_row(df.iloc[0], '0', '0', '0', '0', '-')
        self.__check_daily_import_stats_in_csv_row(df.iloc[0], '-', '-', '-', '-', '-')

    def test_update_default_stats_in_csv(self):
        stats2 = self.__create_stats2()
        df = self.__put_import_stats_on_broker_and_get_fetched_csv_as_df(stats2)
        self.assertEqual(1, df.shape[0])
        self.__check_date_stats_in_csv_row(df.iloc[0], '2020-01-01 01:00:00+0100', '2020-03-03 01:00:00+0100', '2020-03-03 01:00:00+0100')
        self.__check_global_import_stats_in_csv_row(df.iloc[0], '2000', '400', '250', '350', '20.00')
        self.__check_daily_import_stats_in_csv_row(df.iloc[0], '-', '-', '-', '-', '-')

    def test_fetch_next_stats_in_csv(self):
        self.__change_date_of_current_csv_to_past_days(1)
        stats2 = self.__create_stats2()
        df = self.__put_import_stats_on_broker_and_get_fetched_csv_as_df(stats2)
        self.assertEqual(2, df.shape[0])
        self.__check_date_stats_in_csv_row(df.iloc[1], '2020-01-01 01:00:00+0100', '2020-03-03 01:00:00+0100', '2020-03-03 01:00:00+0100')
        self.__check_global_import_stats_in_csv_row(df.iloc[1], '2000', '400', '250', '350', '20.00')
        self.__check_daily_import_stats_in_csv_row(df.iloc[1], '2000', '400', '250', '350', '20.00')

    def test_fetch_next_stats_in_csv_next_hour(self):
        """
        A new hour appends a new row. Daily stats refer to the last row of the previous day, not to the previous row.
        """
        self.__change_date_of_current_csv_to_past_days(1)
        self.__put_import_stats_on_broker_and_get_fetched_csv_as_df(self.__create_stats2())
        self.__change_date_of_last_csv_row_by_hours(1)  # forward, so the row can never fall into yesterday
        df = self.__put_import_stats_on_broker_and_get_fetched_csv_as_df(self.__create_stats3())
        self.assertEqual(3, df.shape[0])
        self.__check_global_import_stats_in_csv_row(df.iloc[2], '3000', '600', '300', '400', '16.28')
        self.__check_daily_import_stats_in_csv_row(df.iloc[2], '3000', '600', '300', '400', '16.28')

    def test_fetch_next_stats_in_csv_timegap(self):
        self.__change_date_of_current_csv_to_past_days(5)
        stats2 = self.__create_stats2()
        df = self.__put_import_stats_on_broker_and_get_fetched_csv_as_df(stats2)
        self.assertEqual(2, df.shape[0])
        self.__check_date_stats_in_csv_row(df.iloc[1], '2020-01-01 01:00:00+0100', '2020-03-03 01:00:00+0100', '2020-03-03 01:00:00+0100')
        self.__check_global_import_stats_in_csv_row(df.iloc[1], '2000', '400', '250', '350', '20.00')
        self.__check_daily_import_stats_in_csv_row(df.iloc[1], '-', '-', '-', '-', '-')

    def test_fetch_next_stats_in_csv_with_dwh_restart(self):
        self.__change_date_of_current_csv_to_past_days(1)
        stats2 = self.__create_stats2_dwh_restart()
        df = self.__put_import_stats_on_broker_and_get_fetched_csv_as_df(stats2)
        self.assertEqual(2, df.shape[0])
        self.__check_date_stats_in_csv_row(df.iloc[1], '2020-01-01 13:00:00+0100', '2020-03-03 01:00:00+0100', '2020-03-03 01:00:00+0100')
        self.__check_global_import_stats_in_csv_row(df.iloc[1], '2000', '400', '250', '350', '20.00')
        self.__check_daily_import_stats_in_csv_row(df.iloc[1], '-', '-', '-', '-', '-')

    def test_fetch_new_stats_in_csv_after_year_change(self):
        self.__change_date_of_current_csv_to_past_days(1)
        self.__rename_csv_to_last_years_csv(self.__DEFAULT_CSV_PATH)
        stats2 = self.__create_stats2()
        df = self.__put_import_stats_on_broker_and_get_fetched_csv_as_df(stats2)
        self.assertEqual(1, df.shape[0])
        self.__check_date_stats_in_csv_row(df.iloc[0], '2020-01-01 01:00:00+0100', '2020-03-03 01:00:00+0100', '2020-03-03 01:00:00+0100')
        self.__check_global_import_stats_in_csv_row(df.iloc[0], '2000', '400', '250', '350', '20.00')
        self.__check_daily_import_stats_in_csv_row(df.iloc[0], '2000', '400', '250', '350', '20.00')

    def test_fetch_new_stats_in_csv_after_year_change_timegap(self):
        self.__change_date_of_current_csv_to_past_days(5)
        self.__rename_csv_to_last_years_csv(self.__DEFAULT_CSV_PATH)
        stats2 = self.__create_stats2()
        df = self.__put_import_stats_on_broker_and_get_fetched_csv_as_df(stats2)
        self.assertEqual(1, df.shape[0])
        self.__check_date_stats_in_csv_row(df.iloc[0], '2020-01-01 01:00:00+0100', '2020-03-03 01:00:00+0100', '2020-03-03 01:00:00+0100')
        self.__check_global_import_stats_in_csv_row(df.iloc[0], '2000', '400', '250', '350', '20.00')
        self.__check_daily_import_stats_in_csv_row(df.iloc[0], '-', '-', '-', '-', '-')

    def __create_stats1(self):
        return BrokerNodeImports(self.__add_timezone_to_date_string('20200101'),
                                 '',
                                 '',
                                 '0',
                                 '0',
                                 '0',
                                 '0')

    def __create_stats2(self):
        return BrokerNodeImports(self.__add_timezone_to_date_string('20200101'),
                                 self.__add_timezone_to_date_string('20200303'),
                                 self.__add_timezone_to_date_string('20200303'),
                                 '2000',
                                 '400',
                                 '250',
                                 '350')

    def __create_stats3(self):
        return BrokerNodeImports(self.__add_timezone_to_date_string('20200101'),
                                 self.__add_timezone_to_date_string('20200303'),
                                 self.__add_timezone_to_date_string('20200303'),
                                 '3000',
                                 '600',
                                 '300',
                                 '400')

    def __create_stats2_dwh_restart(self):
        return BrokerNodeImports(self.__add_timezone_to_date_string('202001011200'),
                                 self.__add_timezone_to_date_string('20200303'),
                                 self.__add_timezone_to_date_string('20200303'),
                                 '2000',
                                 '400',
                                 '250',
                                 '350')

    @staticmethod
    def __add_timezone_to_date_string(date: str) -> str:
        d = parser.parse(date).astimezone(pytz.timezone('Europe/Berlin'))
        return d.strftime('%Y-%m-%d %H:%M:%S%z')

    def __check_date_stats_in_csv_row(self, row: pd.Series, start: str, last_write: str, last_reject: str):
        self.assertEqual(start, row['last_start'])
        self.assertEqual(last_write, row['last_write'])
        self.assertEqual(last_reject, row['last_reject'])

    def __check_global_import_stats_in_csv_row(self, row: pd.Series, imported: str, updated: str, invalid: str, failed: str, error_rate: str):
        self.assertEqual(imported, row['imported'])
        self.assertEqual(updated, row['updated'])
        self.assertEqual(invalid, row['invalid'])
        self.assertEqual(failed, row['failed'])
        self.assertEqual(error_rate, row['error_rate'])

    def __check_daily_import_stats_in_csv_row(self, row: pd.Series, imported: str, updated: str, invalid: str, failed: str, error_rate: str):
        self.assertEqual(imported, row['daily_imported'])
        self.assertEqual(updated, row['daily_updated'])
        self.assertEqual(invalid, row['daily_invalid'])
        self.assertEqual(failed, row['daily_failed'])
        self.assertEqual(error_rate, row['daily_error_rate'])

    def __put_import_stats_on_broker_and_get_fetched_csv_as_df(self, payload):
        self.__DUMMY.put_import_info_on_broker(payload)
        self.__RETRIEVER.download_broker_data_to_file(self.__DEFAULT_NODE_ID)
        return self.__CSV_HANDLER.read_csv_as_df(self.__DEFAULT_CSV_PATH)

    def __change_date_of_current_csv_to_past_days(self, days: int):
        df = self.__CSV_HANDLER.read_csv_as_df(self.__DEFAULT_CSV_PATH)
        df.loc[0, 'date'] = datetime.utcnow().replace(tzinfo=pytz.UTC) - timedelta(days=days)
        self.__CSV_HANDLER.write_data_to_file(df, self.__DEFAULT_CSV_PATH)

    def __change_date_of_last_csv_row_by_hours(self, hours: int):
        df = self.__CSV_HANDLER.read_csv_as_df(self.__DEFAULT_CSV_PATH)
        df.loc[df.index[-1], 'date'] = datetime.utcnow().replace(tzinfo=pytz.UTC) + timedelta(hours=hours)
        self.__CSV_HANDLER.write_data_to_file(df, self.__DEFAULT_CSV_PATH)

    @staticmethod
    def __rename_csv_to_last_years_csv(path_csv: str):
        last_year = str(datetime.now().year - 1)
        path_csv_new = path_csv[:-8] + last_year + path_csv[-4:]
        os.rename(path_csv, path_csv_new)


if __name__ == '__main__':
    unittest.main()
