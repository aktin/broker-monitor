import os
import sys
import unittest
from pathlib import Path
from shutil import rmtree

this_path = Path(os.path.realpath(__file__))
path_src = os.path.join(this_path.parents[2], 'src')
sys.path.insert(0, path_src)

import bs4
import pandas as pd
from common import InfoCSVHandler, ConfigReader
from csv_to_confluence import TemplatePageLoader, TemplatePageCSVInfoWriter


class TestTemplatePageCSVInfoWriter(unittest.TestCase):
    __DEFAULT_NODE_ID: str = '0'
    __WORKING_DIR: str = None
    __TEMPLATE: str = None

    @classmethod
    def setUpClass(cls):
        path_settings = os.path.join(this_path.parents[1], 'resources', 'settings.toml')
        ConfigReader().load_config_as_env_vars(path_settings)
        cls.__WORKING_DIR = os.environ['DIR.WORKING'] if os.environ['DIR.WORKING'] else os.getcwd()
        cls.__CSV_HANDLER = InfoCSVHandler()
        cls.__CSV_INFO_WRITER = TemplatePageCSVInfoWriter()
        name_csv = InfoCSVHandler().generate_node_csv_name(cls.__DEFAULT_NODE_ID)
        cls.__DEFAULT_CSV_PATH = os.path.join(cls.__WORKING_DIR, cls.__DEFAULT_NODE_ID, name_csv)

    def setUp(self):
        loader = TemplatePageLoader()
        self.__TEMPLATE = loader.get_template_page()
        dir_working = os.path.join(self.__WORKING_DIR, self.__DEFAULT_NODE_ID)
        if not os.path.exists(dir_working):
            os.makedirs(dir_working)

    def tearDown(self):
        rmtree(self.__WORKING_DIR)

    def test_write_template_from_one_row(self):
        self.__create_csv1()
        page = self.__CSV_INFO_WRITER.add_content_to_template_page(self.__TEMPLATE, self.__DEFAULT_NODE_ID)
        self.__check_template_page_dates(page, '2022-01-01 12:00:00', '2022-01-01 11:00:00', '2022-01-01 00:00:00', '-', '-')
        self.__check_template_page_weekly_imports(page, '-', '-', '-', '-', '-')
        self.__check_template_page_daily_imports(page, '-', '-', '-', '-', '-')

    def test_write_template_from_multiple_rows(self):
        self.__create_csv2()
        page = self.__CSV_INFO_WRITER.add_content_to_template_page(self.__TEMPLATE, self.__DEFAULT_NODE_ID)
        self.__check_template_page_dates(page, '2022-02-02 12:00:00', '2022-10-10 11:00:00', '2022-02-02 00:00:00', '2022-02-02 10:00:00', '2022-02-02 10:00:00')
        self.__check_template_page_weekly_imports(page, '1000.00', '1000.00', '1000.00', '1000.00', '25.00')
        self.__check_template_page_daily_imports(page, '2000', '2000', '2000', '2000', '50.0')

    def test_write_template_from_hourly_rows(self):
        """
        Weekly mean uses the last row of each day, not the last seven rows.
        """
        self.__create_csv_with_hourly_rows()
        page = self.__CSV_INFO_WRITER.add_content_to_template_page(self.__TEMPLATE, self.__DEFAULT_NODE_ID)
        self.__check_template_page_weekly_imports(page, '3000.00', '3000.00', '3000.00', '3000.00', '50.00')
        self.__check_template_page_daily_imports(page, '4000', '4000', '4000', '4000', '50.0')

    def test_write_template_from_row_with_null_values(self):
        self.__create_csv_with_null_values()
        with self.assertRaises(TypeError):
            _ = self.__CSV_INFO_WRITER.add_content_to_template_page(self.__TEMPLATE, self.__DEFAULT_NODE_ID)

    def test_write_template_from_empty_csv(self):
        self.__create_empty_csv()
        with self.assertRaises(IndexError):
            _ = self.__CSV_INFO_WRITER.add_content_to_template_page(self.__TEMPLATE, self.__DEFAULT_NODE_ID)

    def test_write_template_from_missing_csv(self):
        with self.assertRaises(FileNotFoundError):
            _ = self.__CSV_INFO_WRITER.add_content_to_template_page(self.__TEMPLATE, '99')

    def test_write_from_missing_csv_rows(self):
        self.__create_csv1_with_missing_rows()
        with self.assertRaises(KeyError):
            _ = self.__CSV_INFO_WRITER.add_content_to_template_page(self.__TEMPLATE, self.__DEFAULT_NODE_ID)

    def test_write_into_missing_template_keys(self):
        template = bs4.BeautifulSoup(self.__TEMPLATE, 'html.parser')
        with self.assertRaises(AttributeError):
            template.find(class_='nonexisting').string.replace_with('value')

    def __create_csv1(self):
        df = pd.DataFrame(columns=self.__CSV_HANDLER.get_csv_columns())
        df.loc[len(df)] = ['2022-01-01 12:00:00+0100', '2022-01-01 11:00:00+0100', '2022-01-01 00:00:00+0100', '-', '-',
                           '0', '0', '0', '0', '0.0', '-', '-', '-', '-', '-']
        self.__CSV_HANDLER.write_data_to_file(df, self.__DEFAULT_CSV_PATH)

    def __create_csv2(self):
        df = pd.DataFrame(columns=self.__CSV_HANDLER.get_csv_columns())
        df.loc[len(df)] = ['2022-01-01 12:00:00+0100', '2022-10-10 11:00:00+0200', '2022-01-01 00:00:00+0100', '-', '-',
                           '0', '0', '0', '0', '0.0', '-', '-', '-', '-', '-']
        df.loc[len(df)] = ['2022-02-02 12:00:00+0100', '2022-10-10 11:00:00+0200', '2022-02-02 00:00:00+0100', '2022-02-02 10:00:00+0100', '2022-02-02 10:00:00+0100',
                           '2000', '2000', '2000', '2000', '50.0', '2000', '2000', '2000', '2000', '50.0']
        self.__CSV_HANDLER.write_data_to_file(df, self.__DEFAULT_CSV_PATH)

    def __create_csv_with_hourly_rows(self):
        df = pd.DataFrame(columns=self.__CSV_HANDLER.get_csv_columns())
        for date, value in [('2022-02-01 12:00:00+0100', '1000'), ('2022-02-01 13:00:00+0100', '2000'),
                            ('2022-02-02 12:00:00+0100', '3000'), ('2022-02-02 13:00:00+0100', '4000')]:
            df.loc[len(df)] = [date, '2022-10-10 11:00:00+0200', '2022-02-01 00:00:00+0100', '2022-02-02 10:00:00+0100', '2022-02-02 10:00:00+0100',
                               value, value, value, value, '50.0', value, value, value, value, '50.0']
        self.__CSV_HANDLER.write_data_to_file(df, self.__DEFAULT_CSV_PATH)

    def __create_csv_with_null_values(self):
        df = pd.DataFrame(columns=self.__CSV_HANDLER.get_csv_columns())
        df.loc[len(df)] = ['2022-01-01 12:00:00+0100', '2022-01-01 11:00:00+0100', '2022-01-01 00:00:00+0100', None, '-', None, '0', '0', '0', '0.0', '-', '-', '-', '-', '-']
        self.__CSV_HANDLER.write_data_to_file(df, self.__DEFAULT_CSV_PATH)

    def __create_empty_csv(self):
        df = pd.DataFrame(columns=self.__CSV_HANDLER.get_csv_columns())
        self.__CSV_HANDLER.write_data_to_file(df, self.__DEFAULT_CSV_PATH)

    def __create_csv1_with_missing_rows(self):
        df = pd.DataFrame(columns=['date', 'last_contact', 'last_start'])
        df.loc[len(df)] = ['2022-01-01 12:00:00+0100', '2022-01-01 11:00:00+0100', '2022-01-01 00:00:00+0100']
        self.__CSV_HANDLER.write_data_to_file(df, self.__DEFAULT_CSV_PATH)

    def __check_template_page_dates(self, page_template: str, last_check: str, last_contact: str, last_start: str, last_write: str, last_reject: str):
        page = bs4.BeautifulSoup(page_template, 'html.parser')
        self.assertEqual(last_check, page.find(class_='last_check').string)
        self.assertEqual(last_contact, page.find(class_='last_contact').string)
        self.assertEqual(last_start, page.find(class_='last_start').string)
        self.assertEqual(last_write, page.find(class_='last_write').string)
        self.assertEqual(last_reject, page.find(class_='last_reject').string)

    def __check_template_page_weekly_imports(self, page_template: str, imported: str, updated: str, invalid: str, failed: str, error_rate: str):
        page = bs4.BeautifulSoup(page_template, 'html.parser')
        self.assertEqual(imported, page.find(class_='imported').string)
        self.assertEqual(updated, page.find(class_='updated').string)
        self.assertEqual(invalid, page.find(class_='invalid').string)
        self.assertEqual(failed, page.find(class_='failed').string)
        self.assertEqual(error_rate, page.find(class_='error_rate').string)

    def __check_template_page_daily_imports(self, page_template: str, imported: str, updated: str, invalid: str, failed: str, error_rate: str):
        page = bs4.BeautifulSoup(page_template, 'html.parser')
        self.assertEqual(imported, page.find(class_='daily_imported').string)
        self.assertEqual(updated, page.find(class_='daily_updated').string)
        self.assertEqual(invalid, page.find(class_='daily_invalid').string)
        self.assertEqual(failed, page.find(class_='daily_failed').string)
        self.assertEqual(error_rate, page.find(class_='daily_error_rate').string)


if __name__ == '__main__':
    unittest.main()
